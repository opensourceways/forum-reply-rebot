import re
import os
import json
from openai import OpenAI
from src.ForumBot.logging_config import main_logger as logger

class ImageProcessor:
    def __init__(self, config):
        self.config = config
        self.client = OpenAI(
            base_url=config['api']['base_url'],
            api_key=config['api']['api_key'],
            timeout=600
        )
        self.model_list = [
            config['image_processing']['model1'],
            config['image_processing']['model2'],
        ]

    def process_image_content(self, image_url):
        """
        处理单个图像，提取内容描述
        """
        if not image_url:
            return "无法获取图像内容"

        prompt = "请详细描述这张图片中的内容，这是一张技术论坛中的截图，可能包含错误日志、配置界面或代码片段。请提取图中的文字信息。只保留来自截图中的信息，不要加你的总结或推测。"

        # 调用多模态模型
        try:
            description = self._call_multimodel_model(image_url, prompt)
            return description
        except Exception as e:
            logger.error(f"Error processing image {image_url}: {e}")
            return image_url

    def _call_multimodel_model(self, image_url, prompt):
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
                    stream=False,
                    timeout=600
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
        return image_url

    def enhance_text_with_image_descriptions(self, text):
        """
        使用图像描述增强文本内容
        """
        images = []
        image_pattern = r'https?://[^\s]+?\.(?:png|jpg|jpeg|gif|bmp|webp)'
        image_urls = re.findall(image_pattern, text)
        for url in image_urls:
            images.append(url)

        enhanced_text = text

        # 为每个图像添加描述
        for img_url in images:
            logger.info(f"Processing image: {img_url}")

            # 获取图像描述
            description = self.process_image_content(img_url)

            # 将图像标签替换为包含描述的文本
            enhanced_description = f"[图片: {description}]"
            enhanced_text = enhanced_text.replace(img_url, enhanced_description)

        return enhanced_text

    def process_image_content_from_json_file(self, json_file_path):
        """
        从JSON文件中处理图像内容
        """
        # 读取json文件
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        images = []
        # 处理问题部分
        question_text = data.get('question', '')
        if question_text:
            enhanced_question = self.enhance_text_with_image_descriptions(question_text)
            data['question'] = enhanced_question

        # 处理回答部分
        reply_posts = data.get('reply_posts', [])
        for post in reply_posts:
            post_text = post.get('text', '')
            if post_text:
                enhanced_text = self.enhance_text_with_image_descriptions(post_text)
                post['text'] = enhanced_text

        # 将处理收的数据拼接回原文本然后写回原文件
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


    def process_image_from_files(self, file_list_path):
        """
        处理所有需上传文件中的图片
        """
        logger.info(f"开始处理图片")

        # 检查new_rag文件是否存在
        if not os.path.exists(file_list_path):
            logger.warning(f"new_rag文件不存在: {file_list_path}")
            return

        # 从new_rag文件中读取文件名列表
        with open(file_list_path, 'r', encoding='utf-8') as f:
            file_paths = [line.strip() for line in f.readlines() if line.strip()]

        # 只处理new_rag文件中记录的JSON文件
        for file_path in file_paths:
            full_file_path = f"{self.config['lightrag_paths']['rag_data_dir']}/{file_path}"
            # 检查文件是否存在
            if os.path.exists(full_file_path):
                self.process_image_content_from_json_file(full_file_path)
            else:
                logger.warning(f"文件不存在: {full_file_path}")

        logger.info(f"图片处理完成")