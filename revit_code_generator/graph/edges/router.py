from utils.logger import log_banner, logger
from graph.states.graph_state import GraphState
# from graph.workflow_simple_with_critic import MAX_WORKFLOW_ITERATIONS
from rich.panel import Panel
from rich import print

MAX_WORKFLOW_ITERATIONS = 2

async def route_query(state: GraphState):
    """
    Route back to the Query generator or finish based on feedback from the Query evaluator.
    """
    log_banner("ROUTER", fill='-', width=40)
    logger.info(f"⚪ Query evaluation: {state.script_evaluation}")

    if state.query_evaluation == "Accept" or state.num_of_generation_attempts >= MAX_WORKFLOW_ITERATIONS:
        if state.num_of_generation_attempts >= MAX_WORKFLOW_ITERATIONS:
            logger.warning(f"🔴 Max query attempts ({MAX_WORKFLOW_ITERATIONS}) is reached without acceptance. Stopped.")
            print(Panel(f"Max query attempts ({MAX_WORKFLOW_ITERATIONS}) is reached without acceptance. Stopped.", 
                        title="WARNING", title_align="center", expand=False))
        return "Accepted or stopped"
    
    elif state.query_evaluation == "Error or empty":
        return "Error or empty result"

    else:
        return "Logical flaw or incomplete"
