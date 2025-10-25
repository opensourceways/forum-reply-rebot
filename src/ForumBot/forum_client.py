import requests
import json
from datetime import datetime
import re
from .data_processor import fetch_all_forum_topics,fetch_topic_details
from .logging_config import main_logger as logger

class ForumClient:
    def __init__(self, config):
        self.config = config

    # 在 forum_client.py 的 ForumClient 类中添加方法
    def fetch_topic_details(self, topic_id):
        """
        根据 topic_id 获取单个帖子的详细内容。
        """
        return fetch_topic_details(topic_id, self.config)

    def fetch_all_forum_topics(self):
        """
        获取所有论坛主题
        """
        return fetch_all_forum_topics()

    def reply_to_topic(self, topic_id, reply_content):
        """
        回复指定的论坛主题
        """
        logger.info(f"正在回复主题 {topic_id}")
        headers = {
            "Content-Type": "application/json",
            "Api-Key": self.config['posts']['api_key'],
            "Api-Username": self.config['posts']['api_username']
        }

        payload = {
            "topic_id": topic_id,
            "raw": reply_content
        }

        try:
            response = requests.post(
                f"{self.config['posts']['base_url']}/posts.json",
                headers=headers,
                data=json.dumps(payload)
            )

            if response.status_code == 200:
                logger.info(f"主题 {topic_id} 回复成功")
                return {
                    "success": True,
                    "data": response.json()
                }
            else:
                logger.error(f"主题 {topic_id} 回复失败，状态码: {response.status_code}")
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error_message": response.text
                }
        except Exception as e:
            logger.error(f"主题 {topic_id} 回复请求发送失败: {e}")
            return {
                "success": False,
                "error": f"请求发送失败: {e}"
            }

    def search_related_topics(self, keyword, query_id, max_results=None):
        """
        搜索相关主题
        """
        if max_results is None:
            max_results = self.config['search']['default_page_size']

        base_url = self.config['search']['base_url']
        endpoint = self.config['search']['endpoint']
        url = f"{base_url}{endpoint}"

        headers = {
            "source": self.config['search']['source']
        }

        # 截断过长的关键字
        if len(keyword) > self.config['search']['max_keyword_length']:
            logger.warning(f"关键字太长，截断：{keyword}")
            keyword = keyword[:self.config['search']['max_keyword_length']]

        data = {
            "keyword": keyword,
            "lang": "zh",
            "type": "",
            "filter": [{}],
            "pageSize": max_results
        }

        try:
            response = requests.post(url, headers=headers, json=data)

            if response.status_code == 200:
                result = response.json()
                records = result.get('obj', {}).get('records', [])

                # 过滤掉当前帖子本身并去除HTML标签
                filtered_records = []
                for record in records:
                    record['title'] = self._remove_html_tags(record.get('title', ''))
                    record['textContent'] = self._remove_html_tags(record.get('textContent', ''))
                    filtered_records.append(record)

                return filtered_records
            else:
                logger.error(f"搜索请求失败，状态码：{response.status_code}，ID: {query_id}")
                return []
        except Exception as e:
            logger.error(f"搜索过程中发生错误，搜索内容为: {keyword}")
            logger.error(f"搜索过程中发生错误: {e}")
            return []

    def retrieve_documents_for_topic(self, topic):
        """
        为单个帖子检索相关文档
        """
        topic_id = topic['id']
        title = topic['title']
        user_question = topic['user_question']

        # 构造查询内容：将标题和用户问题拼接
        query = f"{title} {user_question}"

        logger.info(f"正在为帖子 {topic_id} 检索相关文档...")
        related_docs = self._get_response_data(query)

        result = {
            'topic_id': topic_id,
            'related_docs': related_docs
        }

        if related_docs:
            logger.info(f"帖子 {topic_id} 检索到相关文档")
        else:
            logger.info(f"帖子 {topic_id} 未检索到相关文档")

        return result

    def _get_response_data(self, query):
        """
        发送查询请求并返回响应数据
        """
        base_url = self.config['retrieval']['base_url']
        endpoint = self.config['retrieval']['query_endpoint']
        url = f"{base_url}{endpoint}"

        payload = {
            "query": query,
            "only_need_prompt": self.config['retrieval']['only_need_prompt'],
            "top_k": self.config['retrieval']['top_k'],
            "chunk_top_k": self.config['retrieval']['chunk_top_k'],
            "enable_rerank": self.config['retrieval']['enable_rerank'],
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("response")
        except requests.RequestException as e:
            logger.error(f"请求错误: {e}")
            return None
        except ValueError as e:
            logger.error(f"JSON解析错误: {e}")
            return None

    def _remove_html_tags(self, text):
        """
        去除HTML标签
        """
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text)
