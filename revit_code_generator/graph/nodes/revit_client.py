import requests
import textwrap
import json
import os

from graph.states.graph_state import GraphState
from graph.nodes.node_lib.base_node import BaseNode

from utils.logger import logger

from rich import print
from rich.panel import Panel

SERVER_URL = os.getenv("SERVER_URL", "http://host.docker.internal:6124/")
# SERVER_URL = "http://localhost:6123/"  # in case of local windows test without docker and with old revit connector

class RevitExecutor(BaseNode):
    """
    Node that executes the Revit script stored in the state obtained with Revit server
    connected to the active document and returns the result.
    """
    def run_revit_code(self, code: str, title: str = None):
        """
        Send C# code to RevitExecutor Revit add-in and get the result.
        """
        script_status = None
        error = None
        code = textwrap.dedent(code).strip()
        logger.info(f"{title or 'Revit client running'}")

        try:
            resp = requests.post(SERVER_URL, data=code.encode("utf-8"))
            script_status = f"Status: {resp.status_code}, Response: {resp.text}"
            # print(script_status)
            logger.info(script_status)

        except requests.exceptions.RequestException as e:
            error = f"Connection error: {e}"
            # print(error)
            logger.info(error)

        return error, script_status


    async def pre_hook(self, _: GraphState) -> None:
        self.log_banner()
        print("\n----------------------------")
        print(f"{'Revit client running'}\n")


    async def core_logic(self, node_input: GraphState) -> GraphState:
        
        if not node_input.script:
            return GraphState(
                user_messages=node_input.user_messages,
                script="None",
                script_explanation=node_input.script_explanation,
                script_result="No script found from the Generator agent!",
                num_of_generation_attempts=node_input.num_of_generation_attempts,
                errors = "node_input.script is empty!",
            )

        try:
            err_msg, script_res = self.run_revit_code(node_input.script)
            # print(f"SCRIPT RES: {script_res}")

        except Exception as err:
            err_msg = str(err)
            if not err_msg.strip():  # empty or only spaces received
                err = "Unknown exception from the Revit client!"
    
            logger.error(f"{err}")
            script_res = f"Revit client has thrown the exception: {err}!"
        
        if err_msg:
            err = str(err_msg)
            logger.error(f"{err}")
            script_res = f"Revit client has thrown the exception: {err}!"


        # print(f"err_msg: {err_msg}\n")
        # print(f"script_result: {script_res}\n")

        return GraphState(
            user_messages=node_input.user_messages,
            script=node_input.script,
            script_explanation=node_input.script_explanation,
            script_result=script_res,
            num_of_generation_attempts=node_input.num_of_generation_attempts,
            errors = err_msg,
        )


    async def test_logic(self, node_input: GraphState) -> GraphState:
        # print(node_input)
        return GraphState(
            user_messages=node_input.user_messages,
            script=node_input.script,
            script_explanation=node_input.script_explanation,
            script_result="Status: 200 Response: Total windows in model: 7",
            num_of_generation_attempts=node_input.num_of_generation_attempts,
        )
    

    async def post_hook(self, node_output: GraphState) -> None:
        try:
            formatted = json.dumps(node_output.script_result, indent=4, ensure_ascii=False)
        except Exception:
            formatted = str(node_output.script_result)
        logger.info(f"\n{formatted}")

        MAX_LINES = 50
        lines = formatted.splitlines()
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + ["...", "[Output truncated]"]
        display_text = "\n".join(lines)

        print(Panel(f"{display_text}", title=f"{self.name}", title_align="left", expand=False))
        # print("\n")


    def chainlit_output_render_step(self, node_output: dict) -> str:
        script_status = node_output.get("script_result")
        return f"**Script outcome:**\n{script_status}" if script_status else "Empty script status!"
