import logging
import time
import uuid
from abc import ABC, abstractmethod
from http import HTTPStatus
from typing import NoReturn, Union, Dict, Any

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import ValidationError

from .file_handler import FileHandler
from .typings import (
    BasicServerConfig,
    WorkerProtocol,
    TaskParams,
    Status,
    ResponseParams,
    IntermediateResponseParams,
)
from .utils import object_to_cropped_str


class ConfigErrorException(Exception):
    pass


def _get_log_level(log_level_str: str) -> int:
    """
    Convert string log level to logging constant
    
    Args:
        log_level_str: String representation of log level (e.g., "DEBUG", "INFO", "WARNING", "ERROR")
        
    Returns:
        int: Logging level constant
    """
    log_level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    log_level_upper = log_level_str.upper()
    if log_level_upper not in log_level_map:
        raise ConfigErrorException(
            f"Invalid log_level '{log_level_str}'. "
            f"Must be one of: {', '.join(log_level_map.keys())}"
        )
    return log_level_map[log_level_upper]


class Config:
    config_strategy = BasicServerConfig

    def __init__(
            self,
            config_path: str = "default.yaml",
    ):
        self.config_path = config_path
        self.config = None
        self.read_config()
        self.check_config()

    def read_config(self) -> None:
        try:
            with open(self.config_path, "r") as file:
                self.config = yaml.full_load(file)
                if self.config is None:
                    raise ConfigErrorException(f"Config file {self.config_path} is empty")
        except FileNotFoundError:
            raise ConfigErrorException(f"Config {self.config_path} not found")
        except yaml.YAMLError as e:
            raise ConfigErrorException(f"Error parsing YAML config: {e}")

    def check_config(self) -> NoReturn:
        if self.config is None:
            raise ConfigErrorException("Config was not loaded properly")

        if not isinstance(self.config, dict):
            raise ConfigErrorException(f"Config file {self.config_path} must contain a dictionary")

        for var in self.config_strategy.__annotations__.keys():
            if var not in self.config:
                raise ConfigErrorException(f"'{var}' not found in config file {self.config_path}")

    def get_config(self) -> BasicServerConfig:
        if self.config is None:
            raise ConfigErrorException("Config is None")

        try:
            return self.config_strategy(**self.config)
        except ValidationError as e:
            raise ConfigErrorException(f"Config validation error: {e}")


class ABCServer(ABC):
    scheduler = BackgroundScheduler()

    def __init__(
        self, 
        worker: WorkerProtocol, 
        config_path: str = "default.yaml"
    ):
        self.worker = worker
        self.config = self._read_config(config_path)
        self.server_id = str(uuid.uuid4())
        self.name = f"Worker_{self.server_id}"
        self._current_task: TaskParams | None = None
        
        # Use log_level from config
        log_level = _get_log_level(self.config.log_level)
        
        self.logger = self.setup_logger(self.name, level=log_level)
        self.worker.logger = self.logger
        self.file_handler = FileHandler(
            server_id=self.server_id, logger=self.logger, config=self.config
        )

    @abstractmethod
    def get_task(self) -> TaskParams:
        """
        Getting task from backend
        """
        pass

    @abstractmethod
    def send_result(self, result: ResponseParams):
        """
        Sending worker result to backend
        """
        pass

    @abstractmethod
    def _send_intermediate_result(self, result: IntermediateResponseParams):
        """
        Sending intermediate worker result to backend.

        This low-level method should perform actual I/O in concrete implementations.
        """
        pass

    def setup_logger(self, name: str, level: int = logging.INFO) -> logging.Logger:
        """
        Set up a logger with console and file handlers

        Args:
            name: Name of the logger (usually the class/instance name)
            level: Logging level (default: logging.INFO)

        Returns:
            Configured logger instance
        """
        logger = logging.getLogger(name)

        # Prevent adding handlers multiple times
        if logger.handlers:
            return logger

        logger.setLevel(level)

        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)

        # Add handlers to logger
        logger.addHandler(console_handler)
        return logger

    def _wait_for_task(self) -> NoReturn:
        self.logger.debug(f"No new tasks, sleeping {self.config.delay} seconds")
        time.sleep(self.config.delay)

    def _return_failed_status_download(self, request_id: str):
        failed_image_response = ResponseParams(
            request_id=request_id,
            message="Failed to download all files",
            status=Status.FAIL,
            worker_id=self.server_id
        )
        self.send_result(result=failed_image_response)

    def _return_failed_status_upload(self, request_id: str):
        failed_image_response = ResponseParams(
            request_id=request_id,
            message="Failed to upload all files",
            status=Status.FAIL,
            worker_id = self.server_id
        )
        self.send_result(result=failed_image_response)

    def _validate_task_with_files(self, task: TaskParams) -> NoReturn:
        responses = {
            "OK": lambda: self._process_task(task),
            "FAIL": lambda: self._return_failed_status_download(
                request_id=task.request_id
            ),
            "WAIT": lambda: self._wait_for_task(),
        }
        if not task.request_id:
            status = "WAIT"
        elif "files" in task.data.keys() and len(task.data["files"]) != 0:
            files, message, status = self.file_handler.get_files_from_request(
                task.data["files"]
            )
            task.data["files"] = files
        else:
            status = "OK"

        return responses[status]()

    @staticmethod
    def diff_dict(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: str(dict1[key])
            for key in dict1
            if key not in dict2 or dict1[key] != dict2[key]
        }

    @staticmethod
    def _read_config(config_path: str):
        return Config(config_path=config_path).get_config()

    def _get_model_params(self, task) -> Dict[str, Union[str, int, bool]]:
        changed_params = self.diff_dict(task.data, self.config.default_params)
        self.logger.info(
            f"Defaults changed to: {object_to_cropped_str(changed_params)}"
        )
        task.data = {**self.config.default_params, **task.data}
        return task.data

    def _process_task(self, request: TaskParams) -> NoReturn:
        self.logger.info(f"Server got task: {object_to_cropped_str(request)}")
        self.logger.debug(f"Setting default params")
        data = self._get_model_params(request)
        self.logger.debug(f"Giving task to worker")

        # Save current task context so that worker can send intermediate results
        self._current_task = request
        try:
            result_data = self.worker.inference(data)
        finally:
            # Clear current task context after inference is finished
            self._current_task = None

        result = ResponseParams(
            data=result_data,
            request_id=request.request_id,
            status=Status.DONE,
            worker_id=self.server_id,
        )
        if "files" in result_data.keys():
            results, _, status = self.file_handler.upload_files_to_s3(
                result_data["files"]
            )
            self.logger.debug(f"Got images ids: {results} with status {status}")
            if status == "FAIL":
                self._return_failed_status_upload(result.request_id)
            else:
                results = [s.strip('"') for s in results]
                result_data["files"] = results
                result.data = result_data
                self.send_result(result)
        else:
            self.send_result(result)

    def send_intermediate_result(self, data: Dict[str, Any]) -> Union[HTTPStatus, NoReturn]:
        """
        Public helper for workers to send intermediate results.

        Worker provides only `data`; all other fields are filled by this
        abstract class based on the current task context.
        """
        if not self._current_task:
            self.logger.warning(
                "Attempt to send intermediate result without active task context"
            )
            return

        self.logger.debug(
            f"Preparing intermediate result for request_id={self._current_task.request_id}"
        )
        result_data = data

        # Handle files the same way as for /complete endpoint
        if "files" in result_data.keys() and result_data["files"]:
            results, _, status = self.file_handler.upload_files_to_s3(
                result_data["files"]
            )
            self.logger.debug(f"Got images ids for intermediate result: {results} with status {status}")
            if status == "FAIL":
                # Reuse the same failure behaviour as for final result
                self._return_failed_status_upload(self._current_task.request_id)
                return
            results = [s.strip('"') for s in results]
            result_data["files"] = results

        intermediate = IntermediateResponseParams(
            data=result_data,
            request_id=self._current_task.request_id,
            worker_id=self.server_id,
            trace_id=self._current_task.trace_id,
        )

        return self._send_intermediate_result(intermediate)

    def run_loop(self, killer) -> None:
        self.logger.info(f"Starting worker loop for {self.name}")
        self.logger.info(f"Task URL: {self.config.task_url}")
        while not killer.kill_now:
            try:
                # Получение задачи
                self.logger.debug("Attempting to get task...")
                data = self.get_task()
            except Exception as err:
                self.logger.error(f"Error getting task: {err}")
                time.sleep(self.config.delay)
                continue

            try:
                # Обработка задачи
                self._validate_task_with_files(data)
            except Exception as err:
                # Ошибка при обработке задачи - отправляем FAIL
                self.logger.error(f"Error during processing the task: {err}", exc_info=True)
                status_failed = ResponseParams(
                    request_id=data.request_id,
                    message=str(err),
                    worker_id=self.server_id,
                    status=Status.FAIL,
                )
                self.send_result(result=status_failed)

            time.sleep(self.config.delay)
