# src/standalone_api.py
import random
import os
import sys
# 获取当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录
project_root = os.path.join(current_dir, '..')
# 添加项目根目录到Python路径
sys.path.insert(0, project_root)

from flask import Flask, request, jsonify
from src.ForumBot.ai_processor import AIProcessor
from src.ForumBot.forum_client import ForumClient
from src.ForumBot.data_processor import DataProcessor
from src.ForumBot.utils import load_config
from src.ForumBot.logging_config import main_logger as logger
from src.ForumBot.token_tracker import token_tracker


def find_config_file():
    """
    查找配置文件路径
    """
    # 尝试几种可能的配置文件路径
    possible_paths = [
        os.path.join(project_root, 'config', 'config.yaml'),
        os.path.join(os.getcwd(), 'config', 'config.yaml'),
        'config/config.yaml',
        '../config/config.yaml'
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    # 如果找不到配置文件，返回默认路径
    return os.path.join(project_root, 'config', 'config.yaml')


def create_standalone_api(config_file=None):
    """
    创建独立的API服务
    """
    app = Flask(__name__)

    # 如果没有指定配置文件，则尝试查找
    if config_file is None:
        config_file = find_config_file()

    # 初始化组件
    config = load_config(config_file)
    ai_processor = AIProcessor(config)
    forum_client = ForumClient(config)
    data_processor = DataProcessor(config)

    @app.route('/health', methods=['GET'])
    def health_check():
        """健康检查端点"""
        return jsonify({'status': 'healthy', 'service': 'ForumBot Standalone API'})

    @app.route('/process_question', methods=['POST'])
    def process_question():
        """处理用户问题的API端点"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': '缺少请求数据'}), 400

            title = data.get('title', '')
            user_question = data.get('question', '')

            if not user_question:
                return jsonify({'error': '缺少问题内容'}), 400

            # 生成六位随机整数作为topic_id
            topic_id = random.randint(10000000, 99999999)
            topic_id_str = str(topic_id)
            logger.info(f"为用户查询生成随机topic_id: {topic_id}")
            token_tracker.reset_usage(topic_id_str)

            # 1. 生成摘要
            logger.info(f"正在为问题 {topic_id} 生成摘要...")
            summary = ai_processor.summarize_text(title, user_question, topic_id_str)
            logger.info(f"问题 {topic_id} 摘要: {summary}")

            # 2. 基于摘要搜索相关主题
            logger.info(f"正在为问题 {topic_id} 搜索相关主题...")
            search_results = forum_client.search_related_topics(summary, topic_id_str)

            # 3. 构造检索结果格式
            retrieval_result = {
                'topic_id': topic_id_str,
                'related_docs': ''
            }

            # 4. 格式化搜索结果
            if search_results:
                logger.info(f"问题 {topic_id} 搜索到 {len(search_results)} 个相关主题")
                retrieval_result['related_docs'] = data_processor.format_search_results_for_prompt(
                    retrieval_result, search_results
                )
            else:
                logger.info(f"问题 {topic_id} 未搜索到相关主题")

            # 5. 调用大模型生成回答
            logger.info(f"正在为问题 {topic_id} 调用大模型生成回答...")
            answer = ai_processor.call_large_model(
                retrieval_result['related_docs'],
                title,
                user_question,
                topic_id_str
            )

            # 6. 添加AI生成内容提示
            answer_with_notice = "答案内容由AI生成，仅供参考：\n" + answer

            # 7. 获取token使用量统计
            token_usage = token_tracker.get_usage(topic_id_str)

            logger.info(f"问题 {topic_id} 回答已生成(Token使用: 总计{token_usage['total_tokens']})")


            return jsonify({
                'success': True,
                'topic_id': topic_id,
                'summary': summary,
                'answer': answer_with_notice,
                'token_usage': token_usage
            })

        except Exception as e:
            logger.error(f"API处理请求时发生错误: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    return app

def run_standalone_api(host='0.0.0.0', port=5085, config_file='config/config.yaml'):
    """
    运行独立的API服务
    """
    app = create_standalone_api(config_file)
    app.run(host=host, port=port, debug=False)

if __name__ == '__main__':
    # 可以直接运行此文件启动API服务
    run_standalone_api()
