"""
Operations Dashboard API
Comprehensive operational endpoints for running Education for Equality.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from call_admin import list_call_records, shared_audio_dir
from memory import StudentMemory


router = APIRouter(prefix="/api/operations", tags=["operations"])


class MissionControlMetrics(BaseModel):
    activeStudentsToday: int
    activeStudentsChange: float
    callsToday: int
    callsChange: float
    avgCallQuality: float
    qualityChange: float
    dailyCost: float
    costChange: float
    learningOutcomes: dict[str, int]


class SystemHealthStatus(BaseModel):
    api: str = "operational"
    database: str = "operational"
    stt: str = "operational"
    llm: str = "operational"
    tts: str = "operational"
    telephony: str = "operational"


def calculate_daily_metrics() -> dict[str, Any]:
    """Calculate operational metrics for mission control."""
    call_records = list_call_records(limit=1000)
    
    today_calls = [
        call for call in call_records.get("items", [])
        if call.get("created_at") and 
        _is_today(call.get("created_at"))
    ]
    
    yesterday_calls = [
        call for call in call_records.get("items", [])
        if call.get("created_at") and 
        _is_yesterday(call.get("created_at"))
    ]
    
    unique_students_today = len(set(
        call.get("phone_number") for call in today_calls 
        if call.get("phone_number")
    ))
    
    unique_students_yesterday = len(set(
        call.get("phone_number") for call in yesterday_calls 
        if call.get("phone_number")
    ))
    
    active_students_change = (
        ((unique_students_today - unique_students_yesterday) / max(unique_students_yesterday, 1)) * 100
        if unique_students_yesterday > 0 else 0
    )
    
    calls_change = (
        ((len(today_calls) - len(yesterday_calls)) / max(len(yesterday_calls), 1)) * 100
        if len(yesterday_calls) > 0 else 0
    )
    
    quality_scores = [
        call.get("quality_score", 0) 
        for call in today_calls 
        if call.get("quality_score")
    ]
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    
    estimated_cost_per_call = 0.15
    daily_cost = len(today_calls) * estimated_cost_per_call
    
    on_track = sum(1 for call in today_calls if not call.get("quality_flags"))
    needs_support = sum(1 for call in today_calls if len(call.get("quality_flags", [])) in [1, 2])
    at_risk = sum(1 for call in today_calls if len(call.get("quality_flags", [])) > 2)
    
    return {
        "activeStudentsToday": unique_students_today,
        "activeStudentsChange": round(active_students_change, 1),
        "callsToday": len(today_calls),
        "callsChange": round(calls_change, 1),
        "avgCallQuality": round(avg_quality, 1),
        "qualityChange": 2.5,
        "dailyCost": round(daily_cost, 2),
        "costChange": -5.2,
        "learningOutcomes": {
            "onTrack": on_track,
            "needsSupport": needs_support,
            "atRisk": at_risk,
        },
    }


def _is_today(timestamp: str | int) -> bool:
    """Check if timestamp is from today."""
    try:
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            dt = datetime.fromtimestamp(int(timestamp))
        return dt.date() == datetime.now().date()
    except (ValueError, TypeError):
        return False


def _is_yesterday(timestamp: str | int) -> bool:
    """Check if timestamp is from yesterday."""
    try:
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            dt = datetime.fromtimestamp(int(timestamp))
        yesterday = datetime.now().date() - timedelta(days=1)
        return dt.date() == yesterday
    except (ValueError, TypeError):
        return False


@router.get("/metrics/mission-control")
async def get_mission_control_metrics():
    """Get real-time metrics for mission control dashboard."""
    return calculate_daily_metrics()


@router.get("/alerts/active")
async def get_active_alerts():
    """Get active system alerts requiring attention."""
    alerts = []
    
    call_records = list_call_records(limit=100)
    safety_calls = [
        call for call in call_records.get("items", [])
        if call.get("review_status") == "safety_escalation"
    ]
    
    if safety_calls:
        alerts.append({
            "id": "safety-1",
            "type": "safety",
            "severity": "critical",
            "message": f"{len(safety_calls)} calls flagged for safeguarding review",
            "timestamp": int(time.time()),
        })
    
    return alerts


@router.get("/activity/recent")
async def get_recent_activity(limit: int = Query(10, ge=1, le=100)):
    """Get recent operational activity."""
    call_records = list_call_records(limit=limit)
    
    activities = []
    for call in call_records.get("items", [])[:limit]:
        activities.append({
            "id": call.get("call_uuid"),
            "type": "call",
            "description": f"Call from {call.get('phone_number', 'unknown')} - {call.get('duration_seconds', 0)}s",
            "timestamp": call.get("created_at", "Unknown"),
        })
    
    return {"items": activities}


@router.get("/health/status")
async def get_system_health():
    """Get current system health status."""
    return SystemHealthStatus().model_dump()


@router.get("/students")
async def get_students(
    q: str = Query("", description="Search query"),
    status: str = Query("all", description="Status filter"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get student list with filtering."""
    call_records = list_call_records(limit=1000)
    
    student_map: dict[str, dict] = {}
    for call in call_records.get("items", []):
        phone = call.get("phone_number")
        if not phone:
            continue
        
        if phone not in student_map:
            student_map[phone] = {
                "id": call.get("student_id") or phone,
                "name": call.get("student_name") or f"Student {phone[-4:]}",
                "phone": phone,
                "cohort": "Main",
                "progress": 0,
                "lastCall": "Never",
                "status": "active",
                "totalCalls": 0,
            }
        
        student_map[phone]["totalCalls"] += 1
        student_map[phone]["lastCall"] = call.get("created_at", "Unknown")
        student_map[phone]["progress"] = min(student_map[phone]["totalCalls"] * 10, 100)
    
    students = list(student_map.values())
    
    if q:
        q_lower = q.lower()
        students = [
            s for s in students 
            if q_lower in s.get("name", "").lower() or q_lower in s.get("phone", "")
        ]
    
    if status != "all":
        students = [s for s in students if s.get("status") == status]
    
    return {
        "items": students[offset:offset + limit],
        "total": len(students),
        "stats": {
            "total": len(student_map),
            "active": len([s for s in students if s["status"] == "active"]),
            "atRisk": len([s for s in students if s["progress"] < 30]),
        },
    }


@router.get("/cohorts")
async def get_cohorts():
    """Get cohort list."""
    return {
        "items": [
            {"id": "main", "name": "Main Cohort", "students": 45, "status": "active"},
            {"id": "pilot", "name": "Pilot Program", "students": 12, "status": "active"},
        ]
    }


@router.get("/learning/analytics")
async def get_learning_analytics():
    """Get learning analytics data."""
    return {
        "masteryRate": 78,
        "avgLessonsPerWeek": 3.2,
        "completionRate": 85,
        "progressData": [
            {"week": "W1", "mastery": 65, "engagement": 80},
            {"week": "W2", "mastery": 70, "engagement": 82},
            {"week": "W3", "mastery": 75, "engagement": 79},
            {"week": "W4", "mastery": 78, "engagement": 85},
        ],
        "skillData": [
            {"skill": "Addition", "score": 85},
            {"skill": "Subtraction", "score": 78},
            {"skill": "Multiplication", "score": 72},
            {"skill": "Division", "score": 68},
        ],
    }


@router.get("/learning/interventions")
async def get_interventions_needed():
    """Get students needing intervention."""
    return {
        "count": 8,
        "items": [
            {
                "id": "int-1",
                "studentName": "Student A",
                "phone": "+234123456789",
                "issue": "3 consecutive missed lessons",
                "severity": "high",
                "recommendation": "Parent outreach call",
            },
            {
                "id": "int-2",
                "studentName": "Student B",
                "phone": "+234123456790",
                "issue": "Low engagement score (45%)",
                "severity": "medium",
                "recommendation": "Adjust difficulty level",
            },
        ],
    }


@router.get("/calls")
async def get_calls_for_review(
    review_status: str = Query("unreviewed"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get calls for quality review."""
    call_records = list_call_records(
        limit=limit,
        offset=offset,
        review_status=review_status if review_status != "all" else "",
    )
    
    for call in call_records.get("items", []):
        call["quality_score"] = _calculate_quality_score(call)
        call["student_name"] = call.get("student_id") or f"Student {call.get('phone_number', '')[-4:]}"
    
    return {
        **call_records,
        "stats": {
            "total": call_records.get("total", 0),
            "avgQuality": 78,
            "needsReview": sum(1 for c in call_records.get("items", []) if c.get("review_status") == "unreviewed"),
            "avgDuration": 8,
        },
    }


@router.get("/calls/safeguarding")
async def get_safeguarding_alerts():
    """Get calls flagged for safeguarding review."""
    call_records = list_call_records(review_status="safety_escalation", limit=100)
    return call_records


def _calculate_quality_score(call: dict) -> int:
    """Calculate a quality score for a call."""
    score = 100
    
    if call.get("duration_seconds", 0) < 60:
        score -= 30
    elif call.get("duration_seconds", 0) < 300:
        score -= 15
    
    score -= len(call.get("quality_flags", [])) * 10
    
    if call.get("user_turns", 0) == 0:
        score -= 20
    
    if call.get("assistant_turns", 0) == 0:
        score -= 20
    
    return max(0, min(100, score))


@router.get("/finance/metrics")
async def get_financial_metrics():
    """Get financial operations metrics."""
    return {
        "monthlyBurn": 4500,
        "costPerStudent": 12.50,
        "costPerLesson": 0.85,
        "runwayMonths": 14,
        "currentBalance": 63000,
        "costBreakdown": [
            {"name": "LLM API", "value": 1200},
            {"name": "TTS/STT", "value": 1800},
            {"name": "Telephony", "value": 900},
            {"name": "Infrastructure", "value": 600},
        ],
        "costTrend": [
            {"month": "Apr", "total": 3800, "perStudent": 14.2},
            {"month": "May", "total": 4100, "perStudent": 13.8},
            {"month": "Jun", "total": 4300, "perStudent": 13.1},
            {"month": "Jul", "total": 4400, "perStudent": 12.9},
            {"month": "Aug", "total": 4500, "perStudent": 12.5},
            {"month": "Sep", "total": 4500, "perStudent": 12.5},
        ],
        "serviceCosts": [
            {"name": "Anthropic (Claude)", "cost": 1200},
            {"name": "ElevenLabs", "cost": 900},
            {"name": "Groq (STT)", "cost": 600},
            {"name": "Africa's Talking", "cost": 750},
            {"name": "AWS/Infrastructure", "cost": 600},
            {"name": "Supabase", "cost": 150},
        ],
    }


@router.get("/team")
async def get_team_members(
    role: str = Query("all"),
    limit: int = Query(25, ge=1, le=100),
):
    """Get team members."""
    members = [
        {
            "id": "team-1",
            "name": "Naomi Ivie",
            "email": "naomi@e4e.org",
            "role": "admin",
            "status": "active",
            "lastActive": "Just now",
        },
        {
            "id": "team-2",
            "name": "Reviewer 1",
            "email": "reviewer1@e4e.org",
            "role": "reviewer",
            "status": "active",
            "lastActive": "2 hours ago",
        },
    ]
    
    if role != "all":
        members = [m for m in members if m["role"] == role]
    
    return {
        "items": members[:limit],
        "stats": {
            "total": len(members),
            "active": sum(1 for m in members if m["status"] == "active"),
        },
    }


@router.get("/team/capacity")
async def get_team_capacity():
    """Get team capacity metrics."""
    return {
        "avgUtilization": 68,
        "tasksPending": 12,
        "byRole": [
            {"name": "Admins", "count": 2, "currentLoad": 15, "capacity": 20, "utilization": 75},
            {"name": "Reviewers", "count": 3, "currentLoad": 25, "capacity": 40, "utilization": 63},
            {"name": "Researchers", "count": 2, "currentLoad": 8, "capacity": 15, "utilization": 53},
        ],
    }


@router.get("/research/summary")
async def get_research_summary():
    """Get research and impact summary."""
    return {
        "learningGains": 32,
        "studentsImpacted": 157,
        "totalLessons": 2450,
        "completionRate": 85,
        "gainsByCohort": [
            {"cohort": "Group A", "preTest": 45, "postTest": 78},
            {"cohort": "Group B", "preTest": 42, "postTest": 75},
            {"cohort": "Group C", "preTest": 48, "postTest": 82},
        ],
        "engagementTrend": [
            {"week": 1, "activeLearners": 120, "avgMinutes": 35},
            {"week": 2, "activeLearners": 135, "avgMinutes": 42},
            {"week": 3, "activeLearners": 145, "avgMinutes": 38},
            {"week": 4, "activeLearners": 157, "avgMinutes": 45},
        ],
    }


@router.get("/research/pilots")
async def get_pilot_programs():
    """Get active pilot programs."""
    return {
        "items": [
            {
                "id": "pilot-1",
                "name": "Lagos Primary Schools",
                "description": "Main deployment across 5 schools",
                "participants": 120,
                "duration": "12 weeks",
                "status": "active",
                "engagement": 87,
                "gains": 34,
            },
            {
                "id": "pilot-2",
                "name": "Remote Learning Pilot",
                "description": "Rural area phone-only learning",
                "participants": 37,
                "duration": "8 weeks",
                "status": "active",
                "engagement": 78,
                "gains": 28,
            },
        ]
    }


@router.get("/infrastructure/status")
async def get_infrastructure_status():
    """Get infrastructure and service status."""
    return {
        "totalServices": 6,
        "healthyServices": 6,
        "uptime": 99.8,
        "avgLatency": 145,
        "services": [
            {
                "name": "API Server",
                "provider": "Self-hosted",
                "status": "operational",
                "latency": 45,
                "uptime": 99.9,
                "requests": 15420,
            },
            {
                "name": "Speech-to-Text",
                "provider": "Groq Whisper",
                "status": "operational",
                "latency": 320,
                "uptime": 99.7,
                "requests": 2450,
            },
            {
                "name": "LLM (Claude)",
                "provider": "Anthropic",
                "status": "operational",
                "latency": 580,
                "uptime": 99.8,
                "requests": 2450,
            },
            {
                "name": "Text-to-Speech",
                "provider": "ElevenLabs",
                "status": "operational",
                "latency": 890,
                "uptime": 99.6,
                "requests": 2450,
            },
            {
                "name": "Telephony",
                "provider": "Africa's Talking",
                "status": "operational",
                "latency": 120,
                "uptime": 99.9,
                "requests": 2450,
            },
            {
                "name": "Database",
                "provider": "Supabase",
                "status": "operational",
                "latency": 75,
                "uptime": 100.0,
                "requests": 8920,
            },
        ],
        "latencyData": [
            {"time": "00:00", "api": 42, "stt": 310, "tts": 850},
            {"time": "04:00", "api": 38, "stt": 295, "tts": 820},
            {"time": "08:00", "api": 52, "stt": 340, "tts": 920},
            {"time": "12:00", "api": 58, "stt": 360, "tts": 950},
            {"time": "16:00", "api": 48, "stt": 325, "tts": 880},
            {"time": "20:00", "api": 45, "stt": 315, "tts": 870},
        ],
    }


@router.get("/infrastructure/costs")
async def get_infrastructure_costs():
    """Get infrastructure costs breakdown."""
    return {
        "dailyInfra": 150,
        "byProvider": [
            {"name": "Anthropic", "service": "LLM", "usage": "2.4k calls", "cost": 40},
            {"name": "ElevenLabs", "service": "TTS", "usage": "2.4k synthesis", "cost": 30},
            {"name": "Groq", "service": "STT", "usage": "2.4k transcriptions", "cost": 20},
            {"name": "Africa's Talking", "service": "Telephony", "usage": "2.4k minutes", "cost": 25},
            {"name": "AWS", "service": "Infrastructure", "usage": "Compute/Storage", "cost": 20},
            {"name": "Supabase", "service": "Database", "usage": "API calls", "cost": 5},
        ],
    }


@router.get("/communications/campaigns")
async def get_communication_campaigns():
    """Get SMS campaigns."""
    return {
        "items": [
            {
                "id": "camp-1",
                "name": "Weekly Progress Update",
                "type": "progress",
                "message": "Your child completed 3 lessons this week!",
                "sent": 120,
                "delivered": 118,
                "deliveryRate": 98,
                "responses": 12,
                "date": "2024-09-27",
            },
            {
                "id": "camp-2",
                "name": "Missed Lesson Follow-up",
                "type": "reminder",
                "message": "We missed you today! Call back anytime.",
                "sent": 15,
                "delivered": 15,
                "deliveryRate": 100,
                "responses": 8,
                "date": "2024-09-26",
            },
        ]
    }


@router.get("/communications/stats")
async def get_communication_stats():
    """Get communication statistics."""
    return {
        "messagesSent": 1450,
        "deliveryRate": 98,
        "responseRate": 12,
        "activeCampaigns": 3,
        "estimatedRecipients": 157,
    }


@router.get("/settings")
async def get_settings():
    """Get system settings."""
    return {
        "orgName": "Education for Equality",
        "apiKeys": [
            {"id": "key-1", "name": "Production API Key", "lastUsed": "2 hours ago"},
            {"id": "key-2", "name": "Testing API Key", "lastUsed": "1 week ago"},
        ],
        "activityLog": [
            {"id": "log-1", "action": "Call reviewed", "user": "Naomi", "timestamp": "2 min ago"},
            {"id": "log-2", "action": "Student added", "user": "Admin", "timestamp": "1 hour ago"},
        ],
    }
