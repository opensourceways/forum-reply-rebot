from openai import OpenAI, APIError, APITimeoutError, InternalServerError
import time
from .logging_config import main_logger as logger
from .token_tracker import token_tracker

class AIProcessor:
    def __init__(self, config):
        self.config = config
        self.client = OpenAI(
            base_url=config['api']['base_url'],
            api_key=config['api']['api_key']
        )

    def summarize_text(self, title, user_question, topic_id, max_length=None):
        """
        使用大模型总结问题
        """
        if max_length is None:
            max_length = self.config['summary']['max_length']


        prompt_template = """
        - Role: 论坛问题总结专家
        - Background: 用户需要从复杂的论坛问题贴中快速提取核心问题，以便进行高效的管理和回复。
        - Profile: 你是一位经验丰富的论坛管理员，擅长从大量文本中提炼关键信息，能够迅速抓住用户问题的核心。
        - Skills: 你具备高效的文本分析能力、信息提炼能力和简洁表达能力，能够快速总结用户问题。
        - Goals: 从给定的论坛问题贴（包含标题、正文和问题）中，用一句话总结用户问题，且不超过100字符。
        - Constrains: 总结必须准确、简洁，不超过100字符，且能完整表达用户问题的核心。
        - OutputFormat: 一句话总结，不超过100字符。
        - Input: 
        Title：{}
        Body + Question:{}
        - Workflow:
          1. 仔细阅读论坛问题贴的标题、正文和问题部分。
          2. 提炼出用户问题的核心内容，去除冗余信息。
          3. 用简洁的语言总结问题，确保不超过100字符。
          4. 结尾不要输出标点符号。
        """

        text = prompt_template.format(title, user_question)

        try:
            response = self.client.chat.completions.create(
                model=self.config['api']['model_name'],
                messages=[
                    {"role": "user", "content": f"{text}"}
                ],
                stream=False
            )
            summary = response.choices[0].message.content.strip()
            # 确保摘要不超过指定字符数
            if len(summary) > max_length:
                summary = summary[:max_length]
                # 如果提供了topic_id，则记录token使用量
            if topic_id and hasattr(response, 'usage'):
                token_tracker.add_usage(
                    topic_id,
                    prompt_tokens=response.usage.prompt_tokens if hasattr(response.usage, 'prompt_tokens') else 0,
                    completion_tokens=response.usage.completion_tokens if hasattr(response.usage,
                                                                                  'completion_tokens') else 0,
                    total_tokens=response.usage.total_tokens if hasattr(response.usage, 'total_tokens') else 0
                )

            return summary
        except Exception as e:
            logger.error(f"生成摘要时出错: {e}")
            return "摘要生成失败"

    def call_large_model(self, text, title, user_question, topic_id, max_retries=3):
        """
        调用大模型处理文本
        """
        query = f"{title}:{user_question}"
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.config['api']['model_name'],
                    messages=[
                        {
                            'role': 'system',
                            'content': text
                        },
                        {
                            'role': 'user',
                            'content': query
                        }
                    ],
                    stream=False,
                    timeout=600
                )
                # 如果提供了topic_id，则记录token使用量
                if topic_id and hasattr(response, 'usage'):
                    token_tracker.add_usage(
                        topic_id,
                        prompt_tokens=response.usage.prompt_tokens if hasattr(response.usage, 'prompt_tokens') else 0,
                        completion_tokens=response.usage.completion_tokens if hasattr(response.usage,
                                                                                      'completion_tokens') else 0,
                        total_tokens=response.usage.total_tokens if hasattr(response.usage, 'total_tokens') else 0
                    )
                return response.choices[0].message.content
            except (APITimeoutError, InternalServerError, APIError) as e:
                logger.warning(f"第{attempt + 1}次尝试失败: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return f"处理失败: {str(e)}"
            except Exception as e:
                return f"未知错误: {str(e)}"

        return "处理失败: 达到最大重试次数"
