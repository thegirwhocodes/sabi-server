"""
Goal and Task Management System
Tracks high-level goals, breaks them into actionable tasks, and monitors progress.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class GoalStatus(Enum):
    """Status of a goal."""
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"


class TaskStatus(Enum):
    """Status of a task."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Priority(Enum):
    """Priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Task:
    """A single actionable task."""
    id: str
    goal_id: str
    title: str
    description: str
    status: TaskStatus
    priority: Priority
    assigned_to: str  # "user" or "agent"
    created_at: str
    updated_at: str
    due_date: Optional[str] = None
    completed_at: Optional[str] = None
    dependencies: List[str] = None  # List of task IDs
    metadata: Dict = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['status'] = self.status.value
        data['priority'] = self.priority.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Task':
        data['status'] = TaskStatus(data['status'])
        data['priority'] = Priority(data['priority'])
        return cls(**data)


@dataclass
class Goal:
    """A high-level strategic goal."""
    id: str
    title: str
    description: str
    status: GoalStatus
    priority: Priority
    created_at: str
    updated_at: str
    target_date: Optional[str] = None
    completed_at: Optional[str] = None
    success_criteria: List[str] = None
    metadata: Dict = None
    
    def __post_init__(self):
        if self.success_criteria is None:
            self.success_criteria = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['status'] = self.status.value
        data['priority'] = self.priority.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Goal':
        data['status'] = GoalStatus(data['status'])
        data['priority'] = Priority(data['priority'])
        return cls(**data)


class GoalManager:
    """
    Manages goals and tasks for the co-founder agent.
    Breaks down strategic goals into actionable tasks and tracks progress.
    """
    
    def __init__(self, data_dir: str = "cofounder_agent/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.goals_file = self.data_dir / "goals.json"
        self.tasks_file = self.data_dir / "tasks.json"
        
        self.goals: Dict[str, Goal] = {}
        self.tasks: Dict[str, Task] = {}
        
        self._load()
    
    def _load(self):
        """Load goals and tasks from disk."""
        if self.goals_file.exists():
            with open(self.goals_file, 'r') as f:
                data = json.load(f)
                self.goals = {
                    goal_id: Goal.from_dict(goal_data)
                    for goal_id, goal_data in data.items()
                }
        
        if self.tasks_file.exists():
            with open(self.tasks_file, 'r') as f:
                data = json.load(f)
                self.tasks = {
                    task_id: Task.from_dict(task_data)
                    for task_id, task_data in data.items()
                }
    
    def _save(self):
        """Save goals and tasks to disk."""
        with open(self.goals_file, 'w') as f:
            data = {goal_id: goal.to_dict() for goal_id, goal in self.goals.items()}
            json.dump(data, f, indent=2)
        
        with open(self.tasks_file, 'w') as f:
            data = {task_id: task.to_dict() for task_id, task in self.tasks.items()}
            json.dump(data, f, indent=2)
    
    def create_goal(
        self,
        title: str,
        description: str,
        priority: Priority = Priority.MEDIUM,
        target_date: Optional[str] = None,
        success_criteria: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Create a new goal."""
        goal_id = f"goal_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        now = datetime.now().isoformat()
        
        goal = Goal(
            id=goal_id,
            title=title,
            description=description,
            status=GoalStatus.ACTIVE,
            priority=priority,
            created_at=now,
            updated_at=now,
            target_date=target_date,
            success_criteria=success_criteria or [],
            metadata=metadata or {}
        )
        
        self.goals[goal_id] = goal
        self._save()
        return goal_id
    
    def update_goal(
        self,
        goal_id: str,
        status: Optional[GoalStatus] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[Priority] = None,
        target_date: Optional[str] = None,
        success_criteria: Optional[List[str]] = None
    ):
        """Update a goal."""
        if goal_id not in self.goals:
            raise ValueError(f"Goal {goal_id} not found")
        
        goal = self.goals[goal_id]
        
        if status is not None:
            goal.status = status
            if status == GoalStatus.COMPLETED:
                goal.completed_at = datetime.now().isoformat()
        if title is not None:
            goal.title = title
        if description is not None:
            goal.description = description
        if priority is not None:
            goal.priority = priority
        if target_date is not None:
            goal.target_date = target_date
        if success_criteria is not None:
            goal.success_criteria = success_criteria
        
        goal.updated_at = datetime.now().isoformat()
        self._save()
    
    def create_task(
        self,
        goal_id: str,
        title: str,
        description: str,
        assigned_to: str = "user",
        priority: Priority = Priority.MEDIUM,
        due_date: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Create a new task for a goal."""
        if goal_id not in self.goals:
            raise ValueError(f"Goal {goal_id} not found")
        
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        now = datetime.now().isoformat()
        
        task = Task(
            id=task_id,
            goal_id=goal_id,
            title=title,
            description=description,
            status=TaskStatus.TODO,
            priority=priority,
            assigned_to=assigned_to,
            created_at=now,
            updated_at=now,
            due_date=due_date,
            dependencies=dependencies or [],
            metadata=metadata or {}
        )
        
        self.tasks[task_id] = task
        self._save()
        return task_id
    
    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[Priority] = None,
        due_date: Optional[str] = None
    ):
        """Update a task."""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        
        if status is not None:
            task.status = status
            if status == TaskStatus.COMPLETED:
                task.completed_at = datetime.now().isoformat()
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if priority is not None:
            task.priority = priority
        if due_date is not None:
            task.due_date = due_date
        
        task.updated_at = datetime.now().isoformat()
        self._save()
    
    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a specific goal."""
        return self.goals.get(goal_id)
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a specific task."""
        return self.tasks.get(task_id)
    
    def get_active_goals(self) -> List[Goal]:
        """Get all active goals."""
        return [
            g for g in self.goals.values()
            if g.status in [GoalStatus.ACTIVE, GoalStatus.IN_PROGRESS]
        ]
    
    def get_goal_tasks(self, goal_id: str, status: Optional[TaskStatus] = None) -> List[Task]:
        """Get all tasks for a goal, optionally filtered by status."""
        tasks = [t for t in self.tasks.values() if t.goal_id == goal_id]
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: (t.priority.value, t.created_at))
    
    def get_user_pending_tasks(self) -> List[Task]:
        """Get all pending tasks assigned to the user."""
        return [
            t for t in self.tasks.values()
            if t.assigned_to == "user" and t.status in [TaskStatus.TODO, TaskStatus.IN_PROGRESS]
        ]
    
    def get_blocked_tasks(self) -> List[Task]:
        """Get all blocked tasks."""
        return [t for t in self.tasks.values() if t.status == TaskStatus.BLOCKED]
    
    def calculate_goal_progress(self, goal_id: str) -> Dict:
        """Calculate progress metrics for a goal."""
        tasks = self.get_goal_tasks(goal_id)
        if not tasks:
            return {"progress": 0, "total": 0, "completed": 0, "in_progress": 0}
        
        total = len(tasks)
        completed = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
        in_progress = len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS])
        
        return {
            "progress": (completed / total * 100) if total > 0 else 0,
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "blocked": len([t for t in tasks if t.status == TaskStatus.BLOCKED])
        }
    
    def get_dashboard_summary(self) -> Dict:
        """Get a summary of all goals and tasks."""
        active_goals = self.get_active_goals()
        pending_tasks = self.get_user_pending_tasks()
        
        return {
            "total_goals": len(self.goals),
            "active_goals": len(active_goals),
            "completed_goals": len([g for g in self.goals.values() if g.status == GoalStatus.COMPLETED]),
            "total_tasks": len(self.tasks),
            "pending_user_tasks": len(pending_tasks),
            "blocked_tasks": len(self.get_blocked_tasks()),
            "goals": [
                {
                    "id": goal.id,
                    "title": goal.title,
                    "status": goal.status.value,
                    "priority": goal.priority.value,
                    "progress": self.calculate_goal_progress(goal.id)
                }
                for goal in active_goals
            ]
        }
