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