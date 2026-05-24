import asyncio
import textwrap

from langchain_core.messages import AIMessage
from rich import print
from rich.panel import Panel

from graph.states.graph_state import GraphState
from graph.nodes.node_lib.base_node import BaseNode
from utils.code import clean_llm_code
from utils.logger import logger


class NaturalLanguageInterpreter(BaseNode):
    """ Node that interprets the script result in natural language given the script result. """
    async def pre_hook(self, _: GraphState) -> None:
        self.log_banner()

    async def core_logic(self, node_input: GraphState) -> GraphState:
        user_msg = node_input.user_messages[0].content
        message = f"User question: {user_msg}\nscript result: {node_input.script_result}\nIs maximum allowed generation attempts achieved: {node_input.max_generation_attempts_achieved}"
        logger.info(f"⚪ Input: {textwrap.fill(message, width=150)}")
        interpretation_raw = await self.call_llm_client(message=message)
        interpretation_text = getattr(interpretation_raw, "content", interpretation_raw)
        interpretation = clean_llm_code(str(interpretation_text))

        return GraphState(
            user_messages=node_input.user_messages,
            script=node_input.script,
            script_explanation=node_input.script_explanation,
            script_result=node_input.script_result,
            response_interpretation=interpretation,
            num_of_generation_attempts=node_input.num_of_generation_attempts,
            max_generation_attempts_achieved=node_input.max_generation_attempts_achieved,
    )

    async def test_logic(self, node_input: GraphState) -> GraphState:
        user_msg = node_input.user_messages[0].content
        message = f"User question: {user_msg}\nscript result: {node_input.script_result}"
        logger.info(f"Test user message: {message}")
        await asyncio.sleep(delay=0.1)
        interpretation = AIMessage(content="Test interpretation.")
        logger.info(f"Interpretation: {interpretation.content}")

        return GraphState(
            user_messages=node_input.user_messages,
            script=node_input.script,
            script_explanation=node_input.script_explanation,
            script_result=node_input.script_result,
            response_interpretation=interpretation.content,
            num_of_generation_attempts=node_input.num_of_generation_attempts,
            max_generation_attempts_achieved=node_input.max_generation_attempts_achieved,
    )

    async def post_hook(self, node_output: GraphState) -> None:
        logger.info(f"⚪ Answer: {textwrap.fill(node_output.response_interpretation, width=100)}")
        print(
            Panel(
                f"{node_output.response_interpretation}", 
                title=f"{self.name}", 
                title_align="left", 
                expand=False
            )
        )
        print("\n")

    def chainlit_output_render_step(self, node_output: dict) -> str:
        interp = node_output.get("response_interpretation")
        return f"**Interpretation:** {interp}" if interp else "(no interpretation)"
