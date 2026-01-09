#!/bin/bash
# Quick GitHub setup script
# Run this after authenticating with: gh auth login

set -e

echo "════════════════════════════════════════════════════════════════"
echo "  L Investigation Framework - GitHub Repository Setup"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Check if gh is authenticated
if ! gh auth status &>/dev/null; then
    echo "❌ Not authenticated with GitHub"
    echo ""
    echo "Please run: gh auth login"
    echo ""
    echo "Follow prompts:"
    echo "  1. Choose 'GitHub.com'"
    echo "  2. Choose 'HTTPS'"
    echo "  3. Choose 'Yes' (git credential helper)"
    echo "  4. Choose 'Login with a web browser'"
    echo "  5. Copy the one-time code"
    echo "  6. Paste in browser and authorize"
    echo ""
    exit 1
fi

echo "✅ GitHub authentication verified"
echo ""

# Check if remote already exists
if git remote get-url origin &>/dev/null; then
    echo "⚠️  Remote 'origin' already exists:"
    git remote get-url origin
    echo ""
    read -p "Push to existing remote? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git push -u origin main
        echo ""
        echo "✅ Pushed to GitHub!"
        gh repo view --web
    fi
    exit 0
fi

# Create new repository
echo "Creating GitHub repository..."
gh repo create l-investigation-framework \
  --public \
  --description "OSINT RAG chatbot for document corpus analysis - Privacy-first, corpus-only LLM investigation framework" \
  --source=. \
  --remote=origin

echo ""
echo "✅ Repository created!"
echo ""

# Push to GitHub
echo "Pushing to GitHub..."
git push -u origin main

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  ✅ SUCCESS! Repository is live on GitHub"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Open in browser
gh repo view --web

