# api_main.py
import argparse
import os
import sys

# 添加src目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, 'src'))

from standalone_api import run_standalone_api
from src.ForumBot.logging_config import main_logger as logger

def main():
    parser = argparse.ArgumentParser(description='ForumBot 独立API服务')
    parser.add_argument('--host', default='0.0.0.0', help='API服务主机地址')
    parser.add_argument('--port', type=int, default=5085, help='API服务端口')
    parser.add_argument('--config', default=None, help='配置文件路径')

    args = parser.parse_args()

    logger.info(f"正在启动ForumBot独立API服务于 {args.host}:{args.port}")
    if args.config:
        logger.info(f"使用配置文件: {args.config}")
    else:
        logger.info("自动查找配置文件")

    try:
        run_standalone_api(host=args.host, port=args.port, config_file=args.config)
    except KeyboardInterrupt:
        logger.info("API服务已停止")
    except Exception as e:
        logger.error(f"API服务启动失败: {e}")

if __name__ == "__main__":
    main()
