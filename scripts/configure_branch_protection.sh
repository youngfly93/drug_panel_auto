#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: scripts/configure_branch_protection.sh [owner/repo] [branch]

Environment:
  CHECK_CONTEXT                         Required status check name. Default: qa-gate
  ENFORCE_ADMINS                        Whether admins must follow protection. Default: false
  REQUIRE_CONVERSATION_RESOLUTION       Require resolved conversations. Default: true
EOF
  exit 0
fi

REPO="${1:-${GITHUB_REPOSITORY:-youngfly93/drug_panel_auto}}"
BRANCH="${2:-main}"
CHECK_CONTEXT="${CHECK_CONTEXT:-qa-gate}"
REQUIRE_CONVERSATION_RESOLUTION="${REQUIRE_CONVERSATION_RESOLUTION:-true}"
ENFORCE_ADMINS="${ENFORCE_ADMINS:-false}"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required. Install it from https://cli.github.com/ and run gh auth login." >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is not authenticated. Run gh auth login with repo admin permissions." >&2
  exit 1
fi

payload="$(mktemp)"
trap 'rm -f "$payload"' EXIT

cat >"$payload" <<JSON
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["${CHECK_CONTEXT}"]
  },
  "enforce_admins": ${ENFORCE_ADMINS},
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": ${REQUIRE_CONVERSATION_RESOLUTION},
  "lock_branch": false,
  "allow_fork_syncing": true
}
JSON

echo "Configuring branch protection for ${REPO}:${BRANCH}"
echo "Required status check: ${CHECK_CONTEXT}"

gh api \
  --method PUT \
  "repos/${REPO}/branches/${BRANCH}/protection" \
  --input "$payload" \
  >/dev/null

echo "Branch protection configured."
echo "Verify with:"
echo "  gh api repos/${REPO}/branches/${BRANCH}/protection --jq '.required_status_checks.contexts'"
