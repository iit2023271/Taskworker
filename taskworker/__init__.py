"""TaskWorker — autonomous AI task worker (prototype).

Public pieces:
- Agent: the ReAct loop executor (agent.py)
- Brain, LLMBrain, RuleBrain: decision-making brains
- RunMemory: facts + step transcript
- Approver: the write-action approval gate
- verify_records / verify_via_api: outcome verification
- ToolContext, get_schemas, run_tool: the tool layer
"""

from .agent import Agent
from .approval import Approver, WRITE_TOOLS
from .brain.base import Brain, BrainError
from .brain.llm_brain import LLMBrain
from .brain.rule_brain import RuleBrain
from .memory import RunMemory
from .tools.base import ToolContext
from .tools.registry import get_schemas, run_tool, tool_names
from .verify import verify_records, verify_via_api

__all__ = [
    "Agent",
    "Approver",
    "WRITE_TOOLS",
    "Brain",
    "BrainError",
    "LLMBrain",
    "RuleBrain",
    "RunMemory",
    "ToolContext",
    "get_schemas",
    "run_tool",
    "tool_names",
    "verify_records",
    "verify_via_api",
]
