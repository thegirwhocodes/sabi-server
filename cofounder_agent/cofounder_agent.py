"""
Co-Founder Agent
Main agent engine that integrates all systems and provides the co-founder interface.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from agent_memory import AgentMemory, MemoryType
from goal_manager import GoalManager, Priority, GoalStatus, TaskStatus
from opportunity_monitor import OpportunityMonitor, OpportunityType, OpportunityStatus
from accountability_system import AccountabilitySystem, CommitmentStatus


class CofounderAgent:
    """
    The Co-Founder Agent for Sabi.
    
    Acts as a strategic thought partner, operational manager, and accountability system.
    Helps break down high-level goals, track progress, monitor opportunities,
    and keep the founder accountable.
    """
    
    def __init__(self, data_dir: str = "cofounder_agent"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize all subsystems
        self.memory = AgentMemory(f"{data_dir}/memory")
        self.goals = GoalManager(f"{data_dir}/data")
        self.opportunities = OpportunityMonitor(f"{data_dir}/data")
        self.accountability = AccountabilitySystem(f"{data_dir}/data")
        
        # Load agent config
        self.config_file = self.data_dir / "config.json"
        self.config = self._load_config()
        
        # Initialize sabi profile
        self._init_sabi_profile()
    
    def _load_config(self) -> Dict:
        """Load agent configuration."""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)
        
        # Default config
        default_config = {
            "agent_name": "Co-Founder Agent",
            "user_name": "Naomi",
            "check_in_frequency_hours": 24,
            "reminder_style": "supportive_persistent",  # or "direct", "gentle"
            "auto_actions_enabled": False,  # Require approval before autonomous actions
            "opportunity_scan_enabled": True,
            "opportunity_scan_frequency_days": 7
        }
        
        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        return default_config
    
    def _init_sabi_profile(self):
        """Initialize or load Sabi's profile for opportunity matching."""
        profile = self.memory.get_context("sabi_profile")
        if not profile:
            profile = {
                "name": "Sabi",
                "description": "AI-powered phone-based tutor for children in Africa",
                "focus_areas": [
                    "education technology",
                    "AI/ML in education",
                    "African edtech",
                    "voice AI",
                    "early childhood education",
                    "foundational learning and numeracy"
                ],
                "strengths": [
                    "AI voice tutoring",
                    "low-tech delivery (phone calls)",
                    "Nigeria operations",
                    "curriculum expertise",
                    "proven pilot results"
                ],
                "stage": "early-stage startup",
                "team_size": "founder + technical team",
                "location": "Nigeria/Africa"
            }
            self.memory.set_context("sabi_profile", profile)
    
    # ============ Goal Management ============
    
    def set_high_level_goal(
        self,
        title: str,
        description: str,
        priority: str = "medium",
        target_date: Optional[str] = None,
        success_criteria: Optional[List[str]] = None
    ) -> Dict:
        """
        Set a high-level strategic goal.
        
        The agent will break this down into actionable tasks and create a roadmap.
        """
        priority_enum = Priority[priority.upper()]
        goal_id = self.goals.create_goal(
            title=title,
            description=description,
            priority=priority_enum,
            target_date=target_date,
            success_criteria=success_criteria
        )
        
        # Log in memory
        self.memory.add_memory(
            MemoryType.GOAL,
            f"New goal set: {title}",
            metadata={"goal_id": goal_id},
            tags=["goal", "strategic"]
        )
        
        # Break down into tasks
        tasks = self._break_down_goal(goal_id, description)
        
        return {
            "goal_id": goal_id,
            "title": title,
            "tasks_created": len(tasks),
            "message": f"Goal '{title}' created with {len(tasks)} initial tasks. Let's get started!"
        }
    
    def _break_down_goal(self, goal_id: str, description: str) -> List[str]:
        """
        Break down a high-level goal into actionable tasks.
        
        In production, this would use an LLM to intelligently decompose the goal.
        For now, we'll create a basic structure.
        """
        goal = self.goals.get_goal(goal_id)
        if not goal:
            return []
        
        # Create standard phases for any goal
        phases = [
            ("Research and Planning", "Research requirements and create detailed plan"),
            ("Resource Identification", "Identify required resources, tools, and people"),
            ("Execution Planning", "Break down into specific action items"),
            ("Implementation", "Execute the plan"),
            ("Review and Iterate", "Review outcomes and iterate")
        ]
        
        task_ids = []
        for title, description in phases:
            task_id = self.goals.create_task(
                goal_id=goal_id,
                title=title,
                description=description,
                assigned_to="user",
                priority=goal.priority
            )
            task_ids.append(task_id)
        
        return task_ids
    
    def get_next_actions(self) -> Dict:
        """
        Get the next actions the user should take.
        Prioritizes based on deadlines, priority, and dependencies.
        """
        pending_tasks = self.goals.get_user_pending_tasks()
        overdue_commitments = self.accountability.get_overdue_commitments()
        upcoming_opportunities = self.opportunities.get_upcoming_deadlines(days=7)
        
        # Sort tasks by priority and due date
        sorted_tasks = sorted(
            pending_tasks,
            key=lambda t: (
                t.priority.value,
                t.due_date if t.due_date else "9999-12-31"
            )
        )
        
        next_actions = []
        
        # Add overdue commitments first
        for commitment in overdue_commitments[:3]:
            next_actions.append({
                "type": "overdue_commitment",
                "id": commitment.id,
                "description": commitment.description,
                "due_date": commitment.due_date,
                "priority": "URGENT"
            })
        
        # Add top priority tasks
        for task in sorted_tasks[:5]:
            goal = self.goals.get_goal(task.goal_id)
            next_actions.append({
                "type": "task",
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "goal": goal.title if goal else "Unknown",
                "priority": task.priority.value,
                "due_date": task.due_date
            })
        
        # Add upcoming opportunity deadlines
        for opp in upcoming_opportunities[:2]:
            next_actions.append({
                "type": "opportunity_deadline",
                "id": opp.id,
                "title": opp.title,
                "deadline": opp.deadline,
                "priority": "HIGH"
            })
        
        return {
            "next_actions": next_actions,
            "summary": self._generate_action_summary(next_actions)
        }
    
    def _generate_action_summary(self, actions: List[Dict]) -> str:
        """Generate a human-readable summary of next actions."""
        if not actions:
            return "Great! You're all caught up. No urgent actions right now."
        
        overdue = len([a for a in actions if a["type"] == "overdue_commitment"])
        tasks = len([a for a in actions if a["type"] == "task"])
        opps = len([a for a in actions if a["type"] == "opportunity_deadline"])
        
        parts = []
        if overdue > 0:
            parts.append(f"{overdue} overdue commitment(s)")
        if tasks > 0:
            parts.append(f"{tasks} task(s)")
        if opps > 0:
            parts.append(f"{opps} opportunity deadline(s)")
        
        return f"You have {', '.join(parts)} that need attention."
    
    # ============ Opportunity Management ============
    
    def scan_for_opportunities(self) -> Dict:
        """
        Scan for new opportunities based on Sabi's profile.
        
        In production, this would use web search APIs and AI to find relevant
        grants, accelerators, competitions, etc.
        """
        # Placeholder for opportunity scanning logic
        # In real implementation, would call search APIs, scrape websites, etc.
        
        sabi_profile = self.memory.get_context("sabi_profile")
        search_config = self.opportunities.search_config
        
        # Log the scan
        self.memory.add_memory(
            MemoryType.INSIGHT,
            "Performed opportunity scan",
            metadata={
                "keywords": search_config["keywords"],
                "timestamp": datetime.now().isoformat()
            },
            tags=["opportunity", "scan"]
        )
        
        return {
            "scan_completed": True,
            "message": "Opportunity scan completed. Check the opportunities dashboard for new findings.",
            "next_scan": self._calculate_next_scan_date()
        }
    
    def _calculate_next_scan_date(self) -> str:
        """Calculate when the next opportunity scan should happen."""
        from datetime import timedelta
        days = self.config.get("opportunity_scan_frequency_days", 7)
        next_scan = datetime.now() + timedelta(days=days)
        return next_scan.isoformat()
    
    def add_opportunity_manual(
        self,
        title: str,
        opp_type: str,
        description: str,
        source: str,
        **kwargs
    ) -> str:
        """Manually add an opportunity."""
        opp_type_enum = OpportunityType[opp_type.upper()]
        
        # Calculate fit score
        sabi_profile = self.memory.get_context("sabi_profile")
        fit_score = self.opportunities.calculate_fit_score(
            description,
            kwargs.get("requirements", []),
            sabi_profile
        )
        
        opp_id = self.opportunities.add_opportunity(
            title=title,
            opp_type=opp_type_enum,
            description=description,
            source=source,
            fit_score=fit_score,
            **kwargs
        )
        
        # Log in memory
        self.memory.add_memory(
            MemoryType.OPPORTUNITY,
            f"New opportunity: {title}",
            metadata={"opportunity_id": opp_id, "fit_score": fit_score},
            tags=["opportunity", opp_type.lower()]
        )
        
        return opp_id
    
    # ============ Accountability & Check-ins ============
    
    def create_commitment(
        self,
        description: str,
        due_date: str,
        task_id: Optional[str] = None
    ) -> str:
        """Create a commitment that the agent will hold you accountable for."""
        commitment_id = self.accountability.create_commitment(
            description=description,
            due_date=due_date,
            task_id=task_id
        )
        
        self.memory.add_memory(
            MemoryType.COMMITMENT,
            f"Commitment made: {description}",
            metadata={"commitment_id": commitment_id, "due_date": due_date},
            tags=["commitment", "accountability"]
        )
        
        return commitment_id
    
    def check_in(self) -> Dict:
        """
        Perform a check-in: review progress, send reminders, and prompt for updates.
        
        This is the agent's main interaction point where it "doesn't relent"
        until things are done.
        """
        # Check for overdue items
        self.accountability.check_overdue_commitments()
        
        # Get pending reminders
        pending_reminders = self.accountability.get_pending_reminders()
        
        # Get next actions
        next_actions = self.get_next_actions()
        
        # Get goal progress
        active_goals = self.goals.get_active_goals()
        goal_progress = [
            {
                "title": goal.title,
                "progress": self.goals.calculate_goal_progress(goal.id)
            }
            for goal in active_goals
        ]
        
        # Generate check-in message
        message = self._generate_check_in_message(
            pending_reminders,
            next_actions,
            goal_progress
        )
        
        return {
            "message": message,
            "pending_reminders": len(pending_reminders),
            "next_actions": next_actions["next_actions"],
            "goal_progress": goal_progress,
            "accountability_score": self.accountability.get_accountability_score()
        }
    
    def _generate_check_in_message(
        self,
        reminders: List,
        next_actions: Dict,
        goal_progress: List[Dict]
    ) -> str:
        """Generate a personalized check-in message."""
        user_name = self.config.get("user_name", "there")
        style = self.config.get("reminder_style", "supportive_persistent")
        
        if style == "direct":
            greeting = f"Hey {user_name},"
        elif style == "gentle":
            greeting = f"Hi {user_name},"
        else:  # supportive_persistent
            greeting = f"Hey {user_name}! Hope you're doing well."
        
        parts = [greeting]
        
        if reminders:
            parts.append(f"\nYou have {len(reminders)} pending reminder(s). Let's tackle these:")
            for r in reminders[:3]:
                parts.append(f"  - {r.message}")
        
        if next_actions["next_actions"]:
            parts.append(f"\n{next_actions['summary']}")
        
        if goal_progress:
            in_progress = [g for g in goal_progress if g["progress"]["in_progress"] > 0]
            if in_progress:
                parts.append(f"\n{len(in_progress)} goal(s) in progress. Keep going!")
        
        return "\n".join(parts)
    
    # ============ Dashboard & Reporting ============
    
    def get_dashboard(self) -> Dict:
        """Get a complete dashboard of all agent activities and status."""
        return {
            "goals": self.goals.get_dashboard_summary(),
            "opportunities": self.opportunities.get_dashboard_summary(),
            "accountability": {
                "active_commitments": len(self.accountability.get_active_commitments()),
                "overdue_commitments": len(self.accountability.get_overdue_commitments()),
                "score": self.accountability.get_accountability_score(),
                "history": self.accountability.get_commitment_history(days=30)
            },
            "memory_summary": self.memory.get_summary(),
            "next_actions": self.get_next_actions()
        }
    
    def get_weekly_report(self) -> Dict:
        """Generate a weekly progress report."""
        recent_activity = self.memory.get_recent_activity(days=7)
        
        # Categorize activities
        activities_by_type = {}
        for activity in recent_activity:
            type_name = activity.type.value
            if type_name not in activities_by_type:
                activities_by_type[type_name] = []
            activities_by_type[type_name].append(activity)
        
        return {
            "period": "Last 7 days",
            "activities_by_type": {
                k: len(v) for k, v in activities_by_type.items()
            },
            "goals_progress": self.goals.get_dashboard_summary(),
            "accountability": self.accountability.get_commitment_history(days=7),
            "opportunities_added": len([
                a for a in recent_activity
                if a.type == MemoryType.OPPORTUNITY
            ])
        }
    
    # ============ Thought Partnership ============
    
    def think_about_goal(self, goal_id: str) -> Dict:
        """
        Think through a goal and provide strategic insights.
        
        In production, this would use an LLM to provide deep analysis.
        """
        goal = self.goals.get_goal(goal_id)
        if not goal:
            return {"error": "Goal not found"}
        
        tasks = self.goals.get_goal_tasks(goal_id)
        progress = self.goals.calculate_goal_progress(goal_id)
        
        # Generate insights (placeholder - would use LLM in production)
        insights = []
        
        if progress["blocked"] > 0:
            insights.append(f"{progress['blocked']} task(s) are blocked. Let's identify what's blocking them.")
        
        if progress["progress"] < 20 and len(tasks) > 0:
            insights.append("This goal is just getting started. Focus on the first 1-2 tasks to build momentum.")
        elif progress["progress"] > 80:
            insights.append("You're in the final stretch! Keep pushing to completion.")
        
        return {
            "goal": {
                "id": goal.id,
                "title": goal.title,
                "status": goal.status.value
            },
            "progress": progress,
            "insights": insights,
            "suggested_actions": self._suggest_actions_for_goal(goal_id)
        }
    
    def _suggest_actions_for_goal(self, goal_id: str) -> List[str]:
        """Suggest specific actions to move a goal forward."""
        tasks = self.goals.get_goal_tasks(goal_id)
        suggestions = []
        
        todo_tasks = [t for t in tasks if t.status == TaskStatus.TODO]
        blocked_tasks = [t for t in tasks if t.status == TaskStatus.BLOCKED]
        
        if blocked_tasks:
            suggestions.append(f"Unblock {len(blocked_tasks)} blocked task(s)")
        
        if todo_tasks:
            next_task = todo_tasks[0]
            suggestions.append(f"Start work on: {next_task.title}")
        
        return suggestions
