#!/bin/bash
# PettyCash NYSA — Deploy Script
# Usage:
#   ./deploy.sh           Deploy current version
#   ./deploy.sh patch     Bump patch (1.1.0 → 1.1.1), commit, deploy
#   ./deploy.sh minor     Bump minor (1.1.0 → 1.2.0), commit, deploy
#   ./deploy.sh major     Bump major (1.1.0 → 2.0.0), commit, deploy
set -e

# Config
VPS_USER=root
VPS_IP=138.199.150.124
SSH_KEY="/Volumes/Box/ssh/hetzner_rsa"
REMOTE_DIR=/opt/pettycash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR"

# ── Read current version ──
VERSION=$(python3 -c "exec(open('version.py').read()); print(__version__)")
echo "Current version: $VERSION"

# ── Version bump (if requested) ──
BUMP="$1"
if [ -n "$BUMP" ]; then
    IFS='.' read -r MAJOR MINOR PATCH <<< "$VERSION"
    case "$BUMP" in
        major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
        minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
        patch) PATCH=$((PATCH + 1)) ;;
        *) echo "Usage: $0 [major|minor|patch]"; exit 1 ;;
    esac
    VERSION="$MAJOR.$MINOR.$PATCH"
    echo "__version__ = \"$VERSION\"" > version.py
    echo "Bumped to: $VERSION"
fi

# ── Git commit + tag + push ──
echo ""
echo "=== Git push ==="
git add -A
if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "Release v$VERSION

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
    echo "Committed v$VERSION"
else
    echo "No changes to commit"
fi

# Tag (move tag if it already exists)
git tag -f "v$VERSION" -m "Release v$VERSION"
git push origin master --tags --force
echo "Pushed to GitHub"

# ── Deploy to VPS ──
echo ""
echo "=== Deploying to VPS ==="
SSH_CMD="ssh -i $SSH_KEY -o StrictHostKeyChecking=no $VPS_USER@$VPS_IP"

# Rsync app files (exclude git, local data, cache)
rsync -avz --delete \
    -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude 'instance/' \
    --exclude 'attached_assets/' \
    --exclude '.env' \
    --exclude '*.db' \
    "$SCRIPT_DIR/" "$VPS_USER@$VPS_IP:$REMOTE_DIR/"

echo "Files synced"

# Rebuild and restart container
$SSH_CMD "cd $REMOTE_DIR && docker compose down && docker compose build --no-cache && docker compose up -d"
echo "Container rebuilt"

# Wait for container to be healthy
sleep 3
$SSH_CMD "docker logs pettycash-pettycash-1 --tail 5"

echo ""
echo "=== Deployed PettyCash v$VERSION ==="
echo "https://pettycash.nysatex.com"
