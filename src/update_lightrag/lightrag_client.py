import time
from http.client import responses

import requests
import json
from typing import Dict
from src.ForumBot.logging_config import main_logger as logger

class LightRAGClient:
    def __init__(self, config):
        self.config = config

    def upload_document(self, file_path, api_url, api_key=None):
        """
        上传文档到LightRAG系统
        """
        url = f"{api_url}/documents/upload"

        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        with open(file_path, 'rb') as file:
            files = {'file': file}
            response = requests.post(url, files=files, headers=headers)

        return response.json()

    def upload_all_documents_from_file(self, file_list_path, api_url, api_key=None):
        """
        从文件列表中读取所有文件路径并上传
        """
        # 上传文件前查询管道状态是否为空闲，若不为空闲则等待
        self.wait_for_pipeline_status_not_busy(api_url)

        uploaded_documents = []

        with open(file_list_path, 'r', encoding='utf-8') as f:
            file_paths = [line.strip() for line in f.readlines() if line.strip()]

        logger.info(f"找到 {len(file_paths)} 个文件需要上传")

        for i, file_path in enumerate(file_paths, 1):
            try:
                full_file_path = f"{self.config['lightrag_paths']['rag_data_dir']}/{file_path}"

                result = self.upload_document(full_file_path, api_url, api_key)
                if result.get("status") == "success":
                    track_id = result.get("track_id")
                    logger.info(f"  上传成功, 跟踪ID: {track_id}")
                    uploaded_documents.append({
                        "file_path": file_path,
                        "track_id": track_id,
                        "status": "success"
                    })

                else:
                    logger.info(f"  上传失败: {result}")
                    uploaded_documents.append({
                        "file_path": file_path,
                        "error": result,
                        "status": "failed"
                    })
            except Exception as e:
                logger.error(f"  上传出错: {str(e)}")
                uploaded_documents.append({
                    "file_path": file_path,
                    "error": str(e),
                    "status": "error"
                })

            # 添加小延迟避免请求过于频繁
            time.sleep(0.1)

        # 打印汇总信息
        success_count = sum(1 for doc in uploaded_documents if doc["status"] == "success")
        failed_count = sum(1 for doc in uploaded_documents if doc["status"] == "failed")
        error_count = sum(1 for doc in uploaded_documents if doc["status"] == "error")

        logger.info(f"\n上传完成汇总:")
        logger.info(f"  成功: {success_count}")
        logger.info(f"  失败: {failed_count}")
        logger.info(f"  错误: {error_count}")
        logger.info(f"  总计: {len(uploaded_documents)}")

        return uploaded_documents


    def delete_document(self, doc_id, api_url, api_key=None):
        """
        删除lightRAG系统上的文档
        """
        url = f"{api_url}/documents/delete_document"

        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        data = {
            "doc_ids": [doc_id],
            "delete_file": False
        }

        response = requests.delete(url, json=data, headers=headers)

        return response.json()

    def delete_document_from_file(self, file_list_ids, api_url, api_key=None):
        """
            从删除文件列表中读取所有文件id并发送删除请求
        """
        deleted_documents = []

        with open(file_list_ids, 'r', encoding='utf-8') as f:
            file_ids = [line.strip() for line in f.readlines() if line.strip()]

        logger.info(f"找到 {len(file_ids)} 个文件需要删除")

        for i, file_id in enumerate(file_ids, 1):
            try:
                if i <= len(file_ids):
                    # 上传文件前查询管道状态是否为空闲，若不为空闲则等待
                    self.wait_for_pipeline_status_not_busy(api_url)

                result = self.delete_document(file_id, api_url, api_key)
                if result.get("status") == "deletion_started":
                    logger.info(f"  删除成功, 文件ID: {file_id}")
                    deleted_documents.append({
                        "file_id": file_id,
                        "status": "success"
                    })
                else:
                    logger.info(f"  删除失败: {result}")
                    deleted_documents.append({
                        "file_id": file_id,
                        "error": result,
                        "status": "failed"
                    })
            except Exception as e:
                logger.error(f"  删除出错: {str(e)}")
                deleted_documents.append({
                    "file_id": file_id,
                    "error": str(e),
                    "status": "error"
                })

        # 打印汇总信息
        success_count = sum(1 for doc in deleted_documents if doc["status"] == "success")
        failed_count = sum(1 for doc in deleted_documents if doc["status"] == "failed")
        error_count = sum(1 for doc in deleted_documents if doc["status"] == "error")

        logger.info(f"\n删除完成汇总:")
        logger.info(f"  成功: {success_count}")
        logger.info(f"  失败: {failed_count}")
        logger.info(f"  错误: {error_count}")
        logger.info(f"  总计: {len(deleted_documents)}")

    def extract_file_path_id_mapping(self, json_data: dict) -> Dict[str, str]:
        """
        从JSON数据中提取file_path和id的对应关系
        """
        mapping = {}

        documents = json_data.get("documents", [])
        for doc in documents:
            doc_id = doc.get("id")
            file_path = doc.get("file_path")
            if doc_id and file_path:
                mapping[file_path] = doc_id

        return mapping

    def _save_mapping_to_file(self, mapping: Dict[str, str]):
        """
        将映射关系保存到本地文件
        """
        # 读取现有文件内容
        existing_mapping = {}
        file_path = self.config['lightrag_paths']['files_id_mapping']
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_mapping = json.load(f)
        except FileNotFoundError:
            pass

        # 合并新旧映射
        existing_mapping.update(mapping)

        # 完全覆盖写入
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(existing_mapping, f, indent=2, ensure_ascii=False)


    def get_filename_id_mapping_from_lightrag(self, base_url, limit=50):  # 分页数据每页数据必须大于等于10
        """
        从lightRAG获取文件名称与文件id映射
        """
        page = 1

        while True:
            try:
            # 构造分页请求
                payload = {
                    "page": page,
                    "page_size": limit
                }

                # 发送请求
                response = requests.post(f"{base_url}/documents/paginated", json=payload)
                response.raise_for_status()
                result = response.json()

                # 提取映射关系
                mapping = self.extract_file_path_id_mapping(result)

                # 保存到本地文件
                self._save_mapping_to_file(mapping)

                # 检查分页信息
                pagination = result.get('pagination', {})
                current_page = pagination.get('page', 1)
                total_pages = pagination.get('total_pages', 1)

                # 如果已到最后一页，退出循环
                if current_page >= total_pages:
                    break

                page += 1
            except requests.exceptions.RequestException as e:
                logger.error(f"获取第{page}页文件状态数据时发生错误: {e}")
                raise
            except json.JSONDecodeError as e:
                logger.error(f"解析第{page}页文件状态响应JSON时发生错误: {e}")
                raise
            except Exception as e:
                logger.error(f"处理第{page}页文件状态数据时发生未知错误: {e}")
                raise
        logger.info(f"成功获取所有文件映射关系，共处理 {total_pages} 页数据")

    def is_all_file_processed(self, api_url, api_key=None):
        """
        检查文档上传状态是否全部处理完成
        """
        try:
            payload = {
                "page": 1,
                "page_size": 10  # 分页数据每页数据必须大于等于10
            }

            # 发送请求到/documents/paginated接口
            response = requests.post(
                f"{api_url}/documents/paginated",
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            # 检查status_counts字段是否存在PENDING或PROCESSING状态
            status_counts = data.get("status_counts", {})
            if "pending" in status_counts and status_counts["pending"] > 0:
                return False
            if "processing" in status_counts and status_counts["processing"] > 0:
                return False
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"请求文件状态错误: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            return None
        except Exception as e:
            logger.error(f"检查文件处理状态时发生未知错误: {e}")
            return None

    def is_lightrag_empty(self, api_url, api_key=None):
        """
        检查LightRAG上的数据是否为空
        """
        try:
            payload = {
                "page": 1,
                "page_size": 10  # 分页数据每页数据必须大于等于10
            }

            # 发送请求
            response = requests.post(
                f"{self.config['retrieval']['base_url']}/documents/paginated",
                json=payload
            )
            response.raise_for_status()
            result = response.json()

            # 获取total_count字段
            pagination = result.get('pagination', {})
            total_count = pagination.get('total_count', 0)

            # 判断数据是否为空
            return total_count == 0

        except requests.exceptions.RequestException as e:
            logger.error(f"检查LightRAG数据状态失败: {e}")
            return None
        except Exception as e:
            logger.error(f"解析LightRAG数据状态时发生错误: {e}")
            return None


    def is_pipeline_status_busy(self, api_url, api_key=None):
        """
            获取文档索引管道的当前状态，管道状态忙碌时无法删除文件
        """
        url = f"{api_url}/documents/pipeline_status"

        headers = {}
        api_key = None
        if api_key:
            headers["X-API-Key"] = api_key

        response = None
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # 检查HTTP状态码
            status_data = response.json()

            return status_data.get("busy", False)
        except requests.exceptions.RequestException as e:
            logger.error(f"请求管道状态错误: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            logger.error(f"原始响应内容: {response.text}")
            return None

    def wait_for_pipeline_status_not_busy(self, api_url, api_key=None):
        """
        等待管道状态变为非忙碌状态
        """
        logger.info("检查管道状态是否空闲...")
        while True:
            is_busy = self.is_pipeline_status_busy(api_url, api_key)
            if is_busy is None:  # 查询失败
                logger.warning("无法获取管道状态，等待1秒后重试")
                time.sleep(1)
            elif is_busy:  # 管道忙碌
                logger.info("管道正忙，等待1秒后重试...")
                time.sleep(1)
            else:  # 管道空闲
                logger.info("管道已空闲，开始执行操作")
                break