"""
FastAPI Web Interface for Co-Founder Agent
Provides REST API and web dashboard.
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from cofounder_agent import CofounderAgent
from goal_manager import Priority, GoalStatus, TaskStatus
from opportunity_monitor import OpportunityType, OpportunityStatus
from accountability_system import CommitmentStatus


app = FastAPI(title="Sabi Co-Founder Agent API")

# Initialize agent
agent = CofounderAgent()


# Request Models
class GoalCreate(BaseModel):
    title: str
    description: str
    priority: str = "medium"
    target_date: Optional[str] = None
    success_criteria: Optional[List[str]] = None


class TaskCreate(BaseModel):
    goal_id: str
    title: str
    description: str
    assigned_to: str = "user"
    priority: str = "medium"
    due_date: Optional[str] = None


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class OpportunityCreate(BaseModel):
    title: str
    type: str
    description: str
    source: str
    url: Optional[str] = None
    deadline: Optional[str] = None
    amount: Optional[str] = None
    requirements: Optional[List[str]] = None


class CommitmentCreate(BaseModel):
    description: str
    due_date: str
    task_id: Optional[str] = None


# API Routes

@app.get("/")
async def root():
    """Redirect to dashboard"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Redirecting...</title>
        <meta http-equiv="refresh" content="0; url=/dashboard">
    </head>
    <body>
        <p>Redirecting to dashboard...</p>
    </body>
    </html>
    """)


@app.get("/api/dashboard")
async def get_dashboard():
    """Get complete dashboard data"""
    try:
        dashboard = agent.get_dashboard()
        return JSONResponse(dashboard)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/checkin")
async def checkin():
    """Perform a check-in"""
    try:
        result = agent.check_in()
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/goals")
async def list_goals():
    """List all active goals"""
    try:
        goals = agent.goals.get_active_goals()
        return JSONResponse({
            "goals": [
                {
                    "id": g.id,
                    "title": g.title,
                    "description": g.description,
                    "status": g.status.value,
                    "priority": g.priority.value,
                    "created_at": g.created_at,
                    "target_date": g.target_date,
                    "progress": agent.goals.calculate_goal_progress(g.id)
                }
                for g in goals
            ]
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/goals")
async def create_goal(goal: GoalCreate):
    """Create a new goal"""
    try:
        result = agent.set_high_level_goal(
            title=goal.title,
            description=goal.description,
            priority=goal.priority,
            target_date=goal.target_date,
            success_criteria=goal.success_criteria
        )
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/goals/{goal_id}")
async def get_goal(goal_id: str):
    """Get goal details with strategic insights"""
    try:
        thought = agent.think_about_goal(goal_id)
        if "error" in thought:
            raise HTTPException(status_code=404, detail=thought["error"])
        return JSONResponse(thought)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks")
async def list_tasks(goal_id: Optional[str] = None):
    """List tasks, optionally filtered by goal"""
    try:
        if goal_id:
            tasks = agent.goals.get_goal_tasks(goal_id)
        else:
            tasks = agent.goals.get_user_pending_tasks()
        
        return JSONResponse({
            "tasks": [
                {
                    "id": t.id,
                    "goal_id": t.goal_id,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status.value,
                    "priority": t.priority.value,
                    "assigned_to": t.assigned_to,
                    "due_date": t.due_date,
                    "created_at": t.created_at
                }
                for t in tasks
            ]
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks")
async def create_task(task: TaskCreate):
    """Create a new task"""
    try:
        task_id = agent.goals.create_task(
            goal_id=task.goal_id,
            title=task.title,
            description=task.description,
            assigned_to=task.assigned_to,
            priority=Priority[task.priority.upper()],
            due_date=task.due_date
        )
        return JSONResponse({"task_id": task_id, "message": "Task created"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: str, update: TaskUpdate):
    """Update a task"""
    try:
        kwargs = {}
        if update.status:
            kwargs["status"] = TaskStatus[update.status.upper()]
        if update.title:
            kwargs["title"] = update.title
        if update.description:
            kwargs["description"] = update.description
        
        agent.goals.update_task(task_id, **kwargs)
        return JSONResponse({"message": "Task updated"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/opportunities")
async def list_opportunities():
    """List all active opportunities"""
    try:
        opps = agent.opportunities.get_active_opportunities()
        return JSONResponse({
            "opportunities": [
                {
                    "id": o.id,
                    "title": o.title,
                    "type": o.type.value,
                    "description": o.description,
                    "status": o.status.value,
                    "source": o.source,
                    "url": o.url,
                    "deadline": o.deadline,
                    "amount": o.amount,
                    "fit_score": o.fit_score,
                    "created_at": o.created_at
                }
                for o in opps
            ]
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/opportunities")
async def create_opportunity(opp: OpportunityCreate):
    """Create a new opportunity"""
    try:
        opp_id = agent.add_opportunity_manual(
            title=opp.title,
            opp_type=opp.type,
            description=opp.description,
            source=opp.source,
            url=opp.url,
            deadline=opp.deadline,
            amount=opp.amount,
            requirements=opp.requirements
        )
        return JSONResponse({"opportunity_id": opp_id, "message": "Opportunity added"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/commitments")
async def create_commitment(commitment: CommitmentCreate):
    """Create a new commitment"""
    try:
        commitment_id = agent.create_commitment(
            description=commitment.description,
            due_date=commitment.due_date,
            task_id=commitment.task_id
        )
        return JSONResponse({"commitment_id": commitment_id, "message": "Commitment created"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/commitments")
async def list_commitments():
    """List active commitments"""
    try:
        commitments = agent.accountability.get_active_commitments()
        return JSONResponse({
            "commitments": [
                {
                    "id": c.id,
                    "description": c.description,
                    "due_date": c.due_date,
                    "status": c.status.value,
                    "created_at": c.created_at
                }
                for c in commitments
            ]
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/next-actions")
async def get_next_actions():
    """Get next actions"""
    try:
        result = agent.get_next_actions()
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/report")
async def get_report():
    """Get weekly report"""
    try:
        report = agent.get_weekly_report()
        return JSONResponse(report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the web dashboard"""
    return HTMLResponse(open(Path(__file__).parent / "static" / "index.html").read())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
