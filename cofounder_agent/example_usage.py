#!/usr/bin/env python3
"""
Example usage of the Co-Founder Agent
This demonstrates how to programmatically interact with the agent.

Run: python3 cofounder_agent/example_usage.py
"""

from cofounder_agent import CofounderAgent
from datetime import datetime, timedelta

def main():
    print("=" * 60)
    print("  Co-Founder Agent Example Usage")
    print("=" * 60 + "\n")
    
    # Initialize the agent
    agent = CofounderAgent()
    print("✅ Agent initialized\n")
    
    # Set a high-level goal
    print("Setting a strategic goal...")
    result = agent.set_high_level_goal(
        title="Launch Sabi in 3 new Nigerian states",
        description="Expand Sabi's reach by launching in Lagos, Kano, and Rivers states, "
                    "including local partnerships, teacher training, and marketing",
        priority="high",
        target_date=(datetime.now() + timedelta(days=90)).isoformat(),
        success_criteria=[
            "Signed partnerships with 10 schools per state",
            "Trained 30 teachers on Sabi usage",
            "1000+ active student users across all 3 states",
            "Local language support for Yoruba, Hausa, and Igbo"
        ]
    )
    print(f"✅ {result['message']}\n")
    goal_id = result['goal_id']
    
    # Add an opportunity
    print("Adding an opportunity...")
    opp_id = agent.add_opportunity_manual(
        title="Tony Elumelu Foundation Entrepreneurship Programme",
        opp_type="funding",
        description="$5000 seed funding + training + mentorship for African entrepreneurs",
        source="Tony Elumelu Foundation",
        url="https://www.tonyelumelufoundation.org/",
        deadline=(datetime.now() + timedelta(days=45)).isoformat(),
        amount="$5,000"
    )
    print(f"✅ Opportunity added: {opp_id}\n")
    
    # Create a commitment
    print("Creating a commitment...")
    commitment_id = agent.create_commitment(
        description="Complete TEF application form",
        due_date=(datetime.now() + timedelta(days=7)).isoformat()
    )
    print(f"✅ Commitment created: {commitment_id}\n")
    
    # Perform a check-in
    print("Performing check-in...")
    checkin = agent.check_in()
    print("\n" + "=" * 60)
    print(checkin["message"])
    print("=" * 60 + "\n")
    
    # Get strategic thoughts on the goal
    print("Getting strategic insights on the goal...")
    thoughts = agent.think_about_goal(goal_id)
    print(f"\n💭 Thinking about: {thoughts['goal']['title']}\n")
    
    if thoughts.get("insights"):
        print("Insights:")
        for insight in thoughts["insights"]:
            print(f"  • {insight}")
        print()
    
    if thoughts.get("suggested_actions"):
        print("Suggested Actions:")
        for action in thoughts["suggested_actions"]:
            print(f"  • {action}")
        print()
    
    # View dashboard
    print("\nDashboard Summary:")
    dashboard = agent.get_dashboard()
    
    goals_data = dashboard["goals"]
    print(f"  📊 Goals: {goals_data['active_goals']} active, "
          f"{goals_data['completed_goals']} completed")
    
    opp_data = dashboard["opportunities"]
    print(f"  💡 Opportunities: {opp_data['active_opportunities']} active, "
          f"{opp_data['high_fit_count']} high-fit")
    
    acc_data = dashboard["accountability"]
    print(f"  ✅ Accountability Score: {acc_data['score']:.1%}")
    print(f"     Active commitments: {acc_data['active_commitments']}")
    
    print("\n" + "=" * 60)
    print("  Example complete!")
    print("  Run: python cofounder_agent/cli.py dashboard")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
