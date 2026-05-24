"""
From repo root:
uv run python revit_code_generator/execute_revit_workflow.py "Create a wall in Revit" "terminal-thread-1"
"""

import time
import asyncio
import json
import sys
from typing import AsyncGenerator, Dict, Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from graph.revit_workflow import simple_revit_workflow, CHAT_SESSION_CONTEXT
from graph.states.graph_state import GraphState
from utils.logger import (
    configure_logger,
    logger,
    dump_pretty_json,
    recursive_serialize,
)

GRAPH = simple_revit_workflow()
IS_GRAPH_STATES_LOGGED = True

logger = configure_logger(trace_states=IS_GRAPH_STATES_LOGGED)
state_logger = logger.bind(tag="state")


async def stream_revit_workflow(
        message: str,
        thread_id: str,
        ) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Streams node-by-node execution of the LangGraph workflow.
    """
    config = RunnableConfig(
        configurable={"thread_id": thread_id}
    )

    initial_state = GraphState(
        user_messages=[HumanMessage(content=message)]
    )
    state_logger.info(
        "Initial graph state:\n\t{}\n", 
        dump_pretty_json(recursive_serialize(initial_state))
    )

    async for state in GRAPH.astream(initial_state, config=config):
        last_state = state
        node_name, node_output = next(iter(state.items()))

        yield {
            "event": "node_update",
            "node": node_name,
            "payload": recursive_serialize(node_output),
            "timestamp": time.time(),
            "thread_id": thread_id,
        }

    CHAT_SESSION_CONTEXT.set("attempts_counter", 0)

    # # Final state snapshot
    # if last_state is not None:
    #     state_logger.info(f"Final graph state: \n{dump_pretty_json(recursive_serialize(last_state))}")
    #     yield {
    #         "event": "final",
    #         "state": recursive_serialize(last_state),
    #         "timestamp": time.time(),
    #         "thread_id": thread_id,
    #     }

async def _run_workflow(message: str, thread_id: str) -> None:
    async for event in stream_revit_workflow(message, thread_id):
        # print(json.dumps(event, ensure_ascii=False))
        pass


def main(message, thread_id):
    asyncio.run(_run_workflow(message, thread_id))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python revit_code_generator/execute_revit_workflow.py "
            '"<message>" "<thread_id>"',
            file=sys.stderr,
        )
        raise SystemExit(2)
    main(sys.argv[1], sys.argv[2])
