#!/usr/bin/env python3
"""
Co-Founder Agent CLI
Command-line interface for interacting with your AI co-founder.

Usage: python3 cofounder_agent/cli.py [command]
"""

import sys
import argparse
import json
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from cofounder_agent import CofounderAgent
from goal_manager import Priority
from opportunity_monitor import OpportunityType


class CofounderCLI:
    """CLI interface for the Co-Founder Agent."""
    
    def __init__(self):
        self.agent = CofounderAgent()
    
    def run(self, args):
        """Run the CLI command."""
        command = args.command
        
        commands = {
            "dashboard": self.cmd_dashboard,
            "checkin": self.cmd_checkin,
            "goal": self.cmd_goal,
            "task": self.cmd_task,
            "opportunity": self.cmd_opportunity,
            "commit": self.cmd_commit,
            "next": self.cmd_next,
            "report": self.cmd_report,
            "think": self.cmd_think,
            "config": self.cmd_config
        }
        
        if command in commands:
            commands[command](args)
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    
    def cmd_dashboard(self, args):
        """Show the complete dashboard."""
        dashboard = self.agent.get_dashboard()
        
        print("\n" + "="*60)
        print("  SABI CO-FOUNDER AGENT DASHBOARD")
        print("="*60 + "\n")
        
        # Goals section
        goals_data = dashboard["goals"]
        print(f"📊 GOALS: {goals_data['active_goals']}/{goals_data['total_goals']} active")
        print(f"   Tasks: {goals_data['pending_user_tasks']} pending, {goals_data['blocked_tasks']} blocked\n")
        
        if goals_data["goals"]:
            for goal in goals_data["goals"]:
                progress = goal["progress"]
                bar = self._progress_bar(progress["progress"])
                print(f"   • {goal['title']}")
                print(f"     {bar} {progress['progress']:.1f}% ({progress['completed']}/{progress['total']} tasks)")
        
        # Opportunities section
        opp_data = dashboard["opportunities"]
        print(f"\n💡 OPPORTUNITIES: {opp_data['active_opportunities']} active, {opp_data['high_fit_count']} high-fit")
        print(f"   Upcoming deadlines: {opp_data['upcoming_deadlines']}\n")
        
        # Accountability section
        acc_data = dashboard["accountability"]
        score = acc_data["score"]
        score_color = "🟢" if score >= 0.8 else "🟡" if score >= 0.6 else "🔴"
        print(f"\n✅ ACCOUNTABILITY {score_color}")
        print(f"   Score: {score:.1%}")
        print(f"   Active commitments: {acc_data['active_commitments']}")
        print(f"   Overdue: {acc_data['overdue_commitments']}")
        
        # Next actions
        next_actions = dashboard["next_actions"]
        if next_actions["next_actions"]:
            print(f"\n🎯 NEXT ACTIONS:")
            print(f"   {next_actions['summary']}\n")
            for i, action in enumerate(next_actions["next_actions"][:3], 1):
                print(f"   {i}. {action.get('title') or action.get('description')}")
                if action.get("priority"):
                    print(f"      Priority: {action['priority']}")
        
        print("\n" + "="*60 + "\n")
    
    def cmd_checkin(self, args):
        """Perform a check-in."""
        result = self.agent.check_in()
        
        print("\n" + "="*60)
        print("  CHECK-IN")
        print("="*60 + "\n")
        
        print(result["message"])
        
        if result["next_actions"]:
            print("\n🎯 Your next actions:")
            for i, action in enumerate(result["next_actions"][:5], 1):
                title = action.get("title") or action.get("description")
                priority = action.get("priority", "")
                print(f"  {i}. [{priority}] {title}")
        
        if result["goal_progress"]:
            print("\n📊 Goal Progress:")
            for gp in result["goal_progress"]:
                progress = gp["progress"]
                bar = self._progress_bar(progress["progress"])
                print(f"  • {gp['title']}: {bar} {progress['progress']:.1f}%")
        
        score = result["accountability_score"]
        print(f"\n✅ Your accountability score: {score:.1%}")
        
        print("\n" + "="*60 + "\n")
    
    def cmd_goal(self, args):
        """Manage goals."""
        if args.goal_action == "create":
            result = self.agent.set_high_level_goal(
                title=args.title,
                description=args.description,
                priority=args.priority or "medium",
                target_date=args.target_date
            )
            print(f"\n✅ {result['message']}\n")
            print(f"Goal ID: {result['goal_id']}")
            print(f"Tasks created: {result['tasks_created']}\n")
        
        elif args.goal_action == "list":
            goals = self.agent.goals.get_active_goals()
            print(f"\n📊 Active Goals ({len(goals)}):\n")
            for goal in goals:
                progress = self.agent.goals.calculate_goal_progress(goal.id)
                bar = self._progress_bar(progress["progress"])
                print(f"  • {goal.title}")
                print(f"    {bar} {progress['progress']:.1f}% | Priority: {goal.priority.value}")
                print(f"    ID: {goal.id}\n")
        
        elif args.goal_action == "show":
            thought = self.agent.think_about_goal(args.goal_id)
            if "error" in thought:
                print(f"\n❌ {thought['error']}\n")
                return
            
            goal = thought["goal"]
            progress = thought["progress"]
            
            print(f"\n📊 Goal: {goal['title']}\n")
            print(f"Status: {goal['status']}")
            print(f"Progress: {progress['progress']:.1f}%")
            print(f"  - Completed: {progress['completed']}/{progress['total']}")
            print(f"  - In Progress: {progress['in_progress']}")
            print(f"  - Blocked: {progress['blocked']}\n")
            
            if thought["insights"]:
                print("💡 Insights:")
                for insight in thought["insights"]:
                    print(f"  • {insight}")
                print()
            
            if thought["suggested_actions"]:
                print("🎯 Suggested Actions:")
                for action in thought["suggested_actions"]:
                    print(f"  • {action}")
                print()
    
    def cmd_task(self, args):
        """Manage tasks."""
        if args.task_action == "create":
            task_id = self.agent.goals.create_task(
                goal_id=args.goal_id,
                title=args.title,
                description=args.description,
                assigned_to=args.assigned_to or "user",
                priority=Priority[args.priority.upper()] if args.priority else Priority.MEDIUM
            )
            print(f"\n✅ Task created: {task_id}\n")
        
        elif args.task_action == "complete":
            from goal_manager import TaskStatus
            self.agent.goals.update_task(args.task_id, status=TaskStatus.COMPLETED)
            print(f"\n✅ Task marked as complete!\n")
        
        elif args.task_action == "list":
            if args.goal_id:
                tasks = self.agent.goals.get_goal_tasks(args.goal_id)
                print(f"\n📋 Tasks for goal:\n")
            else:
                tasks = self.agent.goals.get_user_pending_tasks()
                print(f"\n📋 Your pending tasks ({len(tasks)}):\n")
            
            for task in tasks:
                status_icon = "✓" if task.status.value == "completed" else "○"
                print(f"  {status_icon} {task.title}")
                print(f"    Status: {task.status.value} | Priority: {task.priority.value}")
                print(f"    ID: {task.id}\n")
    
    def cmd_opportunity(self, args):
        """Manage opportunities."""
        if args.opp_action == "scan":
            result = self.agent.scan_for_opportunities()
            print(f"\n✅ {result['message']}\n")
            print(f"Next scan: {result['next_scan']}\n")
        
        elif args.opp_action == "add":
            opp_id = self.agent.add_opportunity_manual(
                title=args.title,
                opp_type=args.type,
                description=args.description,
                source=args.source,
                url=args.url,
                deadline=args.deadline,
                amount=args.amount
            )
            print(f"\n✅ Opportunity added: {opp_id}\n")
        
        elif args.opp_action == "list":
            opps = self.agent.opportunities.get_active_opportunities()
            print(f"\n💡 Active Opportunities ({len(opps)}):\n")
            for opp in opps:
                fit_icon = "🎯" if opp.fit_score and opp.fit_score >= 0.7 else "○"
                print(f"  {fit_icon} {opp.title}")
                print(f"    Type: {opp.type.value} | Status: {opp.status.value}")
                if opp.deadline:
                    print(f"    Deadline: {opp.deadline}")
                if opp.fit_score:
                    print(f"    Fit Score: {opp.fit_score:.1%}")
                print(f"    ID: {opp.id}\n")
    
    def cmd_commit(self, args):
        """Create a commitment."""
        if not args.due_date:
            # Default to tomorrow
            tomorrow = datetime.now() + timedelta(days=1)
            due_date = tomorrow.isoformat()
        else:
            due_date = args.due_date
        
        commitment_id = self.agent.create_commitment(
            description=args.description,
            due_date=due_date,
            task_id=args.task_id
        )
        
        print(f"\n✅ Commitment recorded: {commitment_id}")
        print(f"Due: {due_date}")
        print(f"\nI'll hold you accountable! 💪\n")
    
    def cmd_next(self, args):
        """Show next actions."""
        result = self.agent.get_next_actions()
        
        print("\n🎯 YOUR NEXT ACTIONS\n")
        print(result["summary"])
        print()
        
        for i, action in enumerate(result["next_actions"], 1):
            title = action.get("title") or action.get("description")
            priority = action.get("priority", "")
            action_type = action.get("type", "")
            
            icon = "🔥" if priority == "URGENT" else "⚡" if priority == "HIGH" else "○"
            print(f"{i}. {icon} {title}")
            
            if action_type == "task" and action.get("goal"):
                print(f"   Goal: {action['goal']}")
            
            if action.get("due_date") or action.get("deadline"):
                date = action.get("due_date") or action.get("deadline")
                print(f"   Due: {date}")
            
            print()
    
    def cmd_report(self, args):
        """Generate a report."""
        report = self.agent.get_weekly_report()
        
        print("\n" + "="*60)
        print(f"  WEEKLY REPORT - {report['period']}")
        print("="*60 + "\n")
        
        print("📊 Activity Summary:")
        for activity_type, count in report["activities_by_type"].items():
            print(f"  • {activity_type}: {count}")
        
        acc = report["accountability"]
        print(f"\n✅ Accountability:")
        print(f"  • Completion rate: {acc['completion_rate']:.1f}%")
        print(f"  • Completed: {acc['completed']}/{acc['total']}")
        
        print(f"\n💡 Opportunities added: {report['opportunities_added']}")
        
        print("\n" + "="*60 + "\n")
    
    def cmd_think(self, args):
        """Get strategic thoughts on a goal."""
        thought = self.agent.think_about_goal(args.goal_id)
        
        if "error" in thought:
            print(f"\n❌ {thought['error']}\n")
            return
        
        print(f"\n💭 Thinking about: {thought['goal']['title']}\n")
        
        if thought["insights"]:
            print("Insights:")
            for insight in thought["insights"]:
                print(f"  • {insight}")
            print()
        
        if thought["suggested_actions"]:
            print("What I suggest:")
            for action in thought["suggested_actions"]:
                print(f"  • {action}")
            print()
    
    def cmd_config(self, args):
        """View or update configuration."""
        if args.show:
            print("\n⚙️  Current Configuration:\n")
            print(json.dumps(self.agent.config, indent=2))
            print()
        elif args.set:
            key, value = args.set.split("=", 1)
            # Try to parse as JSON for booleans/numbers
            try:
                value = json.loads(value)
            except:
                pass
            self.agent.config[key] = value
            with open(self.agent.config_file, 'w') as f:
                json.dump(self.agent.config, f, indent=2)
            print(f"\n✅ Updated {key} = {value}\n")
    
    def _progress_bar(self, percentage: float, width: int = 20) -> str:
        """Generate a text progress bar."""
        filled = int(width * percentage / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}]"


def main():
    parser = argparse.ArgumentParser(
        description="Co-Founder Agent CLI - Your AI co-founder for Sabi"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Dashboard
    subparsers.add_parser("dashboard", help="Show the complete dashboard")
    
    # Check-in
    subparsers.add_parser("checkin", help="Perform a check-in")
    
    # Goal management
    goal_parser = subparsers.add_parser("goal", help="Manage goals")
    goal_sub = goal_parser.add_subparsers(dest="goal_action")
    
    goal_create = goal_sub.add_parser("create", help="Create a new goal")
    goal_create.add_argument("title", help="Goal title")
    goal_create.add_argument("description", help="Goal description")
    goal_create.add_argument("--priority", choices=["low", "medium", "high", "critical"])
    goal_create.add_argument("--target-date", help="Target completion date (ISO format)")
    
    goal_sub.add_parser("list", help="List active goals")
    
    goal_show = goal_sub.add_parser("show", help="Show goal details")
    goal_show.add_argument("goal_id", help="Goal ID")
    
    # Task management
    task_parser = subparsers.add_parser("task", help="Manage tasks")
    task_sub = task_parser.add_subparsers(dest="task_action")
    
    task_create = task_sub.add_parser("create", help="Create a new task")
    task_create.add_argument("goal_id", help="Goal ID")
    task_create.add_argument("title", help="Task title")
    task_create.add_argument("description", help="Task description")
    task_create.add_argument("--priority", choices=["low", "medium", "high", "critical"])
    task_create.add_argument("--assigned-to", choices=["user", "agent"], default="user")
    
    task_complete = task_sub.add_parser("complete", help="Mark task as complete")
    task_complete.add_argument("task_id", help="Task ID")
    
    task_list = task_sub.add_parser("list", help="List tasks")
    task_list.add_argument("--goal-id", help="Filter by goal ID")
    
    # Opportunity management
    opp_parser = subparsers.add_parser("opportunity", help="Manage opportunities")
    opp_sub = opp_parser.add_subparsers(dest="opp_action")
    
    opp_sub.add_parser("scan", help="Scan for new opportunities")
    
    opp_add = opp_sub.add_parser("add", help="Add an opportunity manually")
    opp_add.add_argument("title", help="Opportunity title")
    opp_add.add_argument("type", choices=["grant", "accelerator", "competition", "partnership", "funding", "other"])
    opp_add.add_argument("description", help="Description")
    opp_add.add_argument("source", help="Source of the opportunity")
    opp_add.add_argument("--url", help="URL")
    opp_add.add_argument("--deadline", help="Deadline (ISO format)")
    opp_add.add_argument("--amount", help="Amount (e.g., '$50,000')")
    
    opp_sub.add_parser("list", help="List active opportunities")
    
    # Commitments
    commit_parser = subparsers.add_parser("commit", help="Create a commitment")
    commit_parser.add_argument("description", help="What you're committing to")
    commit_parser.add_argument("--due-date", help="Due date (ISO format)")
    commit_parser.add_argument("--task-id", help="Link to a task ID")
    
    # Next actions
    subparsers.add_parser("next", help="Show next actions")
    
    # Report
    subparsers.add_parser("report", help="Generate weekly report")
    
    # Think
    think_parser = subparsers.add_parser("think", help="Get strategic thoughts on a goal")
    think_parser.add_argument("goal_id", help="Goal ID")
    
    # Config
    config_parser = subparsers.add_parser("config", help="View or update configuration")
    config_parser.add_argument("--show", action="store_true", help="Show current config")
    config_parser.add_argument("--set", help="Set config value (format: key=value)")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    cli = CofounderCLI()
    cli.run(args)


if __name__ == "__main__":
    main()
