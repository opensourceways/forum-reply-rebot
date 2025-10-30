from flask import Flask, jsonify
from src.ForumBot.monitor import ForumMonitor
from src.update_lightrag.full_data_init import FullDataUpdate
from src.update_lightrag.increment_date_update_timer import UpdateLightRAGTimer
from src.ForumBot.logging_config import setup_logger
import os
import threading
import time

# 设置主日志记录器
logger = setup_logger('main', 'logs/main.log')

# 初始化 Flask 应用
app = Flask(__name__)

# 全局变量用于跟踪服务状态
service_initialized = False
monitor_instance = None
monitor_thread = None

class MonitorThread(threading.Thread):
    """监控线程类"""
    def __init__(self, monitor):
        threading.Thread.__init__(self)
        self.monitor = monitor
        self.daemon = True  # 设置为守护线程，主程序退出时自动退出

    def run(self):
        """运行监控器"""
        try:
            self.monitor.start()
        except Exception as e:
            logger.error(f"监控线程运行出错: {e}")

def initialize_service():
    """
    初始化服务组件
    """
    global service_initialized, monitor_instance, monitor_thread

    try:
        logger.info("开始初始化服务...")
        # 初始化监控器
        monitor_instance = ForumMonitor()

        # 在单独的线程中启动监控器
        monitor_thread = MonitorThread(monitor_instance)
        monitor_thread.start()

        service_initialized = True
        logger.info("服务初始化成功")
        return True
    except Exception as e:
        logger.error(f"服务初始化失败: {e}")
        service_initialized = False
        return False

# LightRAG数据初始化
def lightrag_data_init():
    """
    LightRAG数据初始化
    """
    try:
        logger.info("开始初始化LightRAG数据...")
        full_data_update = FullDataUpdate()
        full_data_update.update_full_data()

        logger.info("LightRAG数据初始化成功")
        return True
    except Exception as e:
        logger.error(f"LightRAG数据初始化失败: {e}")
        return False

# LightRAG数据更新定时器
def lightrag_data_update_timer():
    """
    在线程中启动lightrag更新定时器
    """

    try:
        logger.info("启动LightRAG更新定时器")
        # 初始化监控器
        update_lightrag_timer = UpdateLightRAGTimer()

        # 在单独线程中启动定时器
        scheduler_thread = threading.Thread(target=update_lightrag_timer.run_scheduler)
        scheduler_thread.daemon = True  # 设置为守护线程
        scheduler_thread.start()

        logger.info("LightRAG更新定时器启动成功")
        return True
    except Exception as e:
        logger.error(f"LightRAG更新定时器启动失败: {e}")
        return False

@app.route('/health', methods=['GET'])
def health_check():
    """
    健康检查接口
    返回200表示服务正常运行，返回503表示服务异常
    """
    if service_initialized and monitor_instance and monitor_thread and monitor_thread.is_alive():
        return jsonify({
            "status": "healthy",
            "message": "Service is running normally"
        }), 200
    else:
        return jsonify({
            "status": "unhealthy",
            "message": "Service not initialized or monitor not running"
        }), 503

@app.route('/health/detail', methods=['GET'])
def detailed_health_check():
    """
    详细的健康检查接口
    返回更详细的服务状态信息
    """
    health_info = {
        "status": "healthy" if service_initialized and monitor_instance and monitor_thread and monitor_thread.is_alive() else "unhealthy",
        "components": {
            "service_initialized": service_initialized,
            "monitor_instance": monitor_instance is not None,
            "monitor_thread_alive": monitor_thread.is_alive() if monitor_thread else False
        }
    }

    if service_initialized and monitor_instance and monitor_thread and monitor_thread.is_alive():
        health_info["message"] = "All components are working properly"
        return jsonify(health_info), 200
    else:
        health_info["message"] = "Service initialization failed or monitor not running"
        return jsonify(health_info), 503

def main():
    logger.info("Robot应用启动")
    # 确保必要目录存在
    try:
        from src.utils import load_config
        config = load_config()

        # 确保数据目录存在
        data_dir = config.get('paths', {}).get('forum_data_dir', 'data/forum_data')
        os.makedirs(data_dir, exist_ok=True)

        # 确保日志目录存在（已在logging_config.py中处理）
        log_dir = config.get('logging', {}).get('log_dir', 'logs')
        os.makedirs(log_dir, exist_ok=True)

        logger.info("目录检查完成")
    except Exception as e:
        # 如果配置加载失败，使用默认目录
        os.makedirs('data/forum_data', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        logger.info("目录检查完成")

    # 初始化数据
    if not lightrag_data_init():
        logger.error("LightRAG数据初始化失败，应用退出")
        return

    # 初始化服务
    if not initialize_service():
        logger.error("服务初始化失败，应用退出")
        return

    # 启动数据更新定时器
    if not lightrag_data_update_timer():
        logger.error("LightRAG数据更新定时器启动失败")

    # 启动Flask应用，端口可以根据需要修改
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == "__main__":
    main()
