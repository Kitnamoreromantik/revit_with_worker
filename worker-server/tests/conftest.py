import pytest
from src.worker_server.http_server import HTTPServer
import uuid
from typing import Dict, Any
from requests_mock import Mocker
import signal
from unittest.mock import MagicMock

from src.worker_server.typings import TaskParams


class GracefulKiller:
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args):
        self.kill_now = True


class EmptyWorker:
    def __init__(self, *args, **kwargs):
        pass

    @staticmethod
    def inference(data: Dict[str, Any]):
        return data


@pytest.fixture(scope="session")
def http_init():

    server = HTTPServer(worker=EmptyWorker(), config_path="default.yaml")
    server.name = "test"

    return server


@pytest.fixture()
def get_task_mock():
    with Mocker() as mock:
        task = TaskParams(
            request_id=str(uuid.uuid4()),
            data={"prompt": "море"},
            trace_id=str(uuid.uuid4())
        ).model_dump()
        mock.post('https://backend.example.com/worker-adapter/api/v1/tasks/pull', json=task)
        yield mock


@pytest.fixture()
def send_result_mock():
    with Mocker() as mock:
        mock.post('https://backend.example.com/worker-adapter/api/v1/tasks/complete', status_code=200, text="OK")
        yield mock


@pytest.fixture()
def send_failed_result_mock():
    with Mocker() as mock:
        mock.post('https://backend.example.com/worker-adapter/api/v1/tasks/complete', status_code=400, text="FAIL")
        yield mock


@pytest.fixture()
def send_intermediate_result_mock():
    with Mocker() as mock:
        mock.post(
            'https://backend.example.com/worker-adapter/api/v1/tasks/intermediate',
            status_code=200,
            text="OK",
        )
        yield mock


@pytest.fixture()
def killer_init():
    killer = GracefulKiller()
    return killer


@pytest.fixture
def mock_killer():
    killer = MagicMock()
    killer.kill_now = False
    return killer
