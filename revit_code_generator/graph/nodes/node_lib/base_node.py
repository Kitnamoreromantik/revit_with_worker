import asyncio
import traceback
import os
from copy import deepcopy

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Sequence, Union

import chainlit as cl

from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage, AIMessage
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel

from graph.states.graph_state import GraphState
from utils.logger import logger, log_banner
from llm.factory import client_builders


PROMPTS_LOCATION = Path(__file__).resolve().parents[2] / "prompts"


class RetryPolicy(BaseModel):
    attempts: int = 2
    backoff_sec: float = 0.5


class BaseNode(ABC):
    name = "🤖 Abstract node"
    sys_prompt_name = None
    usr_prompt_template_name = None

    def __init__(
        self,
        name: Optional[str] = None,
        sys_prompt_name: Optional[str] = None,
        sys_prompt_injections: Optional[dict] = None,
        usr_prompt_template_name: Optional[str] = None,
        llm_id: Optional[str] = None,
        temperature=None,
        max_tokens=None,
        structured_output_schema: Optional[BaseModel] = None,
        retry_policy: RetryPolicy = RetryPolicy(),
        test_mode: bool = False,
        session_context_variable=None,
        validate_output: bool = False,
        timeout_sec: Optional[float] = None,
    ):
        self.name = name or self.__class__.name
        self.sys_prompt_name = sys_prompt_name or self.__class__.sys_prompt_name
        self.sys_prompt = None
        self.sys_prompt_injections = sys_prompt_injections
        self.usr_prompt_template_name = usr_prompt_template_name or self.__class__.usr_prompt_template_name
        self.llm_id = llm_id
        self.llm_settings = {
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        self.structured_output_schema = structured_output_schema
        self.retry_policy = retry_policy
        self.test_mode = test_mode
        self.session_context_variable = session_context_variable
        self.validate_output = validate_output
        self.timeout_sec = timeout_sec
        self.number_of_calls = 0

        def _find_prompt_file(prompt_name: str, folder: Path) -> Optional[Path]:
            matches = list(folder.glob(f"{prompt_name}.*"))
            return matches[0] if matches else None

        if self.sys_prompt_name:
            self.sys_prompt_path = _find_prompt_file(self.sys_prompt_name, PROMPTS_LOCATION)
            if self.sys_prompt_path is None:
                raise FileNotFoundError(f"No prompt file found for: {self.sys_prompt_name}")
            with open(self.sys_prompt_path, "r", encoding="utf-8") as f:
                self.sys_prompt = f.read()

            def resolve_prompt_injections(injection_dict: dict[str, str]) -> dict[str, str]:
                resolved = {}
                for key, path in injection_dict.items():
                    path = Path(path)
                    if path.exists() and path.is_file():
                        resolved[key] = path.read_text(encoding="utf-8").strip()
                    else:
                        raise FileNotFoundError(f"Injection key '{key}' expected file at: {path}")
                return resolved

            if self.sys_prompt_injections:
                resolved = resolve_prompt_injections(self.sys_prompt_injections)
                self.sys_prompt = self.sys_prompt.format(**resolved)

        if self.usr_prompt_template_name:
            self.usr_prompt_template_path = _find_prompt_file(self.usr_prompt_template_name, PROMPTS_LOCATION)
            if self.usr_prompt_template_path is None:
                raise FileNotFoundError(f"No prompt file found for: {self.usr_prompt_template_name}")
            with open(self.usr_prompt_template_path, "r", encoding="utf-8") as f:
                self.usr_prompt_template = PromptTemplate.from_template(f.read())

        def _get_llm_client(model_id: str, **kwargs):
            provider, _, name = model_id.partition(":")
            try:
                builder = client_builders[provider.lower()]
            except KeyError:
                raise ValueError(f"Unknown LLM provider '{provider}'")
            return builder(name, **kwargs)

        if self.llm_id is None:
            self.llm_client = None
        else:
            client = _get_llm_client(self.llm_id, **self.llm_settings)
            print(f"Structured output schema for LLM client {self.name}: {self.structured_output_schema}.")
            if self.structured_output_schema:
                self.llm_client = client.with_structured_output(self.structured_output_schema)
            else:
                self.llm_client = client

    # async def __call__(self, state: GraphState) -> GraphState:
    #     """
    #     Node entrypoint.
    #     Creates Chainlit step BEFORE node execution and updates the same step AFTER execution.
    #     """
    #     await self._increment_num_node_calls()

    #     async with cl.Step(name=self.name) as step:
    #         try:
    #             step.output = f"⚙️ Выполняется **{self.name}**..."
    #             await step.update()

    #             await self.pre_hook(state)

    #             output = await self._run_node(state)

    #             await self.post_hook(output)

    #             rendered = self._safe_chainlit_render(output)
    #             if rendered and len(rendered) > 12000:
    #                 rendered = rendered[:12000] + "\n\n... [truncated]"

    #             step.output = rendered or f"✅ Шаг **{self.name}** завершён."
    #             await step.update()

    #             return output

    #         except Exception as exc:
    #             logger.exception(f"Unhandled error in node {self.name}: {exc}")
    #             err_text = f"❌ Ошибка в шаге **{self.name}**:\n\n{exc}"

    #             try:
    #                 step.output = err_text
    #                 await step.update()
    #             except Exception:
    #                 pass

    #             if hasattr(state, "model_copy"):
    #                 failed_state = state.model_copy(update={"errors": str(exc)})
    #             elif hasattr(state, "copy"):
    #                 failed_state = state.copy(update={"errors": str(exc)})
    #             else:
    #                 failed_state = deepcopy(state)
    #                 failed_state.errors = str(exc)

    #             return failed_state



    # async def __call__(self, state: GraphState) -> GraphState:
    #     await self._increment_num_node_calls()

    #     async with cl.Step(name=self.name) as step:
    #         try:
    #             logger.info(f"[{self.name}] Step opened")
    #             step.output = f"⚙️ Выполняется шаг **{self.name}**..."
    #             await step.update()
    #             logger.info(f"[{self.name}] Initial step.update() done")

    #             await self.pre_hook(state)
    #             logger.info(f"[{self.name}] pre_hook done")

    #             output = await self._run_node(state)
    #             logger.info(f"[{self.name}] _run_node done")

    #             if getattr(output, "errors", None):
    #                 logger.info(f"[{self.name}] output contains errors")
    #                 step.output = f"❌ Шаг **{self.name}** завершился с ошибкой:\n\n{output.errors}"
    #                 await step.update()
    #                 logger.info(f"[{self.name}] error step.update() done")
    #                 await self.post_hook(output)
    #                 logger.info(f"[{self.name}] post_hook done after errors")
    #                 return output

    #             await self.post_hook(output)
    #             logger.info(f"[{self.name}] post_hook done")

    #             rendered = self._safe_chainlit_render(output)
    #             logger.info(f"[{self.name}] render done, length={len(rendered) if rendered else 0}")

    #             if rendered and len(rendered) > 15000:
    #                 rendered = rendered[:15000] + "\n\n... [truncated]"
    #                 logger.info(f"[{self.name}] render truncated")

    #             step.output = rendered or f"✅ Шаг **{self.name}** завершён."
    #             logger.info(f"[{self.name}] before final step.update()")

    #             await asyncio.wait_for(step.update(), timeout=10)
    #             logger.info(f"[{self.name}] final step.update() done")

    #             return output

    #         except Exception as exc:
    #             logger.exception(f"Unhandled error in node {self.name}: {exc}")
    #             try:
    #                 step.output = f"❌ Ошибка в шаге **{self.name}**:\n\n{exc}"
    #                 await asyncio.wait_for(step.update(), timeout=5)
    #             except Exception:
    #                 logger.exception(f"[{self.name}] failed to update error step")

    #             if hasattr(state, "model_copy"):
    #                 failed_state = state.model_copy(update={"errors": str(exc)})
    #             elif hasattr(state, "copy"):
    #                 failed_state = state.copy(update={"errors": str(exc)})
    #             else:
    #                 failed_state = deepcopy(state)
    #                 failed_state.errors = str(exc)

    #             return failed_state
            
    async def __call__(self, state: GraphState) -> GraphState:
        await self._increment_num_node_calls()

        try:
            logger.info(f"[{self.name}] started")

            await self.pre_hook(state)
            logger.info(f"[{self.name}] pre_hook done")

            output = await self._run_node(state)
            logger.info(f"[{self.name}] _run_node done")

            if getattr(output, "errors", None):
                logger.warning(f"[{self.name}] output contains errors: {output.errors}")

            await self.post_hook(output)
            logger.info(f"[{self.name}] post_hook done")

            return output

        except Exception as exc:
            logger.exception(f"Unhandled error in node {self.name}: {exc}")

            if hasattr(state, "model_copy"):
                failed_state = state.model_copy(update={"errors": str(exc)})
            elif hasattr(state, "copy"):
                failed_state = state.copy(update={"errors": str(exc)})
            else:
                failed_state = deepcopy(state)
                failed_state.errors = str(exc)

            return failed_state

    def _safe_chainlit_render(self, node_output: GraphState) -> str:
        """
        Safe renderer for Chainlit step output.
        """
        try:
            rendered = self.chainlit_output_render_step(node_output)
            if rendered is None:
                return ""
            return str(rendered)
        except Exception as exc:
            logger.exception(f"chainlit_output_render_step failed in node {self.name}: {exc}")

        try:
            if hasattr(node_output, "model_dump"):
                return str(node_output.model_dump())
            if hasattr(node_output, "dict"):
                return str(node_output.dict())
            return str(node_output)
        except Exception:
            return f"✅ Шаг **{self.name}** завершён."

    async def _run_node(self, input: GraphState) -> GraphState:
        err_msg = "Unknown node execution error."

        for i in range(1, self.retry_policy.attempts + 1):
            try:
                if self.timeout_sec:
                    if self.test_mode:
                        output = await asyncio.wait_for(self.test_logic(input), timeout=self.timeout_sec)
                    else:
                        output = await asyncio.wait_for(self.core_logic(input), timeout=self.timeout_sec)
                else:
                    if self.test_mode:
                        output = await self.test_logic(input)
                    else:
                        output = await self.core_logic(input)

                if self.validate_output:
                    output = await self._validate_and_fix(output)

                logger.info(f"🟢 Run successfully: node: {self.name}. Node execution attempts: {i}")
                return output

            except Exception as err:
                tb = traceback.extract_tb(err.__traceback__)
                filename, lineno, func, _ = tb[-1]
                short_file = os.path.basename(filename)
                err_loc = f"{func}(): {err}"
                err_msg = (
                    f"🔴 Node {self.name} failed after execution attempt: {i}, "
                    f"at {short_file}: {lineno} in {err_loc}."
                )
                logger.error(err_msg)

                if i < self.retry_policy.attempts:
                    await asyncio.sleep(self.retry_policy.backoff_sec)

        if hasattr(input, "model_copy"):
            failed_state = input.model_copy(update={"errors": err_msg})
        elif hasattr(input, "copy"):
            failed_state = input.copy(update={"errors": err_msg})
        else:
            failed_state = deepcopy(input)
            failed_state.errors = err_msg

        return failed_state

    @abstractmethod
    async def core_logic(self, input: GraphState) -> GraphState:
        ...

    @abstractmethod
    async def test_logic(self, input: GraphState) -> GraphState:
        ...

    @abstractmethod
    async def pre_hook(self, input: GraphState) -> None:
        ...

    @abstractmethod
    async def post_hook(self, output: GraphState) -> None:
        ...

    async def _validate_and_fix(self, output: GraphState) -> GraphState:
        ...

    async def _increment_num_node_calls(self) -> int:
        self.number_of_calls += 1
        return self.number_of_calls

    async def call_llm_client(
        self,
        *,
        messages: Optional[Sequence[BaseMessage]] = None,
        message: Optional[Union[str, HumanMessage]] = None,
        image_url: Optional[str] = None,
    ):
        """
        Unified LLM call that supports:
        1) LangChain text-only and vision-input models
        2) OpenRouter image-generation models
        """
        def _is_effectively_empty(obj) -> bool:
            if obj is None:
                return True
            if isinstance(obj, str):
                return obj.strip() == ""
            if isinstance(obj, dict):
                return len(obj) == 0 or all(_is_effectively_empty(v) for v in obj.values())
            if isinstance(obj, (list, tuple, set)):
                return len(obj) == 0 or all(_is_effectively_empty(v) for v in obj)
            if hasattr(obj, "__dict__"):
                vals = vars(obj).values()
                return len(list(vals)) == 0 or all(_is_effectively_empty(v) for v in vals)
            return False

        def _extract_text_and_image_url(user_msg) -> tuple[str, str | None]:
            if isinstance(user_msg.content, str):
                return user_msg.content, None

            text = ""
            img_url = None
            for part in user_msg.content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text += part.get("text", "")
                if isinstance(part, dict) and part.get("type") == "image_url":
                    iu = part.get("image_url")
                    if isinstance(iu, dict):
                        img_url = iu.get("url")
                    elif isinstance(iu, str):
                        img_url = iu
            return text.strip(), img_url

        if self.llm_id and self.llm_id.startswith("openrouter_image:"):
            openai_messages = []

            if messages is not None:
                for msg in messages:
                    if isinstance(msg.content, list):
                        text_parts = []
                        for part in msg.content:
                            if part.get("type") == "text":
                                text_parts.append(part["text"])
                        openai_messages.append({
                            "role": "user",
                            "content": "\n".join(text_parts),
                        })
                    else:
                        openai_messages.append({
                            "role": "user",
                            "content": str(msg.content),
                        })
            else:
                if isinstance(message, str):
                    openai_messages.append({
                        "role": "user",
                        "content": message,
                    })
                elif isinstance(message, HumanMessage):
                    openai_messages.append({
                        "role": "user",
                        "content": str(message.content),
                    })
                else:
                    raise ValueError("Image-generation models require text instructions.")

            response = self.llm_client.chat.completions.create(
                model=self.llm_id.split(":", 1)[1],
                messages=openai_messages,
                extra_body={"modalities": ["image", "text"]},
            )

            message = response.choices[0].message

            if not getattr(message, "images", None):
                raise RuntimeError("Image-generation model returned no images.")

            return message

        if self.llm_id and self.llm_id.startswith("gigachat:"):
            if messages is not None:
                user_msg = messages[-1]
                prompt, _ = _extract_text_and_image_url(user_msg)
                raw_images = (user_msg.additional_kwargs or {}).get("raw_images", [])
            else:
                prompt = message if isinstance(message, str) else str(message.content)
                raw_images = []

            giga_messages = []
            if self.sys_prompt and self.sys_prompt.strip():
                giga_messages.append({"role": "system", "content": self.sys_prompt})

            if raw_images:
                import base64
                import io
                from pathlib import Path

                img0 = raw_images[0]
                data = base64.b64decode(img0["data_b64"])
                filename = img0.get("name") or "image.jpg"

                mime = img0.get("mime") or "image/jpeg"
                ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime, ".jpg")
                if Path(filename).suffix.lower() not in [".jpg", ".jpeg", ".png", ".webp"]:
                    filename = f"image{ext}"

                f = io.BytesIO(data)
                f.name = filename

                uploaded = await self.llm_client.aupload_file(f)
                file_id = uploaded.id_ if hasattr(uploaded, "id_") else uploaded["id"]

                giga_messages.append({
                    "role": "user",
                    "content": prompt,
                    "attachments": [file_id],
                })
            else:
                giga_messages.append({"role": "user", "content": prompt})

            resp = await self.llm_client.achat({"messages": giga_messages, "temperature": 1.0})
            text = resp.choices[0].message.content

            if self.structured_output_schema:
                return self.structured_output_schema.model_validate_json(text)

            return text

        if self.llm_id and self.llm_id.startswith("gigachat_image:"):
            response = self.llm_client.chat(messages).choices[0].message.content
            return response

        if messages is not None:
            payload = list(messages)
        else:
            if message is None:
                raise ValueError("call_llm_client requires either messages=... or message=...")

            if isinstance(message, HumanMessage):
                payload = [message]
            elif isinstance(message, str):
                if image_url:
                    content = [
                        {"type": "text", "text": message},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ]
                    payload = [HumanMessage(content=content)]
                else:
                    payload = [HumanMessage(content=message)]
            else:
                raise TypeError(f"Unsupported message type: {type(message)}")

        final_payload: list[BaseMessage] = []
        if self.sys_prompt and isinstance(self.sys_prompt, str) and self.sys_prompt.strip():
            final_payload.append(SystemMessage(content=self.sys_prompt))
        final_payload.extend(payload)

        llm_response = await self.llm_client.ainvoke(final_payload)

        if _is_effectively_empty(llm_response):
            raise RuntimeError("LLM returned an empty or partially empty response!")

        return llm_response

    def log_banner(self):
        log_banner(f"NODE: {self.name}", fill='-', width=40)

    def increment_context_variable(self, var_name: str, delta: int = 1) -> int:
        current_value = self.session_context_variable.get(var_name)
        new_value = current_value + delta
        self.session_context_variable.set(var_name, new_value)
        return new_value

    @abstractmethod
    def chainlit_output_render_step(self, node_output: GraphState) -> str:
        """
        Renderer of node output for Chainlit UI.
        """
        ...
