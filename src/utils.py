import logging

import yaml

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

