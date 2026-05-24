from .node_lib.base_code_evaluator import ScriptEvaluatorBaseNode


class RevitScriptEvaluator(ScriptEvaluatorBaseNode):
    TITLE = "Revit script critic"


class CypherScriptEvaluator(ScriptEvaluatorBaseNode):
    TITLE = "Cypher script critic"
    MAX_WORKFLOW_ITERATIONS = 3
