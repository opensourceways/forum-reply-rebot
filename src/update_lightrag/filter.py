import os
from src.ForumBot.logging_config import main_logger as logger

class Filter:
    def __init__(self, config):
        self.config = config

    def filter_upload_files(self):
        """
        根据config中配置的keywords过滤文件
        """
        logger.info("开始过滤文件")
        new_files_path = self.config['lightrag_paths']['new_rag_files']
        filter_keywords = self.config['filter_keywords']

        # 读取new_rag_files.txt中的文件名
        if not os.path.exists(new_files_path):
            logger.error(f"文件 {new_files_path} 不存在")
            return

        with open(new_files_path, 'r', encoding='utf-8') as f:
            file_paths = [line.strip() for line in f.readlines() if line.strip()]

        # 根据关键词过滤文件名
        filtered_files = []
        for file_path in file_paths:
            should_filter = False
            for keyword in filter_keywords:
                if keyword in file_path:
                    should_filter = True
                    break

            # 只保留不包含过滤关键词的文件
            if not should_filter:
                filtered_files.append(file_path)

        # 将过滤后的文件名写回原文件
        with open(new_files_path, 'w', encoding='utf-8') as f:
            for file_path in filtered_files:
                f.write(f"{file_path}\n")
        logger.info("文件过滤完成")