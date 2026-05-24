from __future__ import annotations

import os
from base64 import b64encode
from typing import Callable

from dotenv import find_dotenv, load_dotenv
# from langchain_gigachat.chat_models.gigachat import GigaChat
from gigachat import GigaChat
from langchain_openai import ChatOpenAI  # For OpenRouter via OpenAI-compatible interface
from openai import OpenAI

# Load environment variables
load_dotenv(find_dotenv())
gpt_api_key = os.getenv("OPENAI_API_KEY")
fm_api_key = os.getenv("FOUNDATION_MODELS_API_KEY")
giga_client_id = os.getenv("GIGA_CLIENT_ID")
giga_auth_key = os.getenv("GIGA_AUTH_KEY")
giga_scope = os.getenv("GIGA_SCOPE", "GIGACHAT_API_PERS")
openrouter_key = os.getenv("OPENROUTER_KEY")

client_builders: dict[str, Callable[[str], object]] = {}

def _try_get_chainlit_user_env(name: str) -> str | None:
    """
    Read user-provided env var from Chainlit UI (project.user_env),
    if we are inside a Chainlit request context. Otherwise return None.
    """
    try:
        import chainlit as cl  # local import: doesn't hard-require Chainlit outside UI runs
    except Exception:
        return None

    try:
        env = cl.user_session.get("env") or {}
    except Exception:
        # Not in a Chainlit context (e.g., CLI / unit tests / import time)
        return None

    val = env.get(name)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _build_gigachat(model_name: str, **kwargs) -> GigaChat:
    # Priority: explicit kwargs -> Chainlit UI user_env -> OS env fallback
    
    # api_key = kwargs.pop("api_key", None) or _try_get_chainlit_user_env("GIGA_AUTH_KEY") or giga_auth_key.strip()
    # scope = kwargs.pop("scope", None) or _try_get_chainlit_user_env("GIGA_SCOPE") or giga_scope.strip()

    # api_key = kwargs.pop("api_key", None) or _try_get_chainlit_user_env("GIGA_AUTH_KEY")
    # scope = kwargs.pop("scope", None) or _try_get_chainlit_user_env("GIGA_SCOPE")

    api_key = (
        kwargs.pop("api_key", None)
        or _try_get_chainlit_user_env("GIGA_AUTH_KEY")
        or (giga_auth_key or "None").strip()
    )
    scope = (
        kwargs.pop("scope", None)
        or _try_get_chainlit_user_env("GIGA_SCOPE")
        or (giga_scope or "None").strip()
    )

    if not api_key:
        raise RuntimeError("GigaChat API key is missing (need GIGA_AUTH_KEY from Chainlit user_env or .env)")
    if not scope:
        raise RuntimeError("GigaChat scope is missing (need GIGA_SCOPE from Chainlit user_env or .env)")

    return GigaChat(
        credentials=api_key,
        scope=scope,
        timeout=600,
        model=model_name,
        verify_ssl_certs=False,
        **kwargs,
    )


def _build_gigachat_image(model_name: str, **kwargs) -> GigaChat:
    # api_key = kwargs.pop("api_key", None) or _try_get_chainlit_user_env("GIGA_AUTH_KEY") or giga_auth_key.strip()
    # scope = kwargs.pop("scope", None) or _try_get_chainlit_user_env("GIGA_SCOPE") or giga_scope.strip()

    api_key = (
        kwargs.pop("api_key", None)
        or _try_get_chainlit_user_env("GIGA_AUTH_KEY")
        or (giga_auth_key or "None").strip()
    )
    scope = (
        kwargs.pop("scope", None)
        or _try_get_chainlit_user_env("GIGA_SCOPE")
        or (giga_scope or "None").strip()
    )

    if not api_key:
        raise RuntimeError("GigaChat API key is missing (need GIGA_AUTH_KEY from Chainlit user_env or .env)")
    if not scope:
        raise RuntimeError("GigaChat scope is missing (need GIGA_SCOPE from Chainlit user_env or .env)")

    return GigaChat(
        credentials=api_key,
        scope=scope,
        timeout=600,
        model=model_name,
        verify_ssl_certs=False,
        **kwargs,
    )

def _build_foundation_models(model_name: str,  **kwargs) -> ChatOpenAI:
    """
    OpenRouter LLM-client builder using OpenAI-compatible interface.
    """
    return ChatOpenAI(
        model=model_name,
        api_key=fm_api_key,
        base_url="https://foundation-models.api.cloud.ru/v1",
        **kwargs
    )

def _build_openrouter(model_name: str,  **kwargs) -> ChatOpenAI:
    """
    OpenRouter LLM-client builder using OpenAI-compatible interface.
    """
    return ChatOpenAI(
        model=model_name,
        api_key=openrouter_key,
        base_url="https://openrouter.ai/api/v1",
        **kwargs
    )

def _build_openrouter_image(model_name: str, **kwargs) -> OpenAI:
    """
    OpenRouter raw client for image-generation models (Nano Banana, Gemini image preview).
    """
    return OpenAI(
        api_key=openrouter_key,
        base_url="https://openrouter.ai/api/v1",
    )

client_builders["gigachat"] = _build_gigachat
client_builders["gigachat_image"] = _build_gigachat_image
client_builders["openrouter"] = _build_openrouter
client_builders["openrouter_image"] = _build_openrouter_image
client_builders["foundationmodels"] = _build_foundation_models


# def get_llm(model_id: str) -> object:
#     """
#     Model getter interface.
#     model_id examples: 'gigachat:GigaChat-2-Max', 'openrouter:openai/gpt-4o-2024-11-20'
#     """
#     provider, _, name = model_id.partition(":")
#     try:
#         builder = client_builders[provider.lower()]
#     except KeyError:
#         raise ValueError(f"Unknown LLM provider '{provider}'")
#     return builder(name)

# def get_llm(model_id: str, **kwargs) -> object:
#     provider, _, name = model_id.partition(":")
#     print(f"Getting LLM for provider: '{provider}' and model '{name}' with kwargs: {kwargs}")
#     try:
#         builder = client_builders[provider.lower()]
#     except KeyError:
#         raise ValueError(f"Unknown LLM provider '{provider}'")
#     return builder(name, **kwargs)

def get_llm(model_id: str, **kwargs) -> object:
    provider, _, name = model_id.partition(":")
    provider_l = provider.lower()

    # Never print secrets
    safe_kwargs = {
        k: ("***" if any(s in k.lower() for s in ("key", "token", "secret", "credentials")) else v)
        for k, v in kwargs.items()
    }
    print(f"Getting LLM for provider: '{provider}' and model '{name}' with kwargs: {safe_kwargs}")

    # Auto-pull key from Chainlit UI for GigaChat if caller didn't pass api_key
    if provider_l in ("gigachat", "gigachat_image"):
        if not kwargs.get("api_key"):
            ui_key = _try_get_chainlit_user_env("GIGA_AUTH_KEY")
            if ui_key:
                kwargs["api_key"] = ui_key
        if not kwargs.get("scope"):
            ui_scope = _try_get_chainlit_user_env("GIGA_SCOPE")
            if ui_scope:
                kwargs["scope"] = ui_scope

    try:
        builder = client_builders[provider_l]
    except KeyError:
        raise ValueError(f"Unknown LLM provider '{provider}'")

    return builder(name, **kwargs)