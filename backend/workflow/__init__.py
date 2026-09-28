"""Lightweight workflow primitives used by the LabMate demo.

The public shape mirrors the parts of LangGraph that are useful here
(typed-ish state, routing and checkpoints) without making the MVP depend on
the full LangGraph distribution. The service can be switched to LangGraph
later without changing the API contract.
"""

from .engine import classify_question, save_checkpoint

__all__ = ["classify_question", "save_checkpoint"]
