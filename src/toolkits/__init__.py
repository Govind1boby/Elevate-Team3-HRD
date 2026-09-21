"""Domain toolkits and deterministic adapter registry.
"""

from typing import Any, Dict, List
from src.toolkits.base import BaseTool, ExecutionContext, ToolExecutionError, AntiIDORViolationError
from src.toolkits.policy.adapter import PolicySearchKnowledgeBaseTool
from src.toolkits.workweek.adapter import (
    WorkWeekGetEmployeeProfileTool,
    WorkWeekUpdateContactInfoTool,
    WorkWeekGetLeaveBalancesTool,
    WorkWeekSubmitLeaveRequestTool,
)
from src.toolkits.service_immediately.adapter import (
    ServiceImmediatelyGetTicketTool,
    ServiceImmediatelyCreateIncidentTool,
    ServiceImmediatelyAddCommentTool,
)


class ToolRegistry:
    """Central registry and dispatcher for all 8 deterministic domain tools."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self.register(PolicySearchKnowledgeBaseTool())
        self.register(WorkWeekGetEmployeeProfileTool())
        self.register(WorkWeekUpdateContactInfoTool())
        self.register(WorkWeekGetLeaveBalancesTool())
        self.register(WorkWeekSubmitLeaveRequestTool())
        self.register(ServiceImmediatelyGetTicketTool())
        self.register(ServiceImmediatelyCreateIncidentTool())
        self.register(ServiceImmediatelyAddCommentTool())

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise ToolExecutionError(f"Tool '{name}' is not recognized or allowed.")
        return self._tools[name]

    def get_all_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns OpenAPI/Function Calling tool declarations for Gemini models."""
        declarations = []
        for name, tool in self._tools.items():
            declarations.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema
            })
        return declarations

    async def dispatch(self, tool_name: str, context: ExecutionContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches tool execution with Anti-IDOR middleware enforcement."""
        tool = self.get_tool(tool_name)
        return await tool.execute(context, **arguments)


# Global singleton registry instance
default_registry = ToolRegistry()

__all__ = [
    "BaseTool",
    "ExecutionContext",
    "ToolExecutionError",
    "AntiIDORViolationError",
    "ToolRegistry",
    "default_registry",
]
