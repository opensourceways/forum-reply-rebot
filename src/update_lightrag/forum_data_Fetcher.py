import requests
from bs4 import BeautifulSoup
import re
import json
import os
import time
from src.ForumBot.logging_config import main_logger as logger

class ForumDataFetcher:
    def __init__(self, config):
        self.config = config

    def fetch_one_page_data(self, page):
        """
        获取单页论坛数据
        """
        params = {
            'page': page,
            'no_definitions': True,
        }

        verify_ssl = self.config.get('forum', {}).get('verify_ssl', True)
        response = requests.get(
            f"{self.config['forum']['base_url']}/latest.json",
            params=params,
            timeout=10,
            verify=verify_ssl
        )
        response.raise_for_status()
        return response.json()

    def extract_posts_data(self, posts_data):
        """
        提取帖子数据
        """
        posts = []
        for post in posts_data:
            user_name = post['name']
            topic_closed = post['topic_accepted_answer']
            is_solution = post['accepted_answer']
            body_cooked = post['cooked']
            soup = BeautifulSoup(body_cooked, 'html.parser')

            text_content = soup.get_text()
            text_content = re.sub(r'\n{3,}', '\n\n', text_content)

            text_content = text_content.strip()

            links = []
            for link in soup.find_all('a', href=True):
                links.append(link['href'])

            if links:
                text = f'content: {text_content}\nlinks: {", ".join(links)}'
            else:
                text = text_content

            post_url = post['post_url']
            posts.append({
                'user_name': user_name,
                'topic_closed': topic_closed,
                'is_solution': is_solution,
                'post_url': post_url,
                'text': text,
            })
        return posts

    def get_one_topic_content(self, topic):
        """
        获取单条话题内容
        """
        topic_id = topic['id']
        topic_title = topic['title']
        topic_url = f"{self.config['forum']['base_url']}/t/{topic_id}.json"

        safe_title = re.sub(r'[^\w\s-]', '', topic_title).strip()
        safe_title = re.sub(r'[-\s]+', '_', safe_title)  # Replace spaces and hyphens with underscores
        max_title_length = 140  # 限制文件名长度
        if len(safe_title) > max_title_length:
            safe_title = safe_title[:max_title_length].rstrip('_')
        file_name = f'{safe_title}_{topic_id}_topic.json'
        params = {
            'track_visit': True,
            'forceLoad': True,
        }
        verify_ssl = self.config.get('forum', {}).get('verify_ssl', True)
        try:
            response = requests.get(
                topic_url,
                params=params,
                timeout=10,
                verify=verify_ssl
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"获取话题内容失败（话题ID {topic_id}）: {e}")
            return None

        post_json_data = response.json()
        question = ''
        best_answer_url = ''
        topic_user_name = ''
        reply_posts = []
        if post_json_data.get('post_stream'):
            post_data = post_json_data['post_stream']['posts']
            posts = self.extract_posts_data(post_data)
            question = f'{topic_title} - {posts[0]["text"]}' if posts else ''
            topic_user_name = posts[0]['user_name']
            reply_posts = posts[1:] if len(posts) > 1 else []
            for post in reply_posts:
                if post['is_solution']:
                    best_answer_url = post['post_url']
                    break

        write_data = {
            'topic_id': topic_id,
            'question': question,
            'topic_user_name': topic_user_name,
            'best_answer_url': best_answer_url,
            'reply_posts': reply_posts,
        }

        # Ensure the directory exists
        rag_dir = self.config['lightrag_paths']['rag_data_dir']
        try:
            if not os.path.exists(rag_dir):
                os.makedirs(rag_dir)
        except OSError as e:
            logger.error(f"创建目录失败 {rag_dir}: {e}")
            raise

        with open(f'{rag_dir}/{file_name}', 'w', encoding='utf-8') as f:
            json.dump(write_data, f, ensure_ascii=False, indent=4)

        return write_data

    def extract_one_page_topic_data(self, page):
        """提取单页论坛话题数据"""
        data = self.fetch_one_page_data(page)
        topics = data.get('topic_list', {}).get('topics', [])

        for topic in topics:
            self.get_one_topic_content(topic)
            time.sleep(0.5)

        return topics