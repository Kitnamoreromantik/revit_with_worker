"""
To start the Revit worker, run from the repo root:
uv run python run_revit_worker.py --config revit_worker.yaml
"""
import argparse
import asyncio
import signal
import sys
import uuid
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parent
WORKER_SERVER_SRC = REPO_ROOT / "worker-server" / "src"
REVIT_CODE_GENERATOR_SRC = REPO_ROOT / "revit_code_generator"

for path in (WORKER_SERVER_SRC, REVIT_CODE_GENERATOR_SRC):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from worker_server import HTTPServer, WorkerProtocol  # noqa: E402
from execute_revit_workflow import run_revit_workflow  # noqa: E402


class RevitHTTPServer(HTTPServer):
    def get_task(self):
        task = super().get_task()
        if task.data and task.data.get("files") is None:
            task.data["files"] = []
        return task


class RevitCodeGeneratorWorker(WorkerProtocol):
    def inference(self, data: Dict[str, Any]) -> Dict[str, Any]:
        question = self._extract_question(data)
        params = data.get("params") or {}
        thread_id = (
            params.get("thread_id")
            or params.get("session_id")
            or data.get("thread_id")
            or f"revit-worker-{uuid.uuid4()}"
        )
        # Run revit workflow and collect events:
        result = asyncio.run(run_revit_workflow(question, str(thread_id)))
        return {
            "question": question,
            **result,
        }

    @staticmethod
    def _extract_question(data: Dict[str, Any]) -> str:
        params = data.get("params")
        if not isinstance(params, dict):
            raise ValueError("Expected task data to contain a 'params' dictionary")

        question = params.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Expected task data['params']['question'] to be a non-empty string")

        return question.strip()


class GracefulKiller:
    kill_now = False

    def __init__(self, logger):
        self.logger = logger
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self):
        self.logger.info("Exiting gracefully after this iteration")
        self.kill_now = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Revit code generator worker")
    parser.add_argument(
        "--config",
        default=str(REPO_ROOT / "revit_worker.yaml"),
        help="Path to worker-server YAML config",
    )
    return parser.parse_args()


def main() -> None:
    server = RevitHTTPServer(
        worker=RevitCodeGeneratorWorker(), 
        config_path=parse_args().config
    ) 
    server.run_loop(killer=GracefulKiller(server.logger))


if __name__ == "__main__":
    main()
