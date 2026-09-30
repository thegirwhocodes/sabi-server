# Co-Founder Agent for Sabi

An AI agent that acts as your strategic co-founder, handling operations, accountability, and thought partnership for Sabi.

## What It Does

Your Co-Founder Agent is designed to be your operational partner for Sabi. It:

- **Strategic Planning**: Takes your high-level goals and breaks them into actionable tasks
- **Accountability**: Keeps you on track with commitments and deadlines (and doesn't relent until things are done!)
- **Opportunity Monitoring**: Scans for and tracks grants, accelerators, partnerships, and other opportunities
- **Thought Partnership**: Provides strategic insights and helps think through complex decisions
- **Operational Management**: Tracks all the moving pieces so you can focus on execution

## Architecture

The agent is built with several interconnected systems:

```
┌─────────────────────────────────────┐
│      Co-Founder Agent Core          │
├─────────────────────────────────────┤
│                                     │
│  ┌───────────────┐  ┌────────────┐ │
│  │ Agent Memory  │  │   Goals    │ │
│  │  • Context    │  │ • Tasks    │ │
│  │  • History    │  │ • Progress │ │
│  └───────────────┘  └────────────┘ │
│                                     │
│  ┌───────────────┐  ┌────────────┐ │
│  │Opportunities  │  │Accountability│
│  │• Scanning     │  │• Commitments│ │
│  │• Tracking     │  │• Reminders  │ │
│  └───────────────┘  └────────────┘ │
│                                     │
└─────────────────────────────────────┘
           │
           ▼
    ┌──────────┐
    │   CLI    │
    └──────────┘
```

## Quick Start

### 1. Set up a goal

```bash
python cofounder_agent/cli.py goal create \
  "Secure $100k in grant funding" \
  "Research and apply to relevant education grants for Sabi" \
  --priority high \
  --target-date 2026-12-31
```

The agent will automatically break this down into actionable tasks.

### 2. Check in regularly

```bash
python cofounder_agent/cli.py checkin
```

This shows you what needs attention, upcoming deadlines, and keeps you accountable.

### 3. View your dashboard

```bash
python cofounder_agent/cli.py dashboard
```

Get a complete overview of all goals, tasks, opportunities, and accountability metrics.

## CLI Commands

### Dashboard & Status

```bash
# View complete dashboard
python cofounder_agent/cli.py dashboard

# Perform a check-in
python cofounder_agent/cli.py checkin

# See next actions
python cofounder_agent/cli.py next

# Generate weekly report
python cofounder_agent/cli.py report
```

### Goal Management

```bash
# Create a goal
python cofounder_agent/cli.py goal create "Goal Title" "Description" --priority high

# List active goals
python cofounder_agent/cli.py goal list

# Show goal details and get strategic thoughts
python cofounder_agent/cli.py goal show <goal_id>

# Get strategic thoughts on a goal
python cofounder_agent/cli.py think <goal_id>
```

### Task Management

```bash
# Create a task for a goal
python cofounder_agent/cli.py task create <goal_id> "Task Title" "Description"

# List your pending tasks
python cofounder_agent/cli.py task list

# Mark a task as complete
python cofounder_agent/cli.py task complete <task_id>
```

### Opportunity Management

```bash
# Scan for opportunities
python cofounder_agent/cli.py opportunity scan

# Add an opportunity manually
python cofounder_agent/cli.py opportunity add \
  "Grant Name" grant "Description" "Source" \
  --deadline 2026-12-31 --amount "$50,000"

# List active opportunities
python cofounder_agent/cli.py opportunity list
```

### Accountability

```bash
# Create a commitment
python cofounder_agent/cli.py commit "Finish grant application" --due-date 2026-11-15

# The agent will automatically:
# - Track your commitment
# - Send reminders as the deadline approaches
# - Mark it overdue if you miss it
# - Keep prompting you until it's done!
```

### Configuration

```bash
# View current configuration
python cofounder_agent/cli.py config --show

# Update a config value
python cofounder_agent/cli.py config --set "reminder_style=direct"
python cofounder_agent/cli.py config --set "user_name=Naomi"
```

## Configuration Options

Edit `cofounder_agent/config.json` or use the CLI:

- **user_name**: Your name (for personalized messages)
- **reminder_style**: "supportive_persistent" (default), "direct", or "gentle"
- **check_in_frequency_hours**: How often to check in (default: 24)
- **auto_actions_enabled**: Whether agent can take autonomous actions (default: false)
- **opportunity_scan_enabled**: Auto-scan for opportunities (default: true)
- **opportunity_scan_frequency_days**: Days between scans (default: 7)

## Data Storage

All data is stored locally in JSON files:

```
cofounder_agent/
├── memory/
│   ├── memories.json        # All agent memories
│   ├── context.json          # Current context
│   └── index.json            # Memory index
├── data/
│   ├── goals.json            # Goals
│   ├── tasks.json            # Tasks
│   ├── opportunities.json    # Opportunities
│   ├── commitments.json      # Commitments
│   └── reminders.json        # Reminders
└── config.json               # Configuration
```

## Integration with Sabi

The Co-Founder Agent is designed to work alongside your Sabi development:

1. **Set operational goals** like "Complete pilot study" or "Scale to 1000 users"
2. **Track opportunities** like grants, accelerators, or partnerships
3. **Stay accountable** with deadlines and commitments
4. **Get strategic insights** when you need a thought partner

The agent maintains its own state separate from the Sabi server, so it won't interfere with production operations.

## Extending the Agent

### Adding AI/LLM Integration

The current implementation uses rule-based logic for task breakdown and insights. To add LLM capabilities:

1. Update `_break_down_goal()` in `cofounder_agent.py` to call an LLM
2. Enhance `think_about_goal()` with deeper analysis
3. Add semantic opportunity matching in `opportunity_monitor.py`

### Adding Web Search for Opportunities

To automatically find opportunities:

1. Add web search API calls in `scan_for_opportunities()`
2. Implement scraping for grant databases
3. Set up scheduled scans

### Adding Notifications

To get notifications:

1. Add email/SMS integration in `accountability_system.py`
2. Set up webhook notifications for reminders
3. Integrate with Slack or other messaging platforms

## Example Workflow

```bash
# Monday morning: Check in
python cofounder_agent/cli.py checkin

# Set a weekly goal
python cofounder_agent/cli.py goal create \
  "Complete grant application draft" \
  "Research requirements and write first draft" \
  --priority critical

# View what to do
python cofounder_agent/cli.py next

# Complete a task
python cofounder_agent/cli.py task complete task_20261001_120000_000001

# Add an opportunity you found
python cofounder_agent/cli.py opportunity add \
  "Google AI Impact Grant" grant \
  "Grant for AI education projects" "Google" \
  --deadline 2026-11-30 --amount "$100,000"

# Friday: Review the week
python cofounder_agent/cli.py report
```

## Philosophy

This agent embodies the qualities of a great co-founder:

- **Relentless**: It doesn't let things slip through the cracks
- **Strategic**: Helps think through complex decisions
- **Accountable**: Keeps you on track with commitments
- **Proactive**: Scans for opportunities and prompts action
- **Organized**: Tracks all the operational details
- **Supportive**: Provides encouragement and insights

Think of it as your always-available co-founder who's laser-focused on moving Sabi forward.

## License

Private - Part of Education for Equality / Sabi

## Support

For questions or issues, contact the development team or check the codebase documentation.
