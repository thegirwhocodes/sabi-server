# Quick Demo - See Your Co-Founder Agent in Action!

## 🚀 5-Minute Demo

### Step 1: Run the Example (1 minute)

```bash
cd /workspace
python3 cofounder_agent/example_usage.py
```

You'll see:
- ✅ Agent initialization
- ✅ Goal creation with task breakdown
- ✅ Opportunity added with fit scoring
- ✅ Commitment created
- ✅ Strategic insights

### Step 2: View CLI Dashboard (1 minute)

```bash
python3 cofounder_agent/cli.py dashboard
```

You'll see your:
- 📊 Active goals with progress bars
- 💡 Opportunities tracked
- ✅ Accountability score
- 🎯 Next priority actions

### Step 3: Try a Check-in (1 minute)

```bash
python3 cofounder_agent/cli.py checkin
```

This is what you'd run every morning - it shows you what needs attention today!

### Step 4: See the Web Dashboard (2 minutes)

```bash
# Start the web server
cd /workspace/cofounder_agent
python3 api.py
```

Then open: **http://localhost:8001**

You'll see a beautiful web interface with:
- 📈 Visual progress tracking
- 🎨 Modern, gradient design
- 📱 Responsive mobile-friendly layout
- 🔄 Auto-refresh every 30 seconds

## What You Just Saw

### The Agent Can:
1. **Break Down Big Goals** - Take "Launch in 3 states" → 5 specific tasks
2. **Track Opportunities** - Monitor grants, accelerators, partnerships
3. **Calculate Fit Scores** - How well does this opportunity match Sabi?
4. **Hold You Accountable** - Create commitments with deadline tracking
5. **Provide Insights** - Strategic thoughts on each goal
6. **Show Next Actions** - Prioritized list of what to do

### Two Interfaces:
1. **CLI** - For daily management (fast, powerful)
2. **Web Dashboard** - For visual overview (beautiful, shareable)

## Try These Commands

```bash
# Add your own goal
python3 cofounder_agent/cli.py goal create \
  "Secure seed funding for Sabi" \
  "Raise $500k seed round to scale operations" \
  --priority critical

# See your new goal
python3 cofounder_agent/cli.py goal list

# Add an opportunity
python3 cofounder_agent/cli.py opportunity add \
  "Y Combinator W27" accelerator \
  "3-month program with $500k investment" "YC" \
  --deadline 2026-12-31

# Make a commitment
python3 cofounder_agent/cli.py commit \
  "Submit YC application" \
  --due-date 2026-10-15

# Get next actions
python3 cofounder_agent/cli.py next

# See weekly report
python3 cofounder_agent/cli.py report
```

## Deploy to Vercel

Want to access your dashboard from anywhere?

```bash
cd /workspace
vercel --prod
```

Or see the full deployment guide: `cofounder_agent/WEB_DEPLOY.md`

## Real-World Usage

### Morning Routine:
```bash
# Start your day
python3 cofounder_agent/cli.py checkin

# See what's urgent
python3 cofounder_agent/cli.py next
```

### Adding a New Goal:
```bash
python3 cofounder_agent/cli.py goal create \
  "Launch parent dashboard feature" \
  "Build and ship v2.0 with parent portal" \
  --priority high
```

### Tracking a Grant:
```bash
python3 cofounder_agent/cli.py opportunity add \
  "Google.org Impact Grant" grant \
  "$100k for AI education projects" "Google" \
  --deadline 2026-11-30 --amount "$100,000"
```

### Weekly Review:
```bash
# Friday afternoon
python3 cofounder_agent/cli.py report
```

## The Agent in Action

Here's what it looks like in real use:

**Dashboard:**
```
============================================================
  SABI CO-FOUNDER AGENT DASHBOARD
============================================================

📊 GOALS: 3/5 active
   Tasks: 12 pending, 1 blocked

   • Launch Sabi in 3 new states
     [████████░░░░░░░░░░░░] 40.0% (2/5 tasks)

   • Secure $500k seed funding
     [██░░░░░░░░░░░░░░░░░░] 10.0% (1/10 tasks)

💡 OPPORTUNITIES: 5 active, 2 high-fit
   Upcoming deadlines: 3

✅ ACCOUNTABILITY 🟢
   Score: 85.0%
   Active commitments: 4
   Overdue: 0

🎯 NEXT ACTIONS:
   You have 12 task(s) that need attention.

   1. [HIGH] Complete partnership proposal for Lagos
   2. [HIGH] Submit Google.org grant application
   3. [MEDIUM] Schedule user interviews
============================================================
```

## What Makes This Special

1. **Truly Operational** - Not just a todo list, but a co-founder that thinks strategically
2. **Relentless Accountability** - Doesn't let things slip through the cracks
3. **Opportunity Tracking** - Keeps eyes on grants, accelerators, partnerships
4. **Strategic Insights** - Helps you think through complex goals
5. **Persistent Memory** - Remembers everything across sessions
6. **Two Interfaces** - CLI for power, Web for beauty

## Next Steps

1. ✅ You've seen the demo
2. 📝 Set your first real goal
3. 💼 Add opportunities you're tracking
4. ✅ Make commitments and let it hold you accountable
5. 🌐 Deploy to Vercel for access anywhere
6. 📅 Make `checkin` part of your daily routine

Ready to build Sabi with your AI co-founder? Let's go! 🚀
