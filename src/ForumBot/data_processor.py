import csv
import json
import os
from datetime import datetime
import time
import requests
from bs4 import BeautifulSoup
from .logging_config import main_logger as logger
import pytz
import psycopg2
from psycopg2.extras import Json, execute_values
from .image_processor import ImageProcessor
import re
import pandas as pd
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetch_topic_details(topic_id, config=None):
    """
    根据 topic_id 获取单个帖子的详细内容。

    参数:
        topic_id (int): 帖子的 ID。

    返回:
        dict or None: 如果请求成功，返回包含详细内容的字典；否则返回 None。
    """
    if config is None:
        from src.utils import load_config
        config = load_config()

        # 从配置中获取论坛基础URL
    base_url = config.get('forum', {}).get('base_url', 'https://openubmc-discussion.test.osinfra.cn')
    url = f"{base_url}/t/{topic_id}.json"
    # 从配置中获取请求延迟时间
    request_delay = config.get('forum', {}).get('request_delay', 0.1)
    verify_ssl = config.get('forum', {}).get('verify_ssl', True)
    try:
        response = requests.get(url, verify=verify_ssl)
        response.raise_for_status()  # 检查响应状态码是否为 2xx
        time.sleep(request_delay)  # 每次请求后暂停0.1秒
        return response.json()  # 返回解析后的 JSON 数据
    except requests.exceptions.RequestException as e:
        # 如果是 429 错误，提示用户增加请求间隔或使用代理
        logger.error(f"请求帖子 {topic_id} 时出错: {e}")
        return None


def fetch_all_forum_topics(sort="newest", config=None):
    # 如果没有传入配置，则加载默认配置
    if config is None:
        from src.utils import load_config
        config = load_config()

    base_url = config.get('forum', {}).get('base_url', 'https://openubmc-discussion.test.osinfra.cn') + "/latest.json"
    page = 0
    all_topics = []

    # 获取过滤条件
    required_tag = config['monitor']['required_tag']
    # 获取SSL验证设置
    verify_ssl = config.get('forum', {}).get('verify_ssl', True)

    # 设置过滤日期 (2025年9月1日)
    cutoff_date = datetime.strptime(config['monitor']['topic_cutoff_date'], '%Y-%m-%d')
    cutoff_date = pytz.utc.localize(cutoff_date)  # 设置为UTC时区

    while True:
        params = {
            "no_definitions": "true",
            "page": page
        }

        try:
            response = requests.get(base_url, params=params, verify=verify_ssl)
            response.raise_for_status()
            data = response.json()

            topic_list = data.get("topic_list", {})
            topics = topic_list.get("topics", [])

            if not topics:
                logger.info(f"第 {page} 页没有更多帖子，结束爬取。")
                break
            # 对当前页的帖子进行过滤
            filtered_topics = []
            for topic in topics:
                # 检查标签是否包含所需标签
                topic_tags = topic.get('tags', [])
                if isinstance(topic_tags, list):
                    topic_tags_str = ','.join(topic_tags)
                else:
                    topic_tags_str = str(topic_tags)

                if required_tag not in topic_tags_str:
                    continue  # 如果不包含所需标签，则跳过

                # 检查创建时间是否在指定日期之后
                created_at_str = topic.get('created_at', '')
                if created_at_str:
                    try:
                        # 解析创建时间
                        created_at = datetime.strptime(created_at_str, '%Y-%m-%dT%H:%M:%S.%fZ')
                        created_at = pytz.utc.localize(created_at)  # 设置为UTC时区

                        # 只处理创建时间在指定日期之后的帖子
                        if created_at >= cutoff_date:
                            filtered_topics.append(topic)
                    except ValueError:
                        # 如果日期解析失败，默认添加该帖子
                        logger.warning(f"无法解析帖子 {topic.get('id')} 的创建时间: {created_at_str}")
                        filtered_topics.append(topic)

            all_topics.extend(filtered_topics)

            logger.info(f"已获取第 {page} 页的 {len(filtered_topics)} 个符合条件的帖子。")

            page += 1

        except requests.exceptions.RequestException as e:
            logger.error(f"请求第 {page} 页时出错: {e}")
            break

    return all_topics


def process_html_content_with_image_links(html_content):
    """
    处理带有HTML标记的数据，保留自然语言文本，并将图片链接保留在文本中相应位置

    Args:
        html_content (str): 包含HTML标记的原始内容

    Returns:
        str: 处理后的文本，包含自然语言文本和嵌入的图片链接
    """
    if pd.isna(html_content) or not isinstance(html_content, str):
        return html_content  # 或者返回空字符串 ""，根据需求决定
    # 解析HTML内容
    soup = BeautifulSoup(html_content, 'html.parser')

    # 创建副本以避免修改原始soup
    soup_copy = BeautifulSoup(str(soup), 'html.parser')

    # 替换img标签为文本格式的图片链接
    img_tags = soup_copy.find_all('img')
    for img in img_tags:
        img_src = img.get('src')
        if img_src:
            # 将图片标签替换为只包含链接的文本格式
            img.replace_with(f"[img: ({img_src})]")

    # 替换lightbox链接为文本格式
    lightbox_links = soup_copy.find_all('a', class_='lightbox')
    for link in lightbox_links:
        href = link.get('href')
        if href:
            # 将链接替换为只包含链接的文本格式
            link.replace_with(f"[img: ({href})]")

    # 提取处理后的文本内容
    text_content = soup_copy.get_text(strip=False)
    # 清理多余的空白字符和换行符
    text_content = re.sub(r'\n+', '\n', text_content).strip()

    # 处理上传的图片标记 (如 upload://...)
    upload_images = re.findall(r'\(upload://[^\)]+\)', text_content)

    return text_content

class DataProcessor:
    def __init__(self, config):
        self.config = config
        # 不再在初始化时建立数据库连接
        self.db_conn = None
        self.image_processor = ImageProcessor(config)

    def _get_db_connection(self):
        """
        获取数据库连接，按需建立连接
        """
        try:
            # 从配置中获取数据库参数
            db_params = {
                'host': self.config['database']['host'],
                'port': self.config['database']['port'],
                'database': self.config['database']['database'],
                'user': self.config['database']['user'],
                'password': self.config['database']['password'],
                'sslmode': self.config['database']['sslmode']
            }
            conn = psycopg2.connect(**db_params)
            logger.debug("数据库连接已建立")
            return conn
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            return None

    def _close_db_connection(self, conn):
        """
        关闭数据库连接
        """
        if conn:
            try:
                conn.close()
                logger.debug("数据库连接已关闭")
            except Exception as e:
                logger.error(f"关闭数据库连接时出错: {e}")

    def get_processed_topic_ids(self):
        """
        获取已处理的帖子ID列表
        """
        query = "SELECT DISTINCT id FROM processed_forum_topics"
        conn = self._get_db_connection()
        if not conn:
            logger.error("无法建立数据库连接")
            return

        try:
            cursor = conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            logger.info("获取id成功")
            return [row[0] for row in results]


        except Exception as e:
            logger.error(f"获取id成功时出错")

        finally:
            self._close_db_connection(conn)

    def get_unprocessed_topics(self, processed_ids):
        """
        获取在 forum_topics 表中存在但 processed_forum_topics 表中不存在的帖子 IDs
        """
        conn = self._get_db_connection()
        if not conn:
            logger.error("无法建立数据库连接")
            return []

        try:
            cursor = conn.cursor()

            if not processed_ids:
                # 如果没有已处理的帖子，则所有 forum_topics 表中的帖子都是未处理的
                query = "SELECT id FROM forum_topics"
                cursor.execute(query)
            else:
                # 使用占位符构建查询
                placeholders = ','.join(['%s'] * len(processed_ids))
                query = f"SELECT id FROM forum_topics WHERE id NOT IN ({placeholders})"
                cursor.execute(query, tuple(processed_ids))

            results = cursor.fetchall()
            unprocessed_ids = [row[0] for row in results]

            cursor.close()
            logger.info(f"找到 {len(unprocessed_ids)} 个未处理的帖子")
            return unprocessed_ids

        except Exception as e:
            logger.error(f"获取未处理帖子IDs时出错: {e}")
            return []
        finally:
            self._close_db_connection(conn)

    def create_tables(self):
        """
        创建数据库表
        """
        conn = self._get_db_connection()
        if not conn:
            logger.error("无法建立数据库连接")
            return

        try:
            cursor = conn.cursor()

            # 创建原始论坛主题表
            cursor.execute("""
                   CREATE TABLE IF NOT EXISTS forum_topics (
                       id INTEGER PRIMARY KEY,
                       title TEXT,
                       user_question TEXT,
                       best_answer TEXT,
                       tags TEXT,
                       replies JSONB,
                       created_at TIMESTAMP,
                       llm_answer TEXT,
                       summary_question TEXT
                   )
               """)

            # 创建处理后的论坛主题表
            cursor.execute("""
                   CREATE TABLE IF NOT EXISTS processed_forum_topics (
                       id INTEGER PRIMARY KEY,
                       title TEXT,
                       user_question TEXT,
                       best_answer TEXT,
                       tags TEXT,
                       replies JSONB,
                       created_at TIMESTAMP,
                       llm_answer TEXT,
                       summary_question TEXT
                   )
               """)

            # 创建搜索结果表（将results中的10个元素拆分成10个列）
            cursor.execute("""
                             CREATE TABLE IF NOT EXISTS forum_search_results (
                                 id SERIAL PRIMARY KEY,
                                 topic_id INTEGER,
                                 search_keyword TEXT,
                                 search_timestamp TIMESTAMP,
                                 total_results INTEGER,
                                 displayed_results INTEGER,
                                 result_1 JSONB,
                                 result_2 JSONB,
                                 result_3 JSONB,
                                 result_4 JSONB,
                                 result_5 JSONB,
                                 result_6 JSONB,
                                 result_7 JSONB,
                                 result_8 JSONB,
                                 result_9 JSONB,
                                 result_10 JSONB
                             )
                         """)

            # 创建检索结果表
            cursor.execute("""
                              CREATE TABLE IF NOT EXISTS forum_retrieval_results (
                                  id SERIAL PRIMARY KEY,
                                  topic_id INTEGER,
                                  related_docs TEXT,
                                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                              )
                          """)
            # 创建token消耗统计表
            cursor.execute("""
                                      CREATE TABLE IF NOT EXISTS consume_tokens_topic (
                                          id SERIAL PRIMARY KEY,
                                          topic_id INTEGER,
                                          prompt_tokens INTEGER DEFAULT 0,
                                          completion_tokens INTEGER DEFAULT 0,
                                          total_tokens INTEGER DEFAULT 0,
                                          model_calls INTEGER DEFAULT 0,
                                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                                      )
                                  """)

            conn.commit()
            cursor.close()
            logger.info("数据库表创建成功")
        except Exception as e:
            logger.error(f"创建数据库表时出错: {e}")
            conn.rollback()
        finally:
            self._close_db_connection(conn)

    def append_to_db(self, data, table_name='forum_topics'):
        """
        将数据插入到数据库表中
        """
        if not data:
            logger.info("没有数据需要插入")
            return

        conn = self._get_db_connection()
        if not conn:
            logger.error("无法建立数据库连接")
            return

        try:
            cursor = conn.cursor()

            # 准备插入数据
            insert_data = []
            for row in data:
                # 处理 replies 字段
                replies = row.get('replies', [])
                if isinstance(replies, list):
                    replies_json = Json(replies)
                else:
                    replies_json = replies

                insert_data.append((
                    int(row['id']),
                    row.get('title', ''),
                    row.get('user_question', ''),
                    row.get('best_answer', ''),
                    row.get('tags', ''),
                    replies_json,
                    row.get('created_at'),
                    row.get('llm_answer', ''),
                    row.get('summary_question', '')
                ))

            # 批量插入数据
            insert_query = f"""
                   INSERT INTO {table_name} 
                   (id, title, user_question, best_answer, tags, replies, created_at, llm_answer, summary_question)
                   VALUES %s
                   ON CONFLICT (id) 
                   DO UPDATE SET
                       title = EXCLUDED.title,
                       user_question = EXCLUDED.user_question,
                       best_answer = EXCLUDED.best_answer,
                       tags = EXCLUDED.tags,
                       replies = EXCLUDED.replies,
                       created_at = EXCLUDED.created_at,
                       llm_answer = EXCLUDED.llm_answer,
                       summary_question = EXCLUDED.summary_question
               """

            execute_values(cursor, insert_query, insert_data)
            conn.commit()
            cursor.close()

            logger.info(f"成功插入/更新 {len(data)} 条数据到 {table_name} 表")
        except Exception as e:
            logger.error(f"插入数据到数据库时出错: {e}")
            conn.rollback()
        finally:
            self._close_db_connection(conn)

    def save_search_results_to_db(self, topic_id, search_results, search_keyword):
        """
        将搜索结果保存到数据库
        """
        conn = self._get_db_connection()
        if not conn:
            logger.error("无法建立数据库连接")
            return

        try:
            cursor = conn.cursor()

            # 限制结果数量为10个
            limited_results = search_results[:10]

            # 将结果拆分成10个列，不足的用NULL填充
            result_columns = [None] * 10
            for i, result in enumerate(limited_results):
                result_columns[i] = Json(result)

            # 插入数据
            insert_query = """
                   INSERT INTO forum_search_results 
                   (topic_id, search_keyword, search_timestamp, total_results, displayed_results, 
                    result_1, result_2, result_3, result_4, result_5, 
                    result_6, result_7, result_8, result_9, result_10)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               """

            timestamp = datetime.now()

            cursor.execute(insert_query, (
                topic_id,
                search_keyword,
                timestamp,
                len(search_results),
                len(limited_results),
                result_columns[0],
                result_columns[1],
                result_columns[2],
                result_columns[3],
                result_columns[4],
                result_columns[5],
                result_columns[6],
                result_columns[7],
                result_columns[8],
                result_columns[9]
            ))

            conn.commit()
            cursor.close()
            logger.info(f"主题 {topic_id} 的搜索结果已保存到数据库")
        except Exception as e:
            logger.error(f"保存搜索结果到数据库时出错: {e}")
            conn.rollback()
        finally:
            self._close_db_connection(conn)

    def save_retrieval_results_to_db(self, topic_id, related_docs):
        """
        将检索结果保存到数据库
        """
        conn = self._get_db_connection()
        if not conn:
            logger.error("无法建立数据库连接")
            return

        try:
            cursor = conn.cursor()

            # 插入数据
            insert_query = """
                   INSERT INTO forum_retrieval_results 
                   (topic_id, related_docs)
                   VALUES (%s, %s)
               """

            cursor.execute(insert_query, (
                topic_id,
                related_docs
            ))

            conn.commit()
            cursor.close()
            logger.info(f"主题 {topic_id} 的检索结果已保存到数据库")
        except Exception as e:
            logger.error(f"保存检索结果到数据库时出错: {e}")
            conn.rollback()
        finally:
            self._close_db_connection(conn)

        # 在 src/data_processor.py 文件中添加新方法
    def save_token_usage_to_db(self, topic_id, token_usage):
        """
        将token使用量保存到consume_tokens_topic表中
        """
        conn = self._get_db_connection()
        if not conn:
            logger.error("无法建立数据库连接")
            return

        try:
            cursor = conn.cursor()

            # 插入或更新token使用量数据
            insert_query = """
                INSERT INTO consume_tokens_topic 
                (topic_id, prompt_tokens, completion_tokens, total_tokens, model_calls)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (topic_id) 
                DO UPDATE SET
                    prompt_tokens = EXCLUDED.prompt_tokens,
                    completion_tokens = EXCLUDED.completion_tokens,
                    total_tokens = EXCLUDED.total_tokens,
                    model_calls = EXCLUDED.model_calls,
                    created_at = CURRENT_TIMESTAMP
            """

            cursor.execute(insert_query, (
                topic_id,
                token_usage.get('prompt_tokens', 0),
                token_usage.get('completion_tokens', 0),
                token_usage.get('total_tokens', 0),
                token_usage.get('model_calls', 0)
            ))

            conn.commit()
            cursor.close()
            logger.info(f"主题 {topic_id} 的token使用量已保存到数据库")
        except Exception as e:
            logger.error(f"保存token使用量到数据库时出错: {e}")
            conn.rollback()
        finally:
            self._close_db_connection(conn)


    def load_existing_data(self, csv_file=None):
        """
        从现有CSV文件中加载已有的帖子数据
        """
        if csv_file is None:
            csv_file = self.config['paths']['csv_file']

        existing_data = {}
        if os.path.exists(csv_file):
            try:
                with open(csv_file, 'r', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    for row in reader:
                        topic_id = int(row['id'])
                        existing_data[topic_id] = row
            except Exception as e:
                logger.error(f"读取现有CSV文件时出错: {e}")
        # """
        #    从数据库中加载已有的帖子数据
        #    """
        # existing_data = {}
        #
        # conn = self._get_db_connection()
        # if not conn:
        #     logger.error("无法建立数据库连接")
        #     return existing_data
        #
        # try:
        #     cursor = conn.cursor()
        #     cursor.execute("SELECT id FROM forum_topics")
        #     rows = cursor.fetchall()
        #     for row in rows:
        #         existing_data[row[0]] = True  # 只需要ID来检查是否存在
        #     cursor.close()
        #     logger.info(f"从数据库加载了 {len(existing_data)} 个已存在的帖子")
        # except Exception as e:
        #     logger.error(f"从数据库加载数据时出错: {e}")
        # finally:
        #     self._close_db_connection(conn)

        return existing_data

    def extract_topic_data(self, topic_details):
        """
        提取每个帖子的 id、标题、用户问题和最佳答案。
        """
        extracted_data = []

        for topic in topic_details:
            topic_id = topic.get('id')
            title = topic.get('title', '').strip()
            tags = topic.get('tags', [])
            created_at = topic.get('created_at', '')

            post_stream = topic.get('post_stream', {})
            posts = post_stream.get('posts', [])

            if not posts:
                logger.info(f"帖子 {topic_id} 没有找到任何内容，跳过。")
                continue

            first_post = posts[0]
            user_question = first_post.get('cooked', '').strip()
            user_question = process_html_content_with_image_links(user_question)
            # 处理用户问题中的图像信息
            user_question = self.image_processor.enhance_text_with_image_descriptions(
                user_question, "user_question", topic_id
            )

            replies = []
            best_answer = ""
            for post in posts[1:]:
                cooked_content = post.get('cooked', '').strip()
                if cooked_content:
                    replies.append(cooked_content)

                if post.get('accepted_answer', False):
                    best_answer = post.get('cooked', '').strip()
                    break

            # 处理最佳答案中的图像信息
            if best_answer:
                best_answer = self.image_processor.enhance_text_with_image_descriptions(
                    best_answer, "best_answer", topic_id
                )

            extracted_data.append({
                'id': topic_id,
                'title': title,
                'tags': ','.join(tags) if isinstance(tags, list) else tags,
                'user_question': user_question,
                'best_answer': best_answer,
                'replies': replies,
                'created_at': created_at,
                'llm_answer': '',  # 默认为空字符串
                'summary_question': ''
            })

        return extracted_data

    def append_to_csv(self, data, filename=None):
        """
        将新数据追加到 CSV 文件中。
        """
        if filename is None:
            filename = self.config['paths']['csv_file']

        try:
            file_exists = os.path.exists(filename)

            with open(filename, mode='a', newline='', encoding='utf-8') as file:
                fieldnames = ['id', 'title', 'user_question', 'best_answer', 'tags', 'replies','created_at', 'llm_answer', 'summary_question']
                writer = csv.DictWriter(file, fieldnames=fieldnames)

                if not file_exists:
                    writer.writeheader()

                for row in data:
                    if 'replies' in row and isinstance(row['replies'], list):
                        row['replies'] = json.dumps(row['replies'], ensure_ascii=False)
                    writer.writerow(row)

            logger.info(f"成功追加 {len(data)} 条新数据到 {filename}")
        except Exception as e:
            logger.error(f"追加数据到CSV文件时出错: {e}")

    def append_to_answer_csv(self, data, filename=None):
        """
        将新数据追加到 CSV 文件中。
        """
        if filename is None:
            filename = self.config['paths']['csv_file']

        try:
            file_exists = os.path.exists(filename)

            with open(filename, mode='a', newline='', encoding='utf-8') as file:
                fieldnames = list(data[0].keys())
                writer = csv.DictWriter(file, fieldnames=fieldnames)

                if not file_exists:
                    writer.writeheader()

                for row in data:
                    writer.writerow(row)

            logger.info(f"成功追加 {len(data)} 条新数据到 {filename}")
        except Exception as e:
            logger.error(f"追加数据到CSV文件时出错: {e}")

    def process_search_results(self, topic_id, search_results, search_keyword, max_results=10):
        """
        处理搜索结果并保存到文件
        """
        limited_results = search_results[:max_results]

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        search_results_file = f"{self.config['paths']['forum_data_dir']}/search_results_topic_{topic_id}_{timestamp}.json"

        # 构造包含搜索关键字和结果的数据结构
        search_data = {
            "topic_id": topic_id,
            "search_keyword": search_keyword,
            "search_timestamp": timestamp,
            "total_results": len(search_results),
            "displayed_results": len(limited_results),
            "results": limited_results
        }

        try:
            # 保存到数据库
            self.save_search_results_to_db(topic_id, search_results, search_keyword)
            with open(search_results_file, 'w', encoding='utf-8') as f:
                json.dump(search_data, f, ensure_ascii=False, indent=2)
            logger.info(f"主题 {topic_id} 的搜索结果已保存到 {search_results_file}")
        except Exception as e:
            logger.error(f"保存搜索结果时出错: {e}")

    def process_retrieval_results(self, results):
        """
        处理检索结果
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = f"{self.config['paths']['forum_data_dir']}/retrieval_results_{timestamp}.json"

        try:
            # 保存到数据库
            for result in results:
                topic_id = result.get('topic_id')
                related_docs = result.get('related_docs')
                if topic_id and related_docs:
                    self.save_retrieval_results_to_db(topic_id, related_docs)
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"检索结果已保存到 {results_file}")
        except Exception as e:
            logger.error(f"保存检索结果时出错: {e}")

    def format_search_results_for_prompt(self, retrieval_result, search_results):
        original_sys_prompt = retrieval_result.get('related_docs', '')
        if '---Response Rules---' in original_sys_prompt:
            # 在---Response Rules---前插入搜索结果
            lines = original_sys_prompt.split('\n')
            new_lines = []
            for line in lines:
                if "- List up to 5 most important reference sources at the end under \"References\" section." in line:
                    continue
                elif '- Do not make anything up. Do not include information not provided by the Knowledge Base.' in line:
                    new_lines.append(line)
                    new_lines.append('- Please answer in Chinese.')
                else:
                    new_lines.append(line)
            # 更新sys_prompt
            new_sys_prompt = '\n'.join(new_lines)
        else:
            new_sys_prompt = original_sys_prompt
        if not search_results:
            return new_sys_prompt
        json_objects = []
        for i in range(1, len(search_results) + 1):
            # 创建JSON对象
            json_obj = {
                "id": i,
                "title": str(search_results[i - 1].get('title', '')),
                "textContent": str(search_results[i - 1].get('textContent', ''))
            }
            json_objects.append(json_obj)
        json_unit_str = json.dumps(json_objects, ensure_ascii=False)
        json_str = f"""
-----Search Result-----

```json
{json_unit_str}
```

"""
        # 找到---Response Rules---的位置
        if '---Response Rules---' in original_sys_prompt:
            # 在---Response Rules---前插入搜索结果
            lines = original_sys_prompt.split('\n')
            new_lines = []
            for line in lines:
                if "- List up to 5 most important reference sources at the end under \"References\" section." in line:
                    continue
                elif '---Response Rules---' in line:
                    # 在---Response Rules---前插入搜索结果
                    new_lines.append(json_str)
                    new_lines.append(line)
                elif '- Do not make anything up. Do not include information not provided by the Knowledge Base.' in line:
                    new_lines.append(line)
                    new_lines.append('- Please answer in Chinese.')
                else:
                    new_lines.append(line)
            # 更新sys_prompt
            new_sys_prompt = '\n'.join(new_lines)
        else:
            # 如果没有找到---Response Rules---，则在sys_prompt末尾添加
            new_sys_prompt = original_sys_prompt + '\n-----Search Result-----\n' + json_str + '\n---Response Rules---'
        return new_sys_prompt
