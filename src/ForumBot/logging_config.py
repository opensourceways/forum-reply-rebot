import logging
import os
from datetime import datetime
from src.utils import load_config
from logging.handlers import RotatingFileHandler

def setup_logger(name, log_file=None, level=logging.INFO, max_bytes=20 * 1024 * 1024, backup_count=4):
    """
    设置日志记录器，支持日志轮转

    Args:
        name: 日志记录器名称
        log_file: 日志文件路径
        level: 日志级别
        max_bytes: 单个日志文件最大字节数，默认20MB
        backup_count: 保留的备份日志文件数量，默认5个
    """
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(name)
    logger.setLevel(level)

    logger.propagate = False

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

        # 使用RotatingFileHandler实现日志轮转
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# 从配置文件加载日志配置
try:
    config = load_config() #是否加载
    log_dir = config.get('logging', {}).get('log_dir', 'logs')
    main_log_file = config.get('logging', {}).get('main_log_file', 'main.log')

    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)

    # 构建完整的日志文件路径
    full_log_path = os.path.join(log_dir, main_log_file)
    main_logger = setup_logger('AskRobotPOC', full_log_path, max_bytes=20*1024*1024, backup_count=4)
except Exception as e:
    print(f"加载日志配置失败: {e}")
    # 如果配置加载失败，使用默认配置
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    full_log_path = os.path.join(log_dir, 'main.log')
    main_logger = setup_logger('AskRobotPOC', full_log_path)