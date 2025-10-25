# src/token_tracker.py
import time
from datetime import datetime
from .logging_config import main_logger as logger

class TokenTracker:
    """
    Token使用量跟踪器
    """
    def __init__(self):
        self.token_usage = {}

    def reset_usage(self, topic_id):
        """
        重置指定topic的token使用量统计
        """
        self.token_usage[topic_id] = {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'model_calls': 0
        }
        logger.info(f"已重置topic {topic_id} 的token统计")

    def add_usage(self, topic_id, prompt_tokens=0, completion_tokens=0, total_tokens=0):
        """
        累加指定topic的token使用量
        """
        if topic_id not in self.token_usage:
            self.reset_usage(topic_id)

        self.token_usage[topic_id]['prompt_tokens'] += prompt_tokens
        self.token_usage[topic_id]['completion_tokens'] += completion_tokens
        self.token_usage[topic_id]['total_tokens'] += total_tokens
        self.token_usage[topic_id]['model_calls'] += 1

        logger.info(f"Topic {topic_id} token使用量更新: "
                    f"prompt={self.token_usage[topic_id]['prompt_tokens']}, "
                    f"completion={self.token_usage[topic_id]['completion_tokens']}, "
                    f"total={self.token_usage[topic_id]['total_tokens']}")

    def get_usage(self, topic_id):
        """
        获取指定topic的token使用量统计
        """
        return self.token_usage.get(topic_id, {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'model_calls': 0
        })

    def get_all_usage(self):
        """
        获取所有topic的token使用量统计
        """
        return self.token_usage

# 创建全局实例
token_tracker = TokenTracker()
