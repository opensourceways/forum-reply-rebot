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

def delete_config_file(config_file='config/config.yaml'):
    """
    删除配置文件以防止敏感信息落盘
    """
    try:
        if os.path.exists(config_file):
            os.remove(config_file)
            # 验证文件是否真的被删除
            if os.path.exists(config_file):
                logging.warning(f"配置文件 {config_file} 似乎未被成功删除")
            else:
                logging.info(f"已成功删除配置文件 {config_file}")
        else:
            logging.info(f"配置文件 {config_file} 不存在")
    except Exception as e:
        logging.error(f"删除配置文件失败: {e}")