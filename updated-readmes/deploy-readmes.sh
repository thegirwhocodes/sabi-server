#!/bin/bash
# Deploy updated READMEs to all GitHub repositories
# This script will copy each updated README to its corresponding repository,
# commit the changes, and push to GitHub.

set -e  # Exit on error

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
READMES_DIR="$SCRIPT_DIR"
WORK_DIR="/tmp/readme-deployment"

# Color output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}GitHub README Deployment Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Create work directory
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# Array of repos to update (repo_name:readme_file)
declare -a REPOS=(
    "thegirwhocodes:thegirwhocodes-README.md"
    "portfolio:portfolio-README.md"
    "Dactyl-Final:Dactyl-Final-README.md"
    "email:email-README.md"
    "kai:kai-README.md"
    "Go:Go-README.md"
    "edit:edit-README.md"
    "Rings:Rings-README.md"
    "spheres-app:spheres-app-README.md"
    "adjutant:adjutant-README.md"
    "script-clearance-copilot:script-clearance-copilot-README.md"
    "Education-for-Equality:Education-for-Equality-README.md"
    "ai-context:ai-context-README.md"
    "Index:Index-README.md"
)

# Process each repo
for repo_info in "${REPOS[@]}"; do
    IFS=':' read -r REPO_NAME README_FILE <<< "$repo_info"
    
    echo -e "\n${BLUE}Processing: ${REPO_NAME}${NC}"
    echo "-------------------------------------------"
    
    # Clone repo if not already cloned
    if [ ! -d "$REPO_NAME" ]; then
        echo "Cloning repository..."
        git clone "https://github.com/thegirwhocodes/${REPO_NAME}.git"
    fi
    
    cd "$REPO_NAME"
    
    # Pull latest changes
    echo "Pulling latest changes..."
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || echo "Using current branch"
    
    # Copy updated README
    echo "Copying updated README..."
    cp "$READMES_DIR/$README_FILE" README.md
    
    # Check if there are changes
    if git diff --quiet README.md; then
        echo -e "${YELLOW}No changes detected, skipping...${NC}"
    else
        echo "Committing changes..."
        git add README.md
        git commit -m "Update README with professional formatting and status badges

- Add status indicators (🚀 Launched / 🏆 Complete / 🔨 In Progress / 📦 Archived)
- Improve formatting and structure for professional presentation
- Add comprehensive tech stack information
- Include demo links and project context
- Optimize for startup job applications"
        
        echo "Pushing to GitHub..."
        git push
        
        echo -e "${GREEN}✓ Successfully updated ${REPO_NAME}${NC}"
    fi
    
    cd "$WORK_DIR"
done

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}All READMEs updated successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}IMPORTANT NEXT STEP:${NC}"
echo -e "Make sabi-server repository PRIVATE via GitHub web interface:"
echo -e "  1. Go to: https://github.com/thegirwhocodes/sabi-server/settings"
echo -e "  2. Scroll to 'Danger Zone'"
echo -e "  3. Click 'Change visibility' → 'Make private'"
echo ""
