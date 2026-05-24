from utils.logger import log_banner, logger
from graph.states.graph_state import GraphState
# from graph.workflow_simple_with_critic import MAX_WORKFLOW_ITERATIONS
from rich.panel import Panel
from rich import print

MAX_WORKFLOW_ITERATIONS = 3

async def route_revit_script(state: GraphState):
    """
    Route back to the Revit generator or finish based on feedback from the Revit script evaluator.
    """
    log_banner("SCRIPT ROUTER", fill='-', width=40)
    logger.info(f"Script evaluation: {state.script_evaluation}")
    print(f"ROUTER: {state.script_evaluation}")

    print(f"Num of generation attempts: {state.num_of_generation_attempts}")

    if state.script_evaluation == "Accept" or state.num_of_generation_attempts >= MAX_WORKFLOW_ITERATIONS or not state.script_evaluation:

        # Log the 1st stopping scenario - acceptance - info:
        if state.script_evaluation == "Accept":
            e_str = f"🟢 Code accepted. Stopping."
            logger.info(e_str)
            print(Panel(e_str, title="INFO", title_align="center", expand=False))

        # Log the 2nd stopping scenario - maximum iterations - warning:
        if state.num_of_generation_attempts >= MAX_WORKFLOW_ITERATIONS:
            e_str = f"🔴 Max script generation attempts ({MAX_WORKFLOW_ITERATIONS}) is reached without acceptance. Stopping."
            logger.warning(e_str)
            print(Panel(e_str, title="WARNING", title_align="center", expand=False))

        # Log the 3rd stopping scenario - evaluator node failure - error:
        if not state.script_evaluation:
            e_str = f"🔴 Error during Evaluation agent run: ({state.errors}). Stopping."
            logger.error(e_str)
            print(Panel(e_str, title="ERROR", title_align="center", expand=False))

        return "Accepted or stopped"
    
    elif state.script_evaluation == "Error or empty":
        e_str = f"🟡 Error or empty code result. Continue."
        logger.info(e_str)
        print(Panel(e_str, title="INFO", title_align="center", expand=False))
        return "Error or empty result"

    else:
        e_str = f"🟡 Incorrect result. Continue."
        logger.info(e_str)
        print(Panel(e_str, title="INFO", title_align="center", expand=False))
        return "Incorrect result"
