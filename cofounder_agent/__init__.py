"""
Co-Founder Agent
An AI agent that acts as a strategic co-founder for Sabi.
"""

from .cofounder_agent import CofounderAgent
from .agent_memory import AgentMemory, MemoryType
from .goal_manager import GoalManager, Priority, GoalStatus, TaskStatus
from .opportunity_monitor import OpportunityMonitor, OpportunityType, OpportunityStatus
from .accountability_system import AccountabilitySystem, CommitmentStatus

__version__ = "1.0.0"
__all__ = [
    "CofounderAgent",
    "AgentMemory",
    "MemoryType",
    "GoalManager",
    "Priority",
    "GoalStatus",
    "TaskStatus",
    "OpportunityMonitor",
    "OpportunityType",
    "OpportunityStatus",
    "AccountabilitySystem",
    "CommitmentStatus",
]
