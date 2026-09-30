"""
Accountability and Prompting System
Keeps track of commitments and prompts the user to complete tasks.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class CommitmentStatus(Enum):
    """Status of a commitment."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    MISSED = "missed"


@dataclass
class Commitment:
    """A commitment made by the user."""
    id: str
    task_id: Optional[str]
    description: str
    due_date: str
    status: CommitmentStatus
    reminder_count: int
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    notes: str = ""
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Commitment':
        data['status'] = CommitmentStatus(data['status'])
        return cls(**data)


@dataclass
class Reminder:
    """A reminder to prompt the user."""
    id: str
    commitment_id: Optional[str]
    message: str
    scheduled_for: str
    sent_at: Optional[str]
    acknowledged: bool
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Reminder':
        return cls(**data)


class AccountabilitySystem:
    """
    Keeps the user accountable by tracking commitments and sending reminders.
    Acts as the "relentless" co-founder that doesn't let things slip.
    """
    
    def __init__(self, data_dir: str = "cofounder_agent/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.commitments_file = self.data_dir / "commitments.json"
        self.reminders_file = self.data_dir / "reminders.json"
        
        self.commitments: Dict[str, Commitment] = {}
        self.reminders: Dict[str, Reminder] = {}
        
        self._load()
    
    def _load(self):
        """Load commitments and reminders from disk."""
        if self.commitments_file.exists():
            with open(self.commitments_file, 'r') as f:
                data = json.load(f)
                self.commitments = {
                    c_id: Commitment.from_dict(c_data)
                    for c_id, c_data in data.items()
                }
        
        if self.reminders_file.exists():
            with open(self.reminders_file, 'r') as f:
                data = json.load(f)
                self.reminders = {
                    r_id: Reminder.from_dict(r_data)
                    for r_id, r_data in data.items()
                }
    
    def _save(self):
        """Save commitments and reminders to disk."""
        with open(self.commitments_file, 'w') as f:
            data = {c_id: c.to_dict() for c_id, c in self.commitments.items()}
            json.dump(data, f, indent=2)
        
        with open(self.reminders_file, 'w') as f:
            data = {r_id: r.to_dict() for r_id, r in self.reminders.items()}
            json.dump(data, f, indent=2)
    
    def create_commitment(
        self,
        description: str,
        due_date: str,
        task_id: Optional[str] = None,
        notes: str = ""
    ) -> str:
        """Create a new commitment."""
        commitment_id = f"commit_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        now = datetime.now().isoformat()
        
        commitment = Commitment(
            id=commitment_id,
            task_id=task_id,
            description=description,
            due_date=due_date,
            status=CommitmentStatus.PENDING,
            reminder_count=0,
            created_at=now,
            updated_at=now,
            notes=notes
        )
        
        self.commitments[commitment_id] = commitment
        self._save()
        
        # Automatically schedule reminders
        self._schedule_reminders_for_commitment(commitment_id)
        
        return commitment_id
    
    def update_commitment_status(
        self,
        commitment_id: str,
        status: CommitmentStatus,
        notes: Optional[str] = None
    ):
        """Update a commitment's status."""
        if commitment_id not in self.commitments:
            raise ValueError(f"Commitment {commitment_id} not found")
        
        commitment = self.commitments[commitment_id]
        commitment.status = status
        commitment.updated_at = datetime.now().isoformat()
        
        if status == CommitmentStatus.COMPLETED:
            commitment.completed_at = datetime.now().isoformat()
        
        if notes:
            commitment.notes = notes
        
        self._save()
    
    def _schedule_reminders_for_commitment(self, commitment_id: str):
        """Schedule automatic reminders for a commitment."""
        commitment = self.commitments[commitment_id]
        due_date = datetime.fromisoformat(commitment.due_date)
        
        # Schedule reminders at:
        # - 1 day before
        # - On the due date
        # - 1 day after (if not completed)
        
        reminder_times = [
            (due_date - timedelta(days=1), "Tomorrow is the deadline for"),
            (due_date, "Today is the deadline for"),
            (due_date + timedelta(days=1), "This is now overdue")
        ]
        
        for reminder_time, prefix in reminder_times:
            self.schedule_reminder(
                message=f"{prefix}: {commitment.description}",
                scheduled_for=reminder_time.isoformat(),
                commitment_id=commitment_id
            )
    
    def schedule_reminder(
        self,
        message: str,
        scheduled_for: str,
        commitment_id: Optional[str] = None
    ) -> str:
        """Schedule a reminder."""
        reminder_id = f"remind_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        reminder = Reminder(
            id=reminder_id,
            commitment_id=commitment_id,
            message=message,
            scheduled_for=scheduled_for,
            sent_at=None,
            acknowledged=False
        )
        
        self.reminders[reminder_id] = reminder
        self._save()
        return reminder_id
    
    def get_pending_reminders(self) -> List[Reminder]:
        """Get all reminders that should be sent now."""
        now = datetime.now().isoformat()
        return [
            r for r in self.reminders.values()
            if not r.sent_at and r.scheduled_for <= now
        ]
    
    def mark_reminder_sent(self, reminder_id: str):
        """Mark a reminder as sent."""
        if reminder_id not in self.reminders:
            raise ValueError(f"Reminder {reminder_id} not found")
        
        reminder = self.reminders[reminder_id]
        reminder.sent_at = datetime.now().isoformat()
        
        # Increment commitment reminder count
        if reminder.commitment_id:
            commitment = self.commitments.get(reminder.commitment_id)
            if commitment:
                commitment.reminder_count += 1
        
        self._save()
    
    def acknowledge_reminder(self, reminder_id: str):
        """Mark a reminder as acknowledged by the user."""
        if reminder_id not in self.reminders:
            raise ValueError(f"Reminder {reminder_id} not found")
        
        self.reminders[reminder_id].acknowledged = True
        self._save()
    
    def check_overdue_commitments(self):
        """Check for overdue commitments and update their status."""
        now = datetime.now().isoformat()
        
        for commitment in self.commitments.values():
            if (commitment.status in [CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS]
                and commitment.due_date < now):
                commitment.status = CommitmentStatus.OVERDUE
        
        self._save()
    
    def get_active_commitments(self) -> List[Commitment]:
        """Get all active commitments."""
        return [
            c for c in self.commitments.values()
            if c.status in [CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS, CommitmentStatus.OVERDUE]
        ]
    
    def get_overdue_commitments(self) -> List[Commitment]:
        """Get all overdue commitments."""
        self.check_overdue_commitments()
        return [
            c for c in self.commitments.values()
            if c.status == CommitmentStatus.OVERDUE
        ]
    
    def get_commitment_history(self, days: int = 30) -> Dict:
        """Get commitment completion history."""
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        recent = [
            c for c in self.commitments.values()
            if c.created_at >= cutoff_str
        ]
        
        completed = len([c for c in recent if c.status == CommitmentStatus.COMPLETED])
        missed = len([c for c in recent if c.status == CommitmentStatus.MISSED])
        total = len(recent)
        
        return {
            "total": total,
            "completed": completed,
            "missed": missed,
            "completion_rate": (completed / total * 100) if total > 0 else 0,
            "recent_commitments": [
                {
                    "description": c.description,
                    "status": c.status.value,
                    "due_date": c.due_date
                }
                for c in sorted(recent, key=lambda x: x.created_at, reverse=True)
            ]
        }
    
    def get_accountability_score(self) -> float:
        """Calculate an accountability score (0-1) based on commitment completion."""
        history = self.get_commitment_history(days=90)
        return history["completion_rate"] / 100 if history["total"] > 0 else 0.5
