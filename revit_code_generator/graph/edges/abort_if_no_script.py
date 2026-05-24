from rich.panel import Panel
from rich import print

def abort_pipeline_if_no_code(state):
    """
    Aborts the workflow if no code/query/script was produced by a generation node.
    Works for any graph schema (Revit, IFC, Cypher, etc.).
    """
    # Try to detect the main generated artifact
    code = getattr(state, "script", None) or getattr(state, "query", None) or getattr(state, "code", None)

    if not code:
        msg = "❌ No code generated — stopping."
        if hasattr(state, "script_feedback"):
            state.script_feedback = msg
        elif hasattr(state, "feedback"):
            state.feedback = msg
        elif hasattr(state, "error"):
            state.error = msg

        # Rich warning
        print(Panel(
            "Code generation agent was unable to produce any code. Pipeline stopped.", title="⚠️  WARNING",
            title_align="center", expand=False
        ))
        return "Abort"

    else:
        return "Continue"
