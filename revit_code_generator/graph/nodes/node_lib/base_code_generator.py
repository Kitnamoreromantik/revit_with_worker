# nodes/base_code_generator.py
import asyncio
import textwrap

import chainlit as cl
from dataclasses import replace
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from langchain_core.messages import AIMessage

from graph.states.graph_state import GraphState
from .base_node import BaseNode
from utils.logger import logger
from utils.code import clean_raw_json_from_llm, wrap_csharp_code


class CodeGeneratorOutput(BaseModel):
    """Universal output schema for any code generator."""
    code: str | None = None
    code_explanation: str | None = None


class CodeGeneratorBaseNode(BaseNode):
    """
    Base class for any LLM-based code generator.
    Child classes should override:
        - LANGUAGE_ID (e.g. 'csharp', 'cypher', 'python')
        - STRUCURED_OUTPUT_SCHEMA (Pydantic model)
        - Optional: core_logic()
        - Optional: test_logic()
        - Optional: construct_prompt()
        - Optional: parse_llm_output()
        - Optional: post_render()
    """

    LANGUAGE_ID = "python"  # used for syntax highlighting
    STRUCTURED_OUTPUT_SCHEMA = CodeGeneratorOutput  # override in subclasses
    TITLE = "Generated Code"  # panel / UI label

    async def pre_hook(self, _: GraphState):
        """Show generation attempt and banner that the node has started."""
        self.log_banner()
        print("\n----------------------------")
        print(f"{'Code-generating agent running'}\n")
        num_of_gen_attempts = self.increment_context_variable("attempts_counter")
        # await cl.Message(content=f"Generation attempt: {num_of_gen_attempts}", author="tool").send()


    async def core_logic(self, state):
        """
        General logic: 
        build prompt -> call LLM -> parse code and explanation -> update and return GraphState.
        Child code generation classes can override this core logic.
        """
        prompt = self.construct_prompt(state)
        print(prompt)
        llm_response = await self.call_llm_client(message=prompt)
        result = self.parse_llm_output(llm_response)
        return self.pack_into_state(state, result)


    async def test_logic(self, state):
        """Mock logic of the code generator node for test purposes."""
        await asyncio.sleep(0.2) # simulate some delay
        mock_code = f"# mock {self.LANGUAGE_ID} script"
        mock_explanation = "test explanation"

        return self.pack_into_state(state,
            self.STRUCTURED_OUTPUT_SCHEMA(
                code=mock_code,
                code_explanation=mock_explanation
            )
        )


    def construct_prompt(self, state) -> str:
        """Default code generation prompt builder. Children may override it."""
        prompt = state.user_messages[-1].content
        if getattr(state, "script_evaluation", None):
            prompt += (
                f"\nPreviously generated code:\n{state.script}\n"
                f"Review this code received:\n{state.script_evaluation}\n"
                "Fix errors if present. Think before answering!"
            )
        if getattr(state, "script_feedback", None):
            prompt += f"\nFeedback on this code:\n{state.script_feedback}"
        return prompt


    def parse_llm_output(self, llm_response) -> CodeGeneratorOutput:
        """
        Handles both structured JSON and plain AIMessage if LLM does not support structured output.
        NOTE: Giga uses backticks inconsistently -> near JSON output str pain!

        Subclasses can override for custom quirks.
        """
        code_processor = wrap_csharp_code if self.LANGUAGE_ID == "csharp" else lambda x: x

        if isinstance(llm_response, AIMessage): # if GigaChat-like AIMessage
            llm_response_cleaned = clean_raw_json_from_llm(llm_response.content)
            code = llm_response_cleaned.get("code")
            code = code_processor(code)
            explanation = llm_response_cleaned.get("code_explanation") or llm_response_cleaned.get("explanation")
        else: # else if normal structured JSON from LLM like in qwen
            code = getattr(llm_response, "code", None)
            explanation = getattr(llm_response, "code_explanation", None)

        return self.STRUCTURED_OUTPUT_SCHEMA(
            code=code if code else None,
            code_explanation=explanation,
        )


    def pack_into_state(self, state, result: CodeGeneratorOutput):
        """Update workflow state (GraphState) with the node's output."""
        return replace(state,
            num_of_generation_attempts=self.session_context_variable.get("attempts_counter", 101),
            script=result.code,
            script_explanation=result.code_explanation
        )


    async def post_hook(self, state):
        """Console and logger pretty-print of the results."""
        console = Console()
        attempts = state.num_of_generation_attempts

        if state.errors:
            console.print(Panel(state.errors, title=f"{self.name}. Attempts {attempts}"))
            logger.error(state.errors)

        if state.script:
            code_syntax = Syntax(state.script, self.LANGUAGE_ID, theme="monokai", line_numbers=True, word_wrap=True)
            console.print(Panel(code_syntax, title= f"{self.name}. Attempts: {attempts}", title_align="left", expand=False, width=170))
            logger.info(f"⚪ LLM-generated code (generation attempt {attempts}):\n{state.script}\n")
            
        if state.script_explanation:
            console.print(Panel(state.script_explanation, title="script justfication", title_align="left", expand=False))
            logger.info(f"⚪ LLM-generated code explanation:\n{textwrap.fill(state.script_explanation, width=100)}")

        else:
            console.print(Panel("Nothing got from LLM generating node.", title= f"{self.name}. Attempts: {attempts}", title_align="left"))
            logger.warning("No code generated")


    def chainlit_output_render_step(self, node_output: dict) -> str:
        strings_to_display = []

        if script := node_output.get("script"):
            strings_to_display.append(f"**Synthesized code:**\n```{self.LANGUAGE_ID}\n{script}\n```")

        if expl := node_output.get("script_explanation"):
            strings_to_display.append(f"**Code explanation:**\n{expl}")

        if err := node_output.get("errors"):
            strings_to_display.append(f"**Error:** {err}")
        
        if not node_output.get("script") and not node_output.get("script_explanation") and not node_output.get("errors"):
            strings_to_display.append("Nothing has returned from node")

        return "\n\n".join(strings_to_display)
