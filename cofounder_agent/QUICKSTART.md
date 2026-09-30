# Co-Founder Agent Quick Start

Get your AI co-founder up and running in 5 minutes!

## Step 1: First Run

```bash
cd /workspace
python cofounder_agent/cli.py dashboard
```

This initializes the agent and shows you the empty dashboard.

## Step 2: Set Your First Goal

Let's set a goal for Sabi. Here's an example:

```bash
python cofounder_agent/cli.py goal create \
  "Reach 100 active Sabi users" \
  "Grow our user base from pilot to 100 active daily users through outreach and partnerships" \
  --priority high
```

The agent will:
- Create the goal
- Break it down into 5 initial tasks
- Track it in your dashboard

## Step 3: Check Your Dashboard

```bash
python cofounder_agent/cli.py dashboard
```

You'll now see:
- Your active goal
- Auto-generated tasks
- Progress tracking

## Step 4: Add an Opportunity

Found a grant or accelerator? Add it:

```bash
python cofounder_agent/cli.py opportunity add \
  "Google for Startups Accelerator Africa" \
  accelerator \
  "3-month accelerator program for African startups with AI products" \
  "Google" \
  --deadline 2026-12-01 \
  --url "https://startup.google.com/accelerator/africa/"
```

The agent will:
- Calculate how well it fits Sabi
- Track the deadline
- Remind you as it approaches

## Step 5: Make a Commitment

Commit to something and let the agent hold you accountable:

```bash
python cofounder_agent/cli.py commit \
  "Send outreach emails to 10 potential partner schools" \
  --due-date 2026-10-05
```

The agent will:
- Track your commitment
- Remind you before the deadline
- Mark it overdue if you miss it
- Keep prompting you until it's done!

## Step 6: Daily Check-In

Make this part of your daily routine:

```bash
python cofounder_agent/cli.py checkin
```

This shows you:
- What needs your attention
- Overdue items
- Next actions
- Goal progress

## Step 7: Complete Tasks

When you finish something:

```bash
# First, list your tasks to get the ID
python cofounder_agent/cli.py task list

# Then mark it complete
python cofounder_agent/cli.py task complete <task_id>
```

## Step 8: Weekly Review

Every Friday, run:

```bash
python cofounder_agent/cli.py report
```

This gives you:
- Week's activity summary
- Accountability score
- Completion rate
- What got done

## Customize Your Agent

Set your preferences:

```bash
# Your name (for personalized messages)
python cofounder_agent/cli.py config --set "user_name=Naomi"

# Reminder style: supportive_persistent, direct, or gentle
python cofounder_agent/cli.py config --set "reminder_style=supportive_persistent"

# How often to check in (in hours)
python cofounder_agent/cli.py config --set "check_in_frequency_hours=12"
```

## Pro Tips

### 1. Create a Daily Alias

Add to your `.bashrc` or `.zshrc`:

```bash
alias cofounder="python /workspace/cofounder_agent/cli.py"
alias checkin="python /workspace/cofounder_agent/cli.py checkin"
```

Then just run:
```bash
checkin
```

### 2. Morning Routine

```bash
# Morning check-in
cofounder checkin

# See what's next
cofounder next

# Review a specific goal
cofounder think <goal_id>
```

### 3. Track Everything

Use the agent to track:
- Product milestones
- Fundraising progress
- Partnership outreach
- Grant applications
- User growth goals
- Team hiring goals

### 4. Let It Be Relentless

The agent's job is to not let things slip. If it's reminding you about something, that's by design! Complete it or explicitly cancel it.

## Common Workflows

### Launch a New Feature

```bash
# Set the goal
cofounder goal create \
  "Launch parent dashboard feature" \
  "Design, build, and deploy dashboard for parents to track child progress"

# Add specific tasks
cofounder task create <goal_id> \
  "Design mockups" \
  "Create Figma mockups for parent dashboard"

# Commit to milestones
cofounder commit "Complete dashboard mockups" --due-date 2026-10-10
```

### Apply for a Grant

```bash
# Add the opportunity
cofounder opportunity add \
  "XYZ Education Grant" grant \
  "50k grant for edtech in Africa" "XYZ Foundation" \
  --deadline 2026-11-15 --amount "$50,000"

# Create a goal for it
cofounder goal create \
  "Complete XYZ Grant Application" \
  "Research requirements and submit complete application"

# Track your progress
cofounder goal show <goal_id>
```

### Weekly Planning

```bash
# Review last week
cofounder report

# Check current status
cofounder dashboard

# Plan next week's commitments
cofounder commit "Schedule 5 user interviews" --due-date 2026-10-07
cofounder commit "Finish Q4 roadmap" --due-date 2026-10-08
```

## What's Next?

1. **Use it daily**: The more you use it, the more valuable it becomes
2. **Be specific**: Detailed goals and tasks get better tracking
3. **Stay accountable**: Let the agent do its job - don't ignore reminders!
4. **Iterate**: Adjust reminder styles and frequency to what works for you

Your co-founder is now ready to help you build Sabi! 🚀
