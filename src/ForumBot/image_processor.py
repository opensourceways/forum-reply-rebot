# src/image_processor.py
import re
import base64
import requests
from urllib.parse import urljoin
from openai import OpenAI
from .logging_config import main_logger as logger
from .token_tracker import token_tracker

class ImageProcessor:
    def __init__(self, config):
        self.config = config
        self.client = OpenAI(
            base_url=config['api']['base_url'],
            api_key=config['api']['api_key']
        )
        self.model_list = [
            config['image_processing']['model1'],
            config['image_processing']['model2'],
            config['image_processing']['model3'],
        ]

    def extract_image_info_from_text(self, text):
        """
        从文本中提取图像信息
        """
        img_pattern = r'\[img: \((.*?)\)\]'
        matches = re.findall(img_pattern, text)
        base_url = self.config.get('image_processing', {}).get('base_url', 'https://discuss.openubmc.cn')

        images = []
        for match in matches:
            # 处理相对路径和绝对路径
            if match.startswith('http'):
                img_url = match
            else:
                img_url = urljoin(base_url, match)

            images.append({
                'url': img_url,
                'original_tag': f'[img: ({match})]'
            })

        return images

    def process_image_content(self, image_url, context="",topic_id=None):
        """
        处理单个图像，提取内容描述
        """
        # 检查是否为用户头像
        if 'user_avatar' in image_url:
            return "USER_AVATAR"  # 特殊标记，表示这是用户头像

        if not image_url:
            return "无法获取图像内容"

        # 根据上下文设置不同的提示词
        if "user_question" in context:
            prompt = "请详细描述这张图片中的内容，这是一张技术论坛中的截图，可能包含错误日志、配置界面或代码片段。请提取图中的文字信息。只保留来自截图中的信息，不要加你的总结或推测。"
        elif "best_answer" in context:
            prompt = "请分析这张图片中的技术内容，这可能包含解决方案截图、配置示例或日志分析结果。请总结关键信息。"
        else:
            prompt = "请描述这张技术图片的内容，重点关注其中的技术信息和关键细节。"

        # 调用多模态模型
        try:
            description = self._call_multimodal_model(image_url, prompt,topic_id)
            return description
        except Exception as e:
            logger.error(f"Error processing image {image_url}: {e}")
            return "图像内容分析失败"

    def _call_multimodal_model(self, image_url, prompt, topic_id= None):
        """
        调用多模态模型分析图像内容
        """
        # 首先尝试默认模型
        models = self.model_list

        for i, model in enumerate(models):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{
                        'role': 'user',
                        'content': [{
                            'type': 'text',
                            'text': prompt,
                        }, {
                            'type': 'image_url',
                            'image_url': {
                                'url': image_url,
                            },
                        }],
                    }],
                    stream=False
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
            except Exception as e:
                logger.error(f"Error calling model {model}: {e}")
                # 如果是最后一个模型，抛出异常
                if i == len(models) - 1:
                    raise e
                else:
                    logger.info(f"Retrying with next model: {models[i + 1]}")

        # 这行代码实际上不会执行到，因为上面的循环会处理所有情况
        return "图像内容分析失败"

    def enhance_text_with_image_descriptions(self, text, context="", topic_id=None):
        """
        使用图像描述增强文本内容
        """
        # 提取图像信息
        images = self.extract_image_info_from_text(text)

        enhanced_text = text

        # 为每个图像添加描述
        for img_info in images:
            img_url = img_info['url']
            original_tag = img_info['original_tag']

            logger.info(f"Processing image: {img_url}")

            # 获取图像描述
            description = self.process_image_content(img_url, context, topic_id)

            # 处理用户头像的情况
            if description == "USER_AVATAR":
                # 直接删除用户头像标签
                enhanced_text = enhanced_text.replace(original_tag, "")
            else:
                # 将图像标签替换为包含描述的文本
                enhanced_description = f"[图片: {description}]"
                enhanced_text = enhanced_text.replace(original_tag, enhanced_description)

        return enhanced_text
