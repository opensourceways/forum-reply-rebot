import logging
import yaml
import os

def load_config(config_file='config/config.yaml'):
    """
    加载配置文件
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logging.error(f"加载配置文件失败: {e}")

def clear_directory(directory_path, ignore_file):
    """只删除文件，保留目录结构"""
    if not os.path.exists(directory_path):
        logging.error(f"目录 {directory_path} 不存在")
        return

    ignore_file_name = os.path.basename(ignore_file)
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            # 跳过需要忽略的文件
            if ignore_file and file == ignore_file_name:
                continue
            file_path = os.path.join(root, file)
            os.remove(file_path)
    logging.info(f"已清空目录 {directory_path}")