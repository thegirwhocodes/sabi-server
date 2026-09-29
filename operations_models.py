"""
Operational Data Models
Database schemas for operational dashboard data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class Student:
    """Student profile with learning progress."""
    
    id: str
    phone_number: str
    name: Optional[str] = None
    cohort: Optional[str] = None
    status: Literal["active", "inactive", "at_risk", "graduated"] = "active"
    enrolled_at: datetime = field(default_factory=datetime.now)
    last_call_at: Optional[datetime] = None
    total_calls: int = 0
    total_lessons_completed: int = 0
    current_level: str = "beginner"
    progress_percentage: int = 0
    engagement_score: float = 0.0
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    notes: str = ""


@dataclass
class Cohort:
    """Learning cohort/group."""
    
    id: str
    name: str
    description: str
    start_date: datetime
    end_date: Optional[datetime] = None
    status: Literal["planning", "active", "completed"] = "planning"
    student_count: int = 0
    target_outcomes: dict = field(default_factory=dict)


@dataclass
class Intervention:
    """Learning intervention for at-risk students."""
    
    id: str
    student_id: str
    issue_type: str
    severity: Literal["low", "medium", "high"] = "medium"
    description: str
    recommendation: str
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    status: Literal["pending", "in_progress", "resolved"] = "pending"


@dataclass
class TeamMember:
    """Team member profile with roles and permissions."""
    
    id: str
    name: str
    email: str
    role: Literal["admin", "reviewer", "researcher", "support"] = "support"
    status: Literal["active", "away", "offline"] = "active"
    created_at: datetime = field(default_factory=datetime.now)
    last_active_at: Optional[datetime] = None
    permissions: list[str] = field(default_factory=list)


@dataclass
class CommunicationCampaign:
    """SMS or communication campaign."""
    
    id: str
    name: str
    message_type: Literal["sms", "reminder", "progress", "announcement"] = "sms"
    message_text: str
    target_audience: str
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    status: Literal["draft", "scheduled", "sending", "sent", "failed"] = "draft"
    recipients_count: int = 0
    delivered_count: int = 0
    failed_count: int = 0
    response_count: int = 0
    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class FinancialRecord:
    """Financial transaction or cost record."""
    
    id: str
    date: datetime
    category: str
    provider: str
    service: str
    amount: float
    currency: str = "USD"
    description: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class SystemAlert:
    """System alert or notification."""
    
    id: str
    alert_type: Literal["safety", "system", "cost", "performance"] = "system"
    severity: Literal["info", "warning", "error", "critical"] = "info"
    title: str
    message: str
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    status: Literal["active", "acknowledged", "resolved"] = "active"
    metadata: dict = field(default_factory=dict)


@dataclass
class ResearchPilot:
    """Research pilot program tracking."""
    
    id: str
    name: str
    description: str
    start_date: datetime
    end_date: Optional[datetime] = None
    status: Literal["planning", "active", "completed", "paused"] = "planning"
    participant_count: int = 0
    control_group_size: int = 0
    intervention_group_size: int = 0
    primary_outcomes: list[str] = field(default_factory=list)
    baseline_metrics: dict = field(default_factory=dict)
    current_metrics: dict = field(default_factory=dict)
    notes: str = ""


@dataclass
class MetricSnapshot:
    """Daily operational metrics snapshot."""
    
    id: str
    date: datetime
    active_students: int
    total_calls: int
    avg_call_duration: float
    avg_quality_score: float
    daily_cost: float
    llm_tokens: int
    stt_minutes: float
    tts_characters: int
    safeguarding_alerts: int
    system_uptime: float
    metadata: dict = field(default_factory=dict)
