# Revit c воркером

## Зависимости
- Python 3.11.13

## Виртуальное окружение

В проекте используется виртуальное окружение, созданное через `uv`.

Активация:

```zsh
source .venv/bin/activate
```

Деактивация:

```zsh
deactivate
```

Для установки новой зависимости используйте `uv pip install`. Пример:

```zsh
uv pip install requests
```

Если окружение не активировано, можно явно указать установку в проектное окружение:

```zsh
uv pip install --python .venv/bin/python requests
```

### Проверка Python внутри окружения

```zsh
python --version
```

или без активации:

```zsh
.venv/bin/python --version
```

## Revit worker

Воркер находится в файле `run_revit_worker.py`. Он использует локальный пакет
`worker-server` для получения задач от бэкенда и запускает
`revit_code_generator/execute_revit_workflow.py` для генерации Revit-кода через
LLM.

Запускать команды нужно из корня репозитория.
### Конфигурация

Основная конфигурация воркера лежит в `revit_worker.yaml`:

```yaml
base_domain: "https://backend.example.com"
model_id: "revit_code_generator"
default_params: {}
delay: 5
connection_error_delay: 10
max_http_retries: 3
log_level: "INFO"
mtls_enabled: false
mtls_cert_path: null
ssl_verify: true
```

Главные параметры:

- `base_domain` - адрес backend-сервиса, откуда воркер забирает задачи и куда отправляет результат.
- `model_id` - идентификатор модели/воркера для backend.
- `delay` - пауза между опросами задач в секундах.
- `log_level` - уровень логирования.
- `mtls_enabled`, `mtls_cert_path`, `ssl_verify` - настройки TLS/mTLS для backend.

Для локального тестирования используется `revit_worker.local.yaml`:

```yaml
base_domain: "http://127.0.0.1:8008"
model_id: "revit_code_generator"
default_params: {}
delay: 1
connection_error_delay: 2
max_http_retries: 1
log_level: "INFO"
mtls_enabled: false
mtls_cert_path: null
ssl_verify: true
```

### Запуск воркера

Для запуска с реальным backend:

```zsh
uv run python run_revit_worker.py --config revit_worker.yaml
```

Для запуска с локальным mock backend:

```zsh
uv run python run_revit_worker.py --config revit_worker.local.yaml
```

Воркер всегда вызывает реальный LLM workflow. Перед запуском должны быть
настроены переменные окружения и credentials, которые требуются
`revit_code_generator/execute_revit_workflow.py`.

### Входной интерфейс

Backend передает воркеру задачу через `worker-server`. Поле `data` задачи должно
иметь следующий формат:

```json
{
  "files": null,
  "params": {
    "question": "Create a wall in Revit"
  }
}
```

Обязательное поле:

- `params.question` - текстовый запрос пользователя, по которому нужно
  сгенерировать Revit-код.

Необязательные поля:

- `params.thread_id` - идентификатор thread/session для workflow.
- `params.session_id` - альтернативный идентификатор session.
- `files` - список файлов, если backend передает вложения. Если файлов нет,
  допустимо передавать `null`; runner воркера преобразует это в пустой список
  перед внутренней обработкой `worker-server`.

Пример полной задачи, которую возвращает backend на pull-запрос воркера:

```json
{
  "request_id": "backend-request-id",
  "trace_id": "backend-trace-id",
  "data": {
    "files": null,
    "params": {
      "question": "Create a wall in Revit",
      "thread_id": "revit-thread-1"
    }
  }
}
```

### Выходной интерфейс

Метод `inference()` воркера возвращает словарь, который `worker-server`
кладет в поле `data` финального ответа:

```json
{
  "question": "Create a wall in Revit",
  "thread_id": "revit-thread-1",
  "script": "...generated Revit code...",
  "script_explanation": "...model explanation...",
  "errors": null,
  "events": [
    {
      "event": "node_update",
      "node": "🤖 Генерация Revit скрипта",
      "payload": {
        "script": "...generated Revit code...",
        "script_explanation": "...model explanation...",
        "errors": null
      },
      "timestamp": 1779658123.123,
      "thread_id": "revit-thread-1"
    }
  ]
}
```

Финальный ответ, который `worker-server` отправляет в backend:

```json
{
  "data": {
    "question": "Create a wall in Revit",
    "thread_id": "revit-thread-1",
    "script": "...generated Revit code...",
    "script_explanation": "...model explanation...",
    "errors": null,
    "events": []
  },
  "request_id": "backend-request-id",
  "worker_id": "worker-generated-id",
  "status": "DONE",
  "message": null
}
```

Если во время обработки возникает ошибка, `worker-server` отправляет:

```json
{
  "data": null,
  "request_id": "backend-request-id",
  "worker_id": "worker-generated-id",
  "status": "FAIL",
  "message": "error text"
}
```

### Локальное тестирование через mock backend

Mock backend находится в `mock_worker_backend.py`. Он реализует минимальные
эндпоинты, которые использует `worker-server`:

- `POST /worker-adapter/api/v1/tasks/pull` - выдача задачи воркеру.
- `POST /worker-adapter/api/v1/tasks/complete` - прием финального результата.
- `POST /worker-adapter/api/v1/tasks/intermediate` - прием промежуточного результата.
- `POST /frontend/request` - вспомогательный эндпоинт для имитации запроса с frontend.
- `GET /results` - просмотр результатов, которые отправил воркер.
- `GET /health` - проверка состояния mock backend.

1. Запустить mock backend:

```zsh
uv run python mock_worker_backend.py --port 8008
```

2. В другом терминале запустить воркер:

```zsh
uv run python run_revit_worker.py --config revit_worker.local.yaml
```

3. В третьем терминале отправить запрос как будто с frontend:

```zsh
uv run python -c "import requests; print(requests.post('http://127.0.0.1:8008/frontend/request', json={'question': 'Create a wall in Revit'}).text)"
```

Также можно отправить запрос в формате с `params`:

```zsh
uv run python -c "import requests; print(requests.post('http://127.0.0.1:8008/frontend/request', json={'params': {'question': 'Create a wall in Revit'}}).text)"
```

4. Проверить результат, отправленный воркером:

```zsh
uv run python -c "import requests; print(requests.get('http://127.0.0.1:8008/results').text)"
```

В ответе ожидается элемент в списке `results`, внутри которого payload имеет
`status: "DONE"` и поле `data.script` с Revit-кодом. Если LLM credentials или
переменные окружения не настроены, результат будет `status: "FAIL"` с текстом
ошибки в поле `message`.
