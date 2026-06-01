import pytest
import http
from requests.exceptions import RequestException
from src.worker_server.typings import ResponseParams, Status
from unittest.mock import patch

task = ResponseParams(
    data={},
    request_id = "123",
    status=Status.DONE,
    worker_id = "456"
)


@pytest.fixture(scope="session")
def real_server(http_init):
    return http_init


def test_get_task(get_task_mock, real_server):
    response = real_server.get_task()
    response_dict = response.dict()
    assert all(key in response_dict for key in ["request_id", "data", "trace_id"])
    assert all(key in get_task_mock.request_history[0].json().keys() for key in ['worker_id', "model_id"])


def test_send_result(send_result_mock, real_server):
    response = real_server.send_result(task)
    assert response == http.HTTPStatus.OK


def test_send_intermediate_result(send_intermediate_result_mock, real_server):
    # Имитация активного задания
    from src.worker_server.typings import TaskParams

    task_params = TaskParams(
        request_id="req-1",
        data={},
        trace_id="trace-1",
    )

    # Установим контекст текущей задачи напрямую
    real_server._current_task = task_params  # type: ignore[attr-defined]

    # Отправляем промежуточный результат (worker передаёт только data)
    response = real_server.send_intermediate_result({"foo": "bar"})
    assert response == http.HTTPStatus.OK


def test_failed_result(send_failed_result_mock, real_server):

    with pytest.raises(RequestException,  match=r"Request failed: .*"):
        real_server.send_result(task)


def test_run_loop(mock_killer, send_result_mock, get_task_mock, real_server):

    with patch.object(mock_killer, 'kill_now', side_effect=[False, False, True]):
        real_server.run_loop(mock_killer)
