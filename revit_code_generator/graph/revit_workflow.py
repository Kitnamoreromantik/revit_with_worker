"""
Define the LLM-workflows
"""
import chainlit as cl

from utils.session import initialize_session, get_current_session
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from graph.states.graph_state import GraphState  # Revit Plugin
# from graph.states.graph_state import GraphState # Chat-with-IFC

from graph.nodes.code_generators import RevitScriptGenerator, RevitScriptGeneratorSchema
from graph.nodes.node_lib.base_code_evaluator import CodeFeedbackSchema
from graph.nodes.code_evaluators import RevitScriptEvaluator
from graph.nodes.revit_client import RevitExecutor
from graph.nodes.revit_natural_language_interpreter import NaturalLanguageInterpreter

from graph.edges import route_revit_script, abort_pipeline_if_no_code
from utils.logger import logger

from dotenv import load_dotenv
import os

load_dotenv()

# MAX_WORKFLOW_ITERATIONS = 2  # defined in revit_router.py

initialize_session()
CHAT_SESSION_CONTEXT = get_current_session()

# Take the LLM model names from .env variables, or defaults:
generator_llm = os.getenv("GENERATOR_MODEL", "foundationmodels:Qwen/Qwen3-Coder-480B-A35B-Instruct")
evaluator_llm = os.getenv("EVALUATOR_MODEL", "foundationmodels:deepseek-ai/DeepSeek-R1-Distill-Llama-70B")
interpreter_llm = os.getenv("INTERPRETER_MODEL", "foundationmodels:GigaChat/GigaChat-2-Max")


def simple_revit_workflow():
    name = "revit_workflow"

    revit_generator = RevitScriptGenerator(name = "🤖 Генерация Revit скрипта",
        session_context_variable = CHAT_SESSION_CONTEXT,  # to keep generation attempts counter
        sys_prompt_name = "revit_script_generator_sys",
        llm_id = generator_llm,
        structured_output_schema = None if ("giga" in generator_llm.lower()) else RevitScriptGeneratorSchema,
        temperature = 0.7,
        max_tokens = None,
        test_mode = True,
    )

    revit_script_executor = RevitExecutor(name = "🧩 Исполнение скрипта", 
                                          test_mode=True
                            )

    revit_script_evaluator = RevitScriptEvaluator(
        name = "🚦 Оценка Revit скрипта",
        structured_output_schema = CodeFeedbackSchema,
        sys_prompt_name = "script_evaluator_sys_rus",
        usr_prompt_template_name = "script_evaluator_usr_template",
        llm_id = evaluator_llm,
        temperature = None,
        max_tokens = None,
        test_mode = True,
    )

    revit_interpreter = NaturalLanguageInterpreter(
        name = "📝 Финальная оценка",
        sys_prompt_name = "revit_interpreter_sys",
        llm_id = interpreter_llm,
        temperature = None,
        max_tokens = None,
        test_mode = True,
    )
  
    # Define the state graph:
    graph = StateGraph(GraphState)

    # Add nodes:
    graph.add_node(revit_generator.name, revit_generator)
    graph.add_node(revit_script_executor.name, revit_script_executor)
    graph.add_node(revit_script_evaluator.name, revit_script_evaluator)
    graph.add_node(revit_interpreter.name, revit_interpreter)

    # Add edges:
    graph.add_edge(START, revit_generator.name)

    graph.add_conditional_edges(
        revit_generator.name,
        abort_pipeline_if_no_code,
        {
            "Continue": revit_script_executor.name,
            "Abort": END,
        },
    )

    graph.add_edge(revit_script_executor.name, revit_script_evaluator.name)

    graph.add_conditional_edges(
        revit_script_evaluator.name,
        route_revit_script,
        {
            "Accepted or stopped": revit_interpreter.name,
            "Incorrect result": revit_generator.name,
            "Error or empty result": revit_generator.name,
        },
    )

    graph.add_edge(revit_interpreter.name, END)
    # graph.add_edge(revit_generator.name, END)

    
    # Compile the workflow:
    G = graph.compile(checkpointer=MemorySaver())
    logger.info(f"LLM workflow initialized: {name}")
    logger.info(f"Workflow graph:\n{G.get_graph().draw_ascii()}")

    # Store not-compiled node instances for Chainlit rendering:
    G.node_instances = {
        revit_generator.name: revit_generator,
        revit_script_executor.name: revit_script_executor,
        revit_script_evaluator.name: revit_script_evaluator,
        revit_interpreter.name: revit_interpreter,
    }
    return G
