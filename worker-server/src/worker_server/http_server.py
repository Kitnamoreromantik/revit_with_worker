import http
import logging
from http import HTTPStatus
from typing import Union, NoReturn

import requests
from requests import HTTPError, RequestException

from .abs_server import ABCServer
from .retry_session import RetrySession
from .typings import (
    TaskParams,
    RequestParams,
    ResponseParams,
    IntermediateResponseParams,
)
from .utils import object_to_cropped_str


class HTTPServer(ABCServer):
    def __init__(
        self, 
        worker, 
        config_path: str = "default.yaml"
    ):
        super().__init__(worker, config_path=config_path)
        self.session = RetrySession(
            retries=self.config.max_http_retries, 
            backoff_factor=self.config.delay,
            mtls_enabled=self.config.mtls_enabled,
            mtls_cert_path=self.config.mtls_cert_path,
            ssl_verify=self.config.ssl_verify
        ).get_session()
        self.headers = {"Content-type": "application/json"}

    def get_task(self) -> TaskParams:
        payload = RequestParams(
            model_id=self.config.model_id,
            worker_id=self.server_id,
        )
        try:
            self.logger.info(f"Requesting task from {self.config.task_url} with payload: {payload.model_dump()}")
            response = self.session.post(
                self.config.task_url,
                json=payload.model_dump(),
                headers=self.headers,
                timeout=(10, 30)  # (connect timeout, read timeout)
            )
            self.logger.debug(f"Received response with status {response.status_code}")
            if response.status_code != HTTPStatus.OK:
                msg = (
                    f"In response to {response.request.url} returned status"
                    f"code {response.status_code}. Reason: {response.content}"
                )
                self.logger.error(msg)
                raise HTTPError(msg)

            res = response.json()
            self.logger.debug(f"Task response: {res}")
            return TaskParams.model_validate(res)
        except requests.exceptions.Timeout as e:
            self.logger.error(f"Request timeout to {self.config.task_url}: {str(e)}")
            raise RequestException(f"Request timeout: {str(e)}")
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error to {self.config.task_url}: {str(e)}")
            raise RequestException(f"Connection error: {str(e)}")
        except RequestException as e:
            self.logger.error(f"Request failed to {self.config.task_url}: {str(e)}", exc_info=True)
            raise RequestException(f"Request failed: {str(e)}")

    def send_result(self, result: ResponseParams) -> Union[HTTPStatus, NoReturn]:
        try:
            self.logger.debug(f"Sending result to {self.config.result_url}")
            response = self.session.post(
                self.config.result_url,
                json=result.model_dump(),
                headers=self.headers,
                timeout=(10, 30)  # (connect timeout, read timeout)
            )
            if response.status_code != HTTPStatus.OK:
                msg = (
                    f"In response to {response.request.url} returned status"
                    f"code {response.status_code}. Reason: {response.content}"
                )
                self.logger.error(msg)
                raise HTTPError(msg)
            self.logger.info(
                f"Task: {object_to_cropped_str(result.model_dump())} "
                f"sent with status {http.HTTPStatus.OK}"
            )
            return http.HTTPStatus.OK
        except requests.exceptions.Timeout as e:
            self.logger.error(f"Request timeout to {self.config.result_url}: {str(e)}")
            raise RequestException(f"Request timeout: {str(e)}")
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error to {self.config.result_url}: {str(e)}")
            raise RequestException(f"Connection error: {str(e)}")
        except RequestException as e:
            self.logger.error(f"Request failed to {self.config.result_url}: {str(e)}", exc_info=True)
            raise RequestException(f"Request failed: {str(e)}")

    def _send_intermediate_result(
        self, result: IntermediateResponseParams
    ) -> Union[HTTPStatus, NoReturn]:
        try:
            self.logger.debug(f"Sending intermediate result to {self.config.intermediate_result_url}")
            response = self.session.post(
                self.config.intermediate_result_url,
                json=result.model_dump(),
                headers=self.headers,
                timeout=(10, 30)  # (connect timeout, read timeout)
            )
            if response.status_code != HTTPStatus.OK:
                msg = (
                    f"In response to {response.request.url} returned status"
                    f"code {response.status_code}. Reason: {response.content}"
                )
                self.logger.error(msg)
                raise HTTPError(msg)
            self.logger.info(
                f"Intermediate task result: {object_to_cropped_str(result.model_dump())} "
                f"sent with status {http.HTTPStatus.OK}"
            )
            return http.HTTPStatus.OK
        except requests.exceptions.Timeout as e:
            self.logger.error(f"Request timeout to {self.config.intermediate_result_url}: {str(e)}")
            raise RequestException(f"Request timeout: {str(e)}")
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error to {self.config.intermediate_result_url}: {str(e)}")
            raise RequestException(f"Connection error: {str(e)}")
        except RequestException as e:
            self.logger.error(f"Request failed to {self.config.intermediate_result_url}: {str(e)}", exc_info=True)
            raise RequestException(f"Request failed: {str(e)}")