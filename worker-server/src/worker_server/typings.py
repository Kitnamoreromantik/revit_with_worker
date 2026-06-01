from enum import Enum
from typing import Protocol, Dict, List, Any, Optional, Union

from pydantic import BaseModel


class WorkerProtocol(Protocol):
    def inference(self, data: Dict) -> Dict:
        pass


class RequestParams(BaseModel):
    model_id: str
    worker_id: str


class TaskParams(BaseModel):
    request_id: Optional[str]
    data: Optional[Dict]
    trace_id: str


class ServerConfig(BaseModel):
    task_url: str
    result_url: str
    upload_url: str
    download_url: str
    model_id: str
    default_params: Dict[str, Union[str, int, bool, float]]
    delay: int
    connection_error_delay: int
    max_http_retries: int


class Status(str, Enum):
    DONE = "DONE"
    FAIL = "FAIL"


class ResponseParams(BaseModel):
    data: Optional[Dict] = None
    request_id: str
    worker_id: str
    status: Status
    message: Optional[str] = None


class BasicServerConfig(BaseModel):
    base_domain: str
    model_id: str
    default_params: Dict[str, Union[str, int, bool, float]]

    delay: int = 1
    connection_error_delay: int = 5
    max_http_retries: int = 3
    log_level: str = "INFO"
    mtls_enabled: bool = False
    mtls_cert_path: Optional[str] = None
    ssl_verify: Union[bool, str] = True

    def to_dict(self) -> dict:
        return self.model_dump()

    # Свойства для получения полных URL с фиксированными путями
    @property
    def task_url(self) -> str:
        return f"{self.base_domain}/worker-adapter/api/v1/tasks/pull"

    @property
    def result_url(self) -> str:
        return f"{self.base_domain}/worker-adapter/api/v1/tasks/complete"

    @property
    def intermediate_result_url(self) -> str:
        return f"{self.base_domain}/worker-adapter/api/v1/tasks/intermediate"

    @property
    def download_url(self) -> str:
        return f"{self.base_domain}/worker-adapter/api/v1/files/download/"

    @property
    def upload_url(self) -> str:
        return f"{self.base_domain}/worker-adapter/api/v1/files/upload"


class RequestInfoDict(BaseModel):
    left_retries: int
    fusion_request_id: str
    rudalle_request_id: str
    request: Dict


class RequestInfo(BaseModel):
    rudalle_request_id: str
    fusion_request_id: str
    request: Dict
    left_retries: int = 3

    def to_dict(self) -> dict:
        return self.model_dump()


class IntermediateResponseParams(BaseModel):
    data: Optional[Dict] = None
    request_id: str
    worker_id: str
    trace_id: str