#!/bin/bash
# Script to check GitHub Actions status and help troubleshoot

echo "=== GitHub Actions Status Checker ==="
echo ""
echo "This script helps you check your GitHub Actions status."
echo ""

# Check if gh CLI is installed
if command -v gh &> /dev/null; then
    echo "✓ GitHub CLI (gh) is installed"
    echo ""
    echo "To check your workflow runs:"
    echo "  gh run list"
    echo ""
    echo "To view the latest run:"
    echo "  gh run view"
    echo ""
    echo "To watch a running workflow:"
    echo "  gh run watch"
    echo ""
    echo "To view logs of a specific run:"
    echo "  gh run view [RUN_ID] --log"
    echo ""
else
    echo "GitHub CLI not installed. Install it with:"
    echo "  brew install gh  # macOS"
    echo "  or visit: https://cli.github.com/"
    echo ""
fi

echo "=== Manual Check ==="
echo "1. Go to: https://github.com/YOUR_USERNAME/arthos-app/actions"
echo "2. Click on the latest workflow run"
echo "3. Check each job for errors"
echo "4. Share any error messages with me for troubleshooting"
echo ""

echo "=== Common Issues to Check ==="
echo "✓ Tests failing? Check test output"
echo "✓ Deployment failing? Check Railway token/ID"
echo "✓ Playwright issues? Check browser installation"
echo "✓ Database issues? Check PostgreSQL connection"
echo ""

