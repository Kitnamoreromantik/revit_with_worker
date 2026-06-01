from pathlib import Path
import tempfile
from typing import Any, Dict
import unittest
from unittest.mock import patch

from run_revit_worker import RevitHTTPServer, WorkerProtocol


class EmptyWorker(WorkerProtocol):
    def inference(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return data


def _write_config(
    tmp_path: Path,
    *,
    mtls_enabled: bool = True,
    mtls_cert_path: str | None,
    ssl_verify: bool | str,
) -> Path:
    config_path = tmp_path / "worker.yaml"
    config_path.write_text(
        "\n".join(
            [
                'base_domain: "https://backend.example.com"',
                'model_id: "revit-model"',
                "default_params: {}",
                "delay: 5",
                "connection_error_delay: 10",
                "max_http_retries: 3",
                'log_level: "INFO"',
                f"mtls_enabled: {str(mtls_enabled).lower()}",
                f"mtls_cert_path: {mtls_cert_path!r}" if mtls_cert_path else "mtls_cert_path: null",
                f"ssl_verify: {ssl_verify!r}" if isinstance(ssl_verify, str) else f"ssl_verify: {str(ssl_verify).lower()}",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


class RevitWorkerTLSTest(unittest.TestCase):
    def test_revit_worker_consumes_certificates_for_all_http_sessions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            client_cert = tmp_path / "client.pem"
            ca_bundle = tmp_path / "ca.pem"
            client_cert.write_text("client certificate", encoding="utf-8")
            ca_bundle.write_text("ca certificate", encoding="utf-8")
            config_path = _write_config(
                tmp_path,
                mtls_cert_path=str(client_cert),
                ssl_verify=str(ca_bundle),
            )

            server = RevitHTTPServer(worker=EmptyWorker(), config_path=str(config_path))

            self.assertEqual(server.session.cert, str(client_cert))
            self.assertEqual(server.session.verify, str(ca_bundle))
            self.assertEqual(server.file_handler.session.cert, str(client_cert))
            self.assertEqual(server.file_handler.session.verify, str(ca_bundle))

    def test_revit_worker_rejects_unconsumed_certificate_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            client_cert = tmp_path / "client.pem"
            ca_bundle = tmp_path / "ca.pem"
            client_cert.write_text("client certificate", encoding="utf-8")
            ca_bundle.write_text("ca certificate", encoding="utf-8")
            config_path = _write_config(
                tmp_path,
                mtls_cert_path=str(client_cert),
                ssl_verify=str(ca_bundle),
            )
            original_validate = RevitHTTPServer._validate_tls_consumed

            def break_file_session_tls(self):
                self.file_handler.session.cert = None

            with patch.object(RevitHTTPServer, "_validate_tls_consumed", break_file_session_tls):
                server = RevitHTTPServer(worker=EmptyWorker(), config_path=str(config_path))

            with self.assertRaisesRegex(RuntimeError, "file session mTLS certificate"):
                original_validate(server)
