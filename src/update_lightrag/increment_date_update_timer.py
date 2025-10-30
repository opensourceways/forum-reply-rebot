import schedule
import time
import requests
import os
import json
from .forum_data_Fetcher import ForumDataFetcher
from .lightrag_client import LightRAGClient
from .filter import Filter
from .image_processor import ImageProcessor
from src.utils import clear_directory
from src.ForumBot.logging_config import main_logger as logger
from src.update_lightrag.update_time import save_last_update_time
from src.update_lightrag.update_time import get_last_update_time
from src.utils import load_config
from datetime import datetime, timezone


# 定时器函数主函数流程
class UpdateIncrementData:
    def __init__(self, config):
        self.config = config
        self.forum_data_fetcher = ForumDataFetcher(self.config)
        self.lightrag_client = LightRAGClient(self.config)
        self.filter = Filter(self.config)
        self.image_processor = ImageProcessor(self.config)

    def get_new_forum_data(self, last_update_time):
        logger.info("开始获取论坛更新数据")
        page = 0
        if isinstance(last_update_time, str):
            last_update_time = datetime.fromisoformat(last_update_time.replace('Z', '+00:00'))

        while True:
            try:
                data = self.forum_data_fetcher.fetch_one_page_data(page)
                topics = data.get('topic_list', {}).get('topics', [])

                if not topics:
                    logger.info("未找到更多topic")
                    break

                for topic in topics:
                    if topic.get('pinned', False):
                        continue

                    bumped_at_str = topic.get('bumped_at')
                    if not bumped_at_str:
                        continue

                    try:
                        bumped_at = datetime.fromisoformat(bumped_at_str.replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"主题 {topic.get('id')} 的bumped_at格式无效: {bumped_at_str}")
                        continue

                    if bumped_at > last_update_time:
                        self.forum_data_fetcher.get_one_topic_content(topic)
                    else:
                        logger.info(f"已处理到早于上次更新时间的主题，停止处理")
                        return

                page += 1
                logger.info(f"已处理第 {page} 页，找到 {len(topics)} 个主题")

            except requests.exceptions.RequestException as e:
                logger.error(f"请求失败: {e}")
                break
            except Exception as e:
                logger.error(f"处理过程中发生错误: {e}")
                break

    def get_increment_update_file(self, rag_data_dir, mapping_file, delete_files_output, new_files_output):
        lightrag_url = self.config['retrieval']['base_url']
        self.lightrag_client.get_filename_id_mapping_from_lightrag(lightrag_url)

        all_files = []
        # 读取mapping文件
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                file_mapping = json.load(f)
        except FileNotFoundError:
            logger.error(f"Mapping文件 {mapping_file} 不存在")
            return
        except json.JSONDecodeError:
            logger.error(f"Mapping文件 {mapping_file} 格式错误")
            return

        # 获取文件夹中的所有文件名
        folder_files = set()
        if os.path.exists(rag_data_dir):
            for file in os.listdir(rag_data_dir):
                if os.path.isfile(os.path.join(rag_data_dir, file)) and file.endswith('.json'):
                    folder_files.add(file)
                    all_files.append(file)
        else:
            logger.error(f"文件夹 {rag_data_dir} 不存在")
            return

        # 获取mapping中的所有文件名
        mapped_files = set(file_mapping.keys())

        # 找出同时存在于文件夹和mapping中的文件
        common_files = folder_files & mapped_files  # 交集操作

        # 获取对应的文件ID
        common_file_ids = []
        for filename in common_files:
            if filename in file_mapping:
                common_file_ids.append(file_mapping[filename])

        # 将文件ID写入输出文件
        if common_file_ids:
            with open(delete_files_output, 'w', encoding='utf-8') as f:
                for file_id in sorted(common_file_ids):
                    f.write(f"{file_id}\n")
            logger.info(f"找到 {len(common_file_ids)} 个需要删除的文件ID，已写入 {delete_files_output}")
        else:
            # 如果没有共同文件，创建空文件或清空现有文件
            with open(delete_files_output, 'w', encoding='utf-8') as f:
                pass
            logger.info("没有找到需要删除的文件ID")

        # 将所有文件名写入输出文件
        if all_files:
            with open(new_files_output, 'w', encoding='utf-8') as f:
                for filename in sorted(all_files):
                    f.write(f"{filename}\n")
            logger.info(f"已将 {len(all_files)} 个文件写入 {new_files_output}")
        else:
            # 如果没有文件，创建空文件
            with open(new_files_output, 'w', encoding='utf-8') as f:
                pass
            logger.info("文件夹中没有找到JSON文件")

    def update_lightrag_task(self):
        # 若正在处理文件，则不更新
        if self.lightrag_client.is_pipeline_status_busy(self.config['retrieval']['base_url']):
            logger.info("当前管道状态为忙碌，暂不更新")
            return

        # 获取论坛数据之前先清理文件夹
        clear_directory(self.config['lightrag_paths']['lightrag_root_dir'],
                        self.config['lightrag_paths']['update_time'])

        update_time = datetime.fromisoformat(
            get_last_update_time(self.config['lightrag_paths']['update_time'], self.config['last_update_time']))
        self.get_new_forum_data(update_time)  # 获取论坛数据
        save_last_update_time(self.config['lightrag_paths']['update_time'])
        self.get_increment_update_file(self.config['lightrag_paths']['rag_data_dir'],
                                       self.config['lightrag_paths']['files_id_mapping'],
                                       self.config['lightrag_paths']['delete_rag_files_id'],
                                       self.config['lightrag_paths']['new_rag_files'])  # 获取增量数据刷新文件
        self.lightrag_client.delete_document_from_file(self.config['lightrag_paths']['delete_rag_files_id'],
                                                       self.config['retrieval']['base_url'])  # 先删除lightrag上的文件
        self.filter.filter_upload_files()  # 过滤上传文件
        self.image_processor.process_image_from_files(self.config['lightrag_paths']['new_rag_files'])  # 处理文件中的图片
        self.lightrag_client.upload_all_documents_from_file(self.config['lightrag_paths']['new_rag_files'],
                                                            self.config['retrieval']['base_url'])  # 再上传更新后的文件


class UpdateLightRAGTimer:
    """RAG数据刷新定时器类"""

    def __init__(self):
        """
        初始化定时器
        """
        self.config = load_config()
        self.update_increment_data = UpdateIncrementData(self.config)
        self.job = None

    def run_scheduler(self):
        """启动定时器"""
        # 设置定时任务
        logger.info("启动定时任务")
        schedule_interval = self.config['timer']['schedule_interval']
        self.job = schedule.every(schedule_interval).day.at('18:00').do(
            self.update_increment_data.update_lightrag_task)

        # 运行定时任务循环
        while True:
            schedule.run_pending()
            time.sleep(1)
