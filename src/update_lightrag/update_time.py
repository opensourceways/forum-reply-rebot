from datetime import datetime, timezone
from src.ForumBot.logging_config import main_logger as logger

def save_last_update_time(update_time_file):
    """保存当前时间作为最后更新时间"""
    # 获取当前UTC时间
    current_time = datetime.now(timezone.utc).isoformat()
    # 保存到配置指定的文件
    try:
        with open(update_time_file, 'w', encoding='utf-8') as f:
            f.write(current_time)
        logger.info(f"最后更新时间已保存: {current_time}")
    except Exception as e:
        logger.error(f"保存最后更新时间失败: {e}")


def get_last_update_time(update_time_file, config_default_time=None):
    """从文件中读取最后更新时间"""
    try:
        with open(update_time_file, 'r', encoding='utf-8') as f:
            last_update_time_str = f.read().strip()
        # 如果文件内容为空，则从配置中读取默认值
        if not last_update_time_str and config_default_time:
            logger.info("更新时间文件内容为空，使用配置中的默认时间")
            return config_default_time
        return last_update_time_str
    except FileNotFoundError:
        logger.warning(f"更新时间文件 {update_time_file} 不存在")
        # 文件不存在时从配置中读取默认值
        if config_default_time:
            logger.info("使用配置中的默认时间")
            return config_default_time
        return None
    except Exception as e:
        logger.error(f"读取更新时间文件失败: {e}")
        # 异常情况下也尝试返回配置中的默认值
        if config_default_time:
            logger.info("使用配置中的默认时间")
            return config_default_time
        return None