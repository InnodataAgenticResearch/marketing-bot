#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${MARKETING_BOT_REPO_DIR:-$HOME/marketing-bot}"
DATE_STR="${1:-$(TZ=America/New_York date +%Y-%m-%d)}"

cd "$REPO_DIR"
git pull --ff-only origin main || true

PYTHONPATH=src python3 -m marketing_bot.cli generate-daily --date "$DATE_STR" --live

git config user.name "Marketing-Bot"
git config user.email "drosen@innodata.com"
git add "roundups/$DATE_STR.md" \
        "BrandAndPositioning/$DATE_STR/positioning.md" \
        "CompetitiveIntelligence/$DATE_STR/competitors.md" \
        "MarketTrends/$DATE_STR/trends.md" \
        "README.md"

if ! git diff --cached --quiet; then
    git commit -m "chore(roundup): daily 8am PR & market intelligence roundup for $DATE_STR"
    git push origin main
fi
