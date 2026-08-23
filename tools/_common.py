"""Shared helpers for the MCP tool layer.

Tools are called by a language model, not by application code. A tool that
raises ends the model's turn with an opaque failure, so each one catches
everything and returns a sentence the model can read and act on. The exception
is still logged in full to stderr for the operator.
"""

from __future__ import annotations

from logger import log_error


def failure(action: str, exc: Exception) -> str:
    """Log an exception and render it as a message for the calling model.

    Args:
        action: Present participle describing what was attempted, e.g.
            "creating issue 'Login page'". Used in both the log line and the
            returned message.
    """
    detail = f"{type(exc).__name__}: {exc}"
    log_error(f"{action} failed: {detail}")
    return f"Error {action}: {detail}"
