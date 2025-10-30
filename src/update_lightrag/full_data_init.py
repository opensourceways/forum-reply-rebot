import requests
import json
import os
import time
from src.update_lightrag.forum_data_Fetcher import ForumDataFetcher
from src.update_lightrag.lightrag_client import LightRAGClient
from src.update_lightrag.filter import Filter
from src.update_lightrag.image_processor import ImageProcessor
from src.utils import clear_directory
from src.update_lightrag.update_time import save_last_update_time
from src.ForumBot.logging_config import main_logger as logger
from src.utils import load_config


class FullDataUpdate:
    def __init__(self):
        self.config = load_config()
        self.forum_data_fetcher = ForumDataFetcher(self.config)
        self.lightrag_client = LightRAGClient(self.config)
        self.filter = Filter(self.config)
        self.image_processor = ImageProcessor(self.config)

    # 获取论坛数据主函数
    def get_all_forum_data(self):
        logger.info("开始获取全部论坛数据")
        page = 0
        while True:
            try:
                topics = self.forum_data_fetcher.extract_one_page_topic_data(page)
                page += 1
                if not topics:
                    logger.info("未找到更多topic")
                    break
            except requests.exceptions.RequestException as e:
                logger.error(f"请求失败: {e}")
                break
            logger.info(f"从第 {page} 页提取了 {len(topics)} 个topic")

    def compare_folder_with_mapping(self, folder_path, mapping_file):
        """
        比较文件夹中的文件与mapping文件的差异
        """
        new_files_output = self.config['lightrag_paths']['new_rag_files']
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
        if os.path.exists(folder_path):
            for file in os.listdir(folder_path):
                if os.path.isfile(os.path.join(folder_path, file)):
                    folder_files.add(file)
        else:
            logger.error(f"文件夹 {folder_path} 不存在")
            return

        # 获取mapping中的所有文件名
        mapped_files = set(file_mapping.keys())

        # 新增的文件：在文件夹中但不在mapping中的文件
        new_files = folder_files - mapped_files

        # 5. 处理新增文件
        if new_files:
            with open(new_files_output, 'w', encoding='utf-8') as f:
                for filename in sorted(new_files):
                    f.write(f"{filename}\n")
            logger.info(f"新增文件已写入 {new_files_output}")

    def get_full_update_file(self):
        lightrag_url = self.config['retrieval']['base_url']
        self.lightrag_client.get_filename_id_mapping_from_lightrag(lightrag_url)

        self.compare_folder_with_mapping(
            folder_path=self.config['lightrag_paths']['rag_data_dir'],
            mapping_file=self.config['lightrag_paths']['files_id_mapping']
        )

    def update_full_data(self):
        logger.info("开始初始化LightRAG数据")
        # 检查LightRAG是否为空，若不为空则不进行初始化
        if not self.lightrag_client.is_lightrag_empty(self.config['retrieval']['base_url']):
            logger.info("LightRAG不为空，不进行初始化")
            return

        # 获取论坛数据之前先清理文件夹
        clear_directory(self.config['lightrag_paths']['lightrag_root_dir'],
                        self.config['lightrag_paths']['update_time'])
        self.get_all_forum_data()  # 获取所有论坛数据

        save_last_update_time(self.config['lightrag_paths']['update_time'])  # 保存更新时间
        self.get_full_update_file()  # 获取全量更新文件
        self.filter.filter_upload_files()  # 过滤上传文件
        self.image_processor.process_image_from_files(self.config['lightrag_paths']['new_rag_files'])  # 处理文件中的图片
        self.lightrag_client.upload_all_documents_from_file(self.config['lightrag_paths']['new_rag_files'],
                                                            self.config['retrieval']['base_url'])  # 上传文件
        # 检查文件是否已经上传完成
        while True:
            if self.lightrag_client.is_all_file_processed(self.config['retrieval']['base_url']):
                logger.info("所有文件处理完成")
                # 清空本地文件夹
                clear_directory(self.config['lightrag_paths']['lightrag_root_dir'])
                break
            else:
                time.sleep(5)
