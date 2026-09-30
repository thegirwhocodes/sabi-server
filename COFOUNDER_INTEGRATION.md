# Integrating the Co-Founder Agent with Sabi Server

This guide shows how to integrate the Co-Founder Agent with your Sabi operations.

## Overview

The Co-Founder Agent is a standalone system that complements your Sabi server. While Sabi handles the technical tutoring operations, the Co-Founder Agent handles strategic planning, operations management, and accountability.

## Directory Structure

```
sabi-server/
├── main.py                  # Sabi server
├── llm.py                   # Tutoring logic
├── memory.py                # Student memory
├── ...
└── cofounder_agent/         # NEW: Co-founder agent system
    ├── agent_memory.py
    ├── goal_manager.py
    ├── opportunity_monitor.py
    ├── accountability_system.py
    ├── cofounder_agent.py
    ├── cli.py
    ├── README.md
    └── QUICKSTART.md
```

## Daily Workflow

### 1. Morning Check-In

Start your day by checking in with your co-founder:

```bash
python cofounder_agent/cli.py checkin
```

This shows you:
- What needs your attention today
- Overdue commitments
- Next priority actions
- Goal progress

### 2. Set Weekly Goals

Every Monday, set or review your goals:

```bash
# View current goals
python cofounder_agent/cli.py goal list

# Add new goals as needed
python cofounder_agent/cli.py goal create \
  "Your Goal" "Description" --priority high
```

### 3. Track Opportunities

When you find grants, accelerators, or partnerships:

```bash
python cofounder_agent/cli.py opportunity add \
  "Opportunity Name" grant \
  "Description" "Source" \
  --deadline YYYY-MM-DD
```

### 4. Make Commitments

When you commit to something:

```bash
python cofounder_agent/cli.py commit \
  "What you're committing to" \
  --due-date YYYY-MM-DD
```

The agent will hold you accountable!

### 5. Weekly Review

Every Friday:

```bash
python cofounder_agent/cli.py report
```

## Integration Examples

### Example 1: Track User Growth Goal

```bash
# Set a growth goal
python cofounder_agent/cli.py goal create \
  "Reach 1000 active Sabi users" \
  "Grow user base through partnerships and marketing" \
  --priority critical

# Add related tasks
# (automatically created by the agent)

# Track a partnership opportunity
python cofounder_agent/cli.py opportunity add \
  "Partnership with Lagos Education Board" partnership \
  "Potential to reach 50 schools in Lagos" "Lagos State" \
  --deadline 2026-12-01

# Commit to next steps
python cofounder_agent/cli.py commit \
  "Send partnership proposal to Lagos Education Board" \
  --due-date 2026-10-10
```

### Example 2: Track Fundraising

```bash
# Set fundraising goal
python cofounder_agent/cli.py goal create \
  "Raise $500k seed round" \
  "Secure seed funding to scale Sabi operations" \
  --priority critical

# Track each opportunity
python cofounder_agent/cli.py opportunity add \
  "Y Combinator W27 Application" accelerator \
  "3-month accelerator + $500k investment" "Y Combinator" \
  --deadline 2026-10-15

python cofounder_agent/cli.py opportunity add \
  "Google for Startups" grant \
  "Grant for AI education startups" "Google" \
  --deadline 2026-11-01 --amount "$100,000"
```

### Example 3: Track Product Development

```bash
# Product milestone goal
python cofounder_agent/cli.py goal create \
  "Launch v2.0 with parent dashboard" \
  "Build and launch new features for parents" \
  --priority high --target-date 2026-12-31

# Break down into tasks (done automatically)
# Then commit to milestones
python cofounder_agent/cli.py commit \
  "Complete dashboard mockups" \
  --due-date 2026-10-20

python cofounder_agent/cli.py commit \
  "Backend API for parent portal" \
  --due-date 2026-11-15
```

## Separating Concerns

### Sabi Server Handles:
- Voice tutoring operations
- Speech-to-text processing
- LLM curriculum delivery
- Student memory and progress
- Call handling and telephony

### Co-Founder Agent Handles:
- Strategic goal setting
- Task breakdown and tracking
- Opportunity monitoring (grants, partnerships)
- Accountability and reminders
- Operational planning
- Progress reporting

They're independent systems that work together to help you build Sabi.

## Automation Ideas

### 1. Daily Reminder

Add to your crontab:

```bash
0 9 * * * cd /workspace && python cofounder_agent/cli.py checkin | mail -s "Daily Sabi Check-in" your@email.com
```

### 2. Weekly Report

```bash
0 17 * * 5 cd /workspace && python cofounder_agent/cli.py report | mail -s "Weekly Sabi Report" your@email.com
```

### 3. Opportunity Scanning

The agent can automatically scan for opportunities:

```bash
python cofounder_agent/cli.py opportunity scan
```

Set this to run weekly via cron.

## API Integration (Future)

You can also use the agent programmatically:

```python
from cofounder_agent import CofounderAgent

agent = CofounderAgent()

# Set a goal
goal_id = agent.set_high_level_goal(
    title="Your goal",
    description="Description",
    priority="high"
)

# Check in
result = agent.check_in()
print(result["message"])

# Get dashboard
dashboard = agent.get_dashboard()
```

See `cofounder_agent/example_usage.py` for more examples.

## Configuration

Customize your agent in `cofounder_agent/config.json`:

```json
{
  "agent_name": "Co-Founder Agent",
  "user_name": "Naomi",
  "check_in_frequency_hours": 24,
  "reminder_style": "supportive_persistent",
  "auto_actions_enabled": false,
  "opportunity_scan_enabled": true,
  "opportunity_scan_frequency_days": 7
}
```

## Data Persistence

All agent data is stored in:
- `cofounder_agent/memory/` - Memories and context
- `cofounder_agent/data/` - Goals, tasks, opportunities, commitments

These are separate from Sabi's operational data and safe to backup independently.

## Best Practices

1. **Check in daily**: Make `checkin` part of your morning routine
2. **Be specific**: Detailed goals get better tracking
3. **Track everything**: Use the agent for all operational goals
4. **Review weekly**: Run `report` every Friday
5. **Let it hold you accountable**: Don't ignore reminders!

## Getting Help

Run any command with `-h` for help:

```bash
python cofounder_agent/cli.py -h
python cofounder_agent/cli.py goal -h
python cofounder_agent/cli.py task -h
```

## Next Steps

1. Run the quick start: `python cofounder_agent/example_usage.py`
2. Set your first goal
3. Make it part of your daily routine
4. Let your AI co-founder help you build Sabi! 🚀
