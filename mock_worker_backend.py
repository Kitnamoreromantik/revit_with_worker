import argparse
import json
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import urlparse


TASK_QUEUE: list[Dict[str, Any]] = []
RESULTS: list[Dict[str, Any]] = []
INTERMEDIATE_RESULTS: list[Dict[str, Any]] = []


def _task_from_question(question: str) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    return {
        "request_id": request_id,
        "trace_id": str(uuid.uuid4()),
        "data": {
            "files": None,
            "params": {
                "question": question,
                "thread_id": request_id,
            },
        },
    }


class MockWorkerBackendHandler(BaseHTTPRequestHandler):
    server_version = "MockWorkerBackend/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/results":
            self._send_json({"results": RESULTS, "intermediate_results": INTERMEDIATE_RESULTS})
            return
        if path == "/health":
            self._send_json({"status": "ok", "queued_tasks": len(TASK_QUEUE), "results": len(RESULTS)})
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        payload = self._read_json()

        if path == "/frontend/request":
            question = self._extract_question(payload)
            if not question:
                self._send_json(
                    {"error": "Expected JSON body with 'question' or params.question"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            task = _task_from_question(question)
            TASK_QUEUE.append(task)
            self._send_json({"queued": True, "task": task})
            return

        if path == "/worker-adapter/api/v1/tasks/pull":
            if not TASK_QUEUE:
                self._send_json(
                    {"request_id": None, "trace_id": str(uuid.uuid4()), "data": {}}
                )
                return

            task = TASK_QUEUE.pop(0)
            self._send_json(task)
            return

        if path == "/worker-adapter/api/v1/tasks/complete":
            RESULTS.append({"received_at": time.time(), "payload": payload})
            self._send_text("OK")
            return

        if path == "/worker-adapter/api/v1/tasks/intermediate":
            INTERMEDIATE_RESULTS.append({"received_at": time.time(), "payload": payload})
            self._send_text("OK")
            return

        if path == "/worker-adapter/api/v1/files/upload":
            self._send_text(str(uuid.uuid4()))
            return

        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.log_date_time_string()} - {format % args}")

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}

        body = self.rfile.read(length)
        try:
            decoded = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _extract_question(payload: Dict[str, Any]) -> str | None:
        direct_question = payload.get("question")
        if isinstance(direct_question, str) and direct_question.strip():
            return direct_question.strip()

        params = payload.get("params")
        if isinstance(params, dict):
            question = params.get("question")
            if isinstance(question, str) and question.strip():
                return question.strip()

        return None

    def _send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, payload: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local mock backend for worker-server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8008)
    parser.add_argument("--question", help="Queue one initial question before serving")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.question:
        TASK_QUEUE.append(_task_from_question(args.question))

    server = ThreadingHTTPServer((args.host, args.port), MockWorkerBackendHandler)
    print(f"Mock backend listening on http://{args.host}:{args.port}")
    print("Queue a request: POST /frontend/request with {'question': '...'}")
    print("Read results:    GET /results")
    server.serve_forever()


if __name__ == "__main__":
    main()
