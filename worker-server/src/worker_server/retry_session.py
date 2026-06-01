import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Union


class RetrySession:
    def __init__(
        self, 
        retries: int = 10, 
        backoff_factor: float = 0.3,
        mtls_enabled: bool = False,
        mtls_cert_path: Optional[str] = None,
        ssl_verify: Union[bool, str] = True
    ):
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.mtls_enabled = mtls_enabled
        self.mtls_cert_path = mtls_cert_path
        self.ssl_verify = ssl_verify
        self.session = self._create_retry_session()

    def _create_retry_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=self.retries,
            read=self.retries,
            connect=self.retries,
            backoff_factor=self.backoff_factor,
            allowed_methods=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        
        # Настройка mTLS если включен
        if self.mtls_enabled:
            if not self.mtls_cert_path:
                raise ValueError("mtls_cert_path must be provided when mtls_enabled is True")
            if not os.path.exists(self.mtls_cert_path):
                raise FileNotFoundError(f"mTLS certificate file not found: {self.mtls_cert_path}")
            session.cert = self.mtls_cert_path
        
        # Настройка SSL верификации
        # Если ssl_verify - строка (путь к CA bundle), проверяем существование файла
        if isinstance(self.ssl_verify, str):
            if not os.path.exists(self.ssl_verify):
                raise FileNotFoundError(f"SSL CA bundle file not found: {self.ssl_verify}")
        
        session.verify = self.ssl_verify
        
        return session

    def get_session(self) -> requests.Session:
        return self.session
