"""Base classes, execution context, and Anti-IDOR middleware for domain toolkits.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel


@dataclass
class ExecutionContext:
    """Authenticated session context locked from ingress JWT."""
    caller_id: str = "EMP-10492"
    user_role: str = "fte_singapore"
    session_id: str = "sess-default"
    trace_id: str = "trace-default"


class ToolExecutionError(Exception):
    """Raised when deterministic tool validation or execution fails."""
    pass


class AntiIDORViolationError(ToolExecutionError):
    """Raised when an operation attempts to target an employee_id other than the authenticated caller."""
    pass


class BaseTool:
    """Abstract base tool with schema declaration and Anti-IDOR middleware enforcement."""
    name: str
    description: str
    parameters_schema: Dict[str, Any]

    def enforce_anti_idor(self, context: ExecutionContext, target_employee_id: Optional[str]) -> str:
        """Enforces caller == session.user_id.
        If target_employee_id is provided, it MUST match context.caller_id.
        Always returns context.caller_id to prevent prompt injection parameter overrides.
        """
        if target_employee_id and target_employee_id != context.caller_id:
            raise AntiIDORViolationError(
                f"Security Authorization Violation: Authenticated caller '{context.caller_id}' "
                f"is not authorized to access or mutate records for '{target_employee_id}'."
            )
        return context.caller_id

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError
