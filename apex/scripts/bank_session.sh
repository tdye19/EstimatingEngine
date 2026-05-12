#!/usr/bin/env bash
# scripts/bank_session.sh
#
# Banks a session log to apex/docs/session-logs/ with timestamp,
# git state, test count, and a template for the human-authored
# summary section.
#
# Usage:
#   ./scripts/bank_session.sh                  # uses today's date
#   ./scripts/bank_session.sh 2026-05-12       # explicit date
#
# Output:
#   apex/docs/session-logs/Session-YYYY-MM-DD.md
#
# Why this exists:
#   End-of-session handoffs are the most valuable artifact and the
#   easiest one to skip. This script makes "bank the session" a
#   single command. Mechanical state (commits, test count, status)
#   is filled in automatically; you write the narrative.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Date: arg 1, or today
DATE="${1:-$(date +%Y-%m-%d)}"

# Validate date format (YYYY-MM-DD)
if [[ ! "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "ERROR: Date must be YYYY-MM-DD format. Got: $DATE" >&2
  exit 1
fi

OUTPUT_DIR="apex/docs/session-logs"
OUTPUT_FILE="$OUTPUT_DIR/Session-$DATE.md"

mkdir -p "$OUTPUT_DIR"

# Refuse to clobber an existing log without explicit confirmation
if [[ -f "$OUTPUT_FILE" ]]; then
  echo "WARNING: $OUTPUT_FILE already exists." >&2
  echo "Overwrite? [y/N] " >&2
  read -r REPLY
  if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
    echo "Aborted. No changes made." >&2
    exit 1
  fi
fi

# Gather mechanical state
BRANCH=$(git branch --show-current 2>/dev/null || echo "<detached>")
RECENT_COMMITS=$(git log --oneline -10 2>/dev/null || echo "<no commits>")
GIT_STATUS=$(git status --short 2>/dev/null || echo "<status unavailable>")
WORKTREE_CLEAN="no"
if [[ -z "$GIT_STATUS" ]]; then
  WORKTREE_CLEAN="yes"
fi

# Test count — try pytest collection without running, fall back gracefully
TEST_COUNT="<run pytest manually to populate>"
if command -v pytest >/dev/null 2>&1; then
  COLLECTED=$(python -m pytest apex/backend/ --collect-only -q 2>/dev/null | tail -1 || echo "")
  if [[ -n "$COLLECTED" ]]; then
    TEST_COUNT="$COLLECTED"
  fi
fi

# Check for running claude processes — surfaces the parallel-session footgun
CLAUDE_PROCS=$(ps aux 2>/dev/null | grep -i claude | grep -v grep | wc -l || echo "0")

# Write the file
cat > "$OUTPUT_FILE" <<EOF
# APEX Session Handoff — $DATE

**Generated:** $(date -u +"%Y-%m-%dT%H:%M:%SZ")
**Branch:** $BRANCH
**Worktree clean:** $WORKTREE_CLEAN
**Claude Code processes running:** $CLAUDE_PROCS

---

## Mechanical state (auto-gathered)

### Recent commits

\`\`\`
$RECENT_COMMITS
\`\`\`

### Git status

\`\`\`
${GIT_STATUS:-<clean>}
\`\`\`

### Test count

\`\`\`
$TEST_COUNT
\`\`\`

---

## Session summary (fill in)

### What shipped today

<!-- One section per sprint or workstream. Reference commit hashes. -->

### What's still open

<!-- Items intentionally not closed today and why. -->

### Backlog items filed today

<!-- New backlog entries with file paths. -->

### Lessons banked

<!-- Workflow patterns to repeat or avoid. Be specific. -->

---

## Recommended next session

<!-- Ordered list. First item should be the cheapest empirical validation
     of whatever shipped today (Railway deploy check, manual run, etc.). -->

EOF

echo "Banked: $OUTPUT_FILE"
echo
echo "Next steps:"
echo "  1. Fill in the session summary sections."
echo "  2. git add $OUTPUT_FILE && git commit -m 'docs: session log $DATE'"
echo "  3. Upload to project knowledge if relevant."

if [[ "$CLAUDE_PROCS" -gt 1 ]]; then
  echo
  echo "WARNING: $CLAUDE_PROCS Claude Code processes detected."
  echo "Parallel sessions on \`main\` are a footgun. Close all but one."
fi
