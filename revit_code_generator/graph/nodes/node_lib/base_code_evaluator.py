import textwrap

from typing import Literal
from rich import print

from rich.console import Console
from rich.panel import Panel
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage
from dataclasses import replace

from graph.states.graph_state import GraphState
from graph.nodes.node_lib.base_node import BaseNode
from utils.logger import logger
from utils.code import clean_raw_json_from_llm


class CodeFeedbackSchema(BaseModel):
    """
    Structured output schema for script-evaluating LLM agent.

    Fields:
        evaluation (Literal["Accept", "Incorrect", "Error or empty"]): 
            - 'Accept' if the script is correct and its outcome answers the user's question.
            - 'Incorrect' if the script runs but is logically flawed, irrelevant, or incomplete.
            - 'Error or empty' if the script fails to execute or returns no data.

        feedback (str): 
            - If evaluation is not 'Accept': explain the problem and how to fix or improve the script.
            - If 'Accept': briefly justify the decision.
    """
    evaluation: Literal["Accept", "Incorrect", "Error or empty"] = Field(
        description="Evaluate the script as either 'Accept' or 'Error or empty' depending on execution result."
    )

    feedback: str = Field(
        description="If not accepted, explain what's wrong and how to fix the script. "
                    "If accepted, briefly justify the verdict."
    )


class ScriptEvaluatorBaseNode(BaseNode):
    """
    Node that evaluates the Revit script with an LLM client, based on the user message, the script,
    its explanation, and the script result from the Revit environment.
    The structured output is used to get from LLM the (1) evaluation and (2) feedback.
    """
    MAX_WORKFLOW_ITERATIONS = 2
    STRUCTURED_OUTPUT_SCHEMA = CodeFeedbackSchema  # override in childs if needed
    TITLE = "Code script critic"

    @staticmethod
    def _format_user_messages(state: GraphState) -> str:
        return "\n".join(str(message.content) for message in state.user_messages)

    async def pre_hook(self, _: GraphState) -> None:
        """Show generation attempt and banner that the node has started."""
        self.log_banner()
        print("\n----------------------------")
        print(f"{'Evaluator agent running'}\n")


    async def core_logic(self, state: GraphState) -> GraphState:
        """
        General logic.
        Child code generation classes can override this core logic.
        """
        prompt = self.usr_prompt_template.format(
            messages=self._format_user_messages(state),
            script=state.script,
            script_explanation=state.script_explanation,
            script_result=state.script_result,
        )
        logger.info(f"⚪ Message to evaluate:\n{textwrap.fill(prompt, width=150)}\n")
        llm_response = await self.call_llm_client(message=prompt)
        result = self.parse_llm_output(llm_response)

        if state.num_of_generation_attempts == self.MAX_WORKFLOW_ITERATIONS:
            is_max_iterations = True
        else:
            is_max_iterations = False

        return self.pack_into_state(state, result, is_max_iterations=is_max_iterations)


    async def test_logic(self, state: GraphState) -> GraphState:
        message = self.usr_prompt_template.format(
            messages=self._format_user_messages(state),
            script=state.script,
            script_explanation=state.script_explanation,
            script_result=state.script_result,
        )
        logger.info(f"⚪ Message to evaluate (test):\n{message}\n")

        # Simulate LLM response for testing purposes
        class MockEvaluation:
            evaluation = "Accept"  # or "Incorrect" or "Error or empty"
            feedback = "The script is test evaluated."
        llm_response = MockEvaluation()

        if state.num_of_generation_attempts == self.MAX_WORKFLOW_ITERATIONS:
            is_max_iterations = True
        else:
            is_max_iterations = False

        result = self.parse_llm_output(llm_response)
        return self.pack_into_state(state, result, is_max_iterations)


    def parse_llm_output(self, llm_response) -> CodeFeedbackSchema:
        """
        Subclasses can override for custom quirks.
        """
        # Accept either a pydantic-like object or a dict-like or gigachat AIMessage
        if isinstance(llm_response, dict):
            evaluation = llm_response.get("evaluation")
            feedback = llm_response.get("feedback")
        elif isinstance(llm_response, AIMessage): # if GigaChat-like AIMessage
            llm_response_cleaned = clean_raw_json_from_llm(llm_response.content)
            evaluation = llm_response_cleaned.get("evaluation")
            feedback = llm_response_cleaned.get("feedback")
        else:
            evaluation = getattr(llm_response, "evaluation")
            feedback = getattr(llm_response, "feedback")

        if evaluation is None: evaluation = "None"
        if feedback is None: feedback = "None"

        evaluation_clean = textwrap.dedent(str(evaluation))
        feedback_clean = textwrap.dedent(str(feedback))
        print(f"evaluation_clean: {type(evaluation_clean)} - {evaluation_clean}")

        return self.STRUCTURED_OUTPUT_SCHEMA(
            evaluation=evaluation_clean,
            feedback=feedback_clean
        )
    

    def pack_into_state(self, state, result: CodeFeedbackSchema, is_max_iterations) -> GraphState:
        """Update workflow state (GraphState) with the node's output."""
        return replace(state,
            script_evaluation=result.evaluation,
            script_feedback=result.feedback,
            max_generation_attempts_achieved=is_max_iterations
        )


    async def post_hook(self, state: GraphState) -> None:
        """Console and logger pretty-print of the results."""
        console = Console()

        if state.script_evaluation:
            console.print(Panel(state.script_evaluation, title="Code evaluation", title_align="left", expand=False))
            logger.info(f"⚪ LLM-generated code evaluation:\n{textwrap.fill(state.script_evaluation, width=100)}")

        if state.script_feedback:
            console.print(Panel(state.script_feedback, title="Code feedback", title_align="left", expand=False))
            logger.info(f"⚪ LLM-generated code feedback:\n{textwrap.fill(state.script_feedback, width=100)}")
            print(f"SCRIPT FEEDBACK TYPE: {type(state.script_feedback)}")
        
        else:
            console.print(Panel("Nothing got from LLM evaluator node.", title= f"{self.name}.", title_align="left"))
            logger.warning("No evaluation generated")


    def chainlit_output_render_step(self, node_output: dict) -> str:
        strings_to_display = []

        if evaluation := node_output.get("script_evaluation"):
            strings_to_display.append(f"**Script evaluation:** {evaluation}")
        else:
            strings_to_display.append(f"**No evaluation**. Errors:\n{node_output.get('errors')}")

        if feedback := node_output.get("script_feedback"):
            strings_to_display.append(f"**Feedback:** {feedback}")

        return "\n\n".join(strings_to_display)
