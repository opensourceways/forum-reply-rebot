import logging
import os
from datetime import datetime
from src.utils import load_config

def setup_logger(name, log_file=None, level=logging.INFO):
    """
    设置日志记录器
    """
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# 从配置文件加载日志配置
try:
    config = load_config()
    log_dir = config.get('logging', {}).get('log_dir', 'logs')
    main_log_file = config.get('logging', {}).get('main_log_file', 'main.log')

    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)

    # 构建完整的日志文件路径
    full_log_path = os.path.join(log_dir, main_log_file)
    main_logger = setup_logger('AskRobotPOC', full_log_path)
except Exception as e:
    print(f"加载日志配置失败: {e}")
    # 如果配置加载失败，使用默认配置
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    full_log_path = os.path.join(log_dir, 'main.log')
    main_logger = setup_logger('AskRobotPOC', full_log_path)