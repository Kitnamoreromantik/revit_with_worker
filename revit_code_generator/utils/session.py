import contextvars

# Global context variable for the active session
_user_session_var = contextvars.ContextVar("user_session", default=None)

class SessionContext:
    """Per-request or per-workflow global session store, async-safe."""

    def __init__(self):
        self._store = {}

    def set(self, key, value):
        self._store[key] = value

    def get(self, key, default=None):
        return self._store.get(key, default)

    def reset(self):
        self._store.clear()

    def activate(self):
        """Make this instance the current global session."""
        _user_session_var.set(self)

def get_current_session() -> "SessionContext | None":
    """Return the currently active SessionContext, or None."""
    return _user_session_var.get()

def initialize_session() -> SessionContext:
    """
    Create and activate a new global SessionContext.
    Used once per workflow or user session.
    """
    session = SessionContext()
    session.reset()
    session.activate()
    session.set("attempts_counter", 0)
    return session


# 1. Start a new workflow
# --------------------------------
# from utils.session_context import initialize_session

# session = initialize_session()


# 2. Access it anywhere later
# from utils.session_context import get_current_session

# def increment_attempts():
#     session = get_current_session()
#     if not session:
#         return
#     count = session.get("attempts_counter", 0) + 1
#     session.set("attempts_counter", count)
#     print(f"Attempts so far: {count}")