import logging
from http import HTTPStatus
from typing import Dict, List, Union

from requests.exceptions import HTTPError, RequestException

from .retry_session import RetrySession
from .typings import BasicServerConfig


class FileHandler:
    def __init__(self, server_id: str, logger, config: BasicServerConfig):
        self.logger = logger
        self.config = config
        self.session = RetrySession(
            retries=self.config.max_http_retries, 
            backoff_factor=self.config.delay,
            mtls_enabled=self.config.mtls_enabled,
            mtls_cert_path=self.config.mtls_cert_path,
            ssl_verify=self.config.ssl_verify
        ).get_session()
        self.server_id = server_id

    @staticmethod
    def convert_files_to_b64(files: List[bytes]) -> List[str]:
        """Принимает список байтов, возвращает список строк base64"""
        import base64
        return [
            base64.b64encode(file).decode("utf-8") for file in files
        ]

    def _make_file_get_request(self, ids: str) -> bytes:
        try:
            response = self.session.get(self.config.download_url + ids)
            if response.status_code != HTTPStatus.OK:
                msg = (
                    f"In response to {response.request.url} returned status"
                    f"code {response.status_code}. Reason: {response.content}"
                )
                self.logger.error(msg)
                raise HTTPError(msg)
            return response.content
        except RequestException as e:
            self.logger.error("Request failed", exc_info=True)
            raise RequestException(f"Request failed: {str(e)}")

    def _validate_files_from_request(
            self,
            id_list: List[str],
            results: List[Union[bytes, str]],
            upload: bool = False,
    ) -> tuple[List[Union[bytes, str]], str, str]:
        task_type = "UPLOADED" if upload else "DOWNLOADED"
        statuses: Dict[str, tuple[str, int]] = {
            "OK": (f"All images {task_type}", logging.DEBUG),
            "FAIL": (
                f"Could not get all images. Expected: {len(id_list)}, got: {len(results)}",
                logging.ERROR,
            ),
        }
        status = "OK" if len(results) == len(id_list) else "FAIL"
        message, level = statuses[status]
        self.logger.log(level, message)
        return results, message, status

    def get_files_from_request(self, id_list: List[str]) -> tuple[List[str], str, str]:
        files_list: List[bytes] = []
        id_list = [s.strip('"') for s in id_list]

        self.logger.debug(f"Trying to get images: {id_list}")
        for ids in id_list:
            files_list.append(self._make_file_get_request(ids=ids))

        results: List[str] = self.convert_files_to_b64(files_list)
        return self._validate_files_from_request(id_list=id_list, results=results)

    def _put_file_post_request(self, file: bytes) -> str:
        try:
            response = self.session.post(self.config.upload_url, files={"file": file})
            if response.status_code != HTTPStatus.OK:
                msg = (
                    f"In response to {response.request.url} returned status"
                    f"code {response.status_code}. Reason: {response.content}"
                )
                self.logger.error(msg)
                raise HTTPError(msg)

            res = response.text.strip()
            self.logger.debug(f"Image uploaded, got id {res}")
            return res

        except RequestException as e:
            self.logger.error("Request failed", exc_info=True)
            raise RequestException(f"Request failed: {str(e)}")

    def upload_files_to_s3(self, files: List[Union[str, bytes]]) -> tuple[List[str], str, str]:
        """
        Принимает список файлов в одном из двух форматов:
        - bytes: «сырое» содержимое файла (рекомендуемый формат для Worker)
        - str: base64-строка (старый формат, поддерживается для совместимости)
        """
        import base64

        ids_list: List[str] = []
        files_bytes: List[bytes] = []

        for file in files:
            if isinstance(file, bytes):
                files_bytes.append(file)
            elif isinstance(file, str):
                files_bytes.append(base64.b64decode(file))
            else:
                raise TypeError(
                    f"Unsupported file type {type(file)} in 'files'. "
                    f"Expected bytes or base64 string."
                )

        for file in files_bytes:
            ids_list.append(self._put_file_post_request(file=file))

        # Для валидации используем исходный список, чтобы количество
        # элементов совпадало с переданным Worker'ом
        return self._validate_files_from_request(
            id_list=[str(f) for f in files], results=ids_list, upload=True
        )