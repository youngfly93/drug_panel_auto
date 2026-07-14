#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-youngfly93/drug_panel_auto}"
BASE_BRANCH="${BASE_BRANCH:-main}"
CHECK_CONTEXT="${CHECK_CONTEXT:-qa-gate}"
WORKFLOW_NAME="${WORKFLOW_NAME:-Reportgen QA Gate}"
OUTPUT_ROOT="${OUTPUT_ROOT:-tmp/release_check/$(date +%Y%m%d_%H%M%S)}"
RUN_QA_GATE="${RUN_QA_GATE:-1}"
RUN_GITHUB_CHECKS="${RUN_GITHUB_CHECKS:-1}"
RUN_HISTORICAL_GOLDEN="${RUN_HISTORICAL_GOLDEN:-1}"
REQUIRE_HISTORICAL_GOLDEN="${REQUIRE_HISTORICAL_GOLDEN:-0}"
HISTORICAL_GOLDEN_MANIFEST="${HISTORICAL_GOLDEN_MANIFEST:-}"
ALLOW_DIRTY="${ALLOW_DIRTY:-0}"
QA_GATE_ARGS="${QA_GATE_ARGS:-}"

current_branch="$(git branch --show-current)"
current_sha="$(git rev-parse HEAD)"

echo "Release readiness check"
echo "  repo: ${REPO}"
echo "  branch: ${current_branch}"
echo "  commit: $(git rev-parse --short HEAD)"

if [ "$ALLOW_DIRTY" != "1" ]; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Working tree has uncommitted changes. Commit or stash before release." >&2
    exit 1
  fi
fi

mkdir -p "$OUTPUT_ROOT"
if [ "$RUN_HISTORICAL_GOLDEN" = "1" ]; then
  echo ""
  echo "[1/3] Checking historical golden contracts"
  if [ -n "$HISTORICAL_GOLDEN_MANIFEST" ] && [ -f "$HISTORICAL_GOLDEN_MANIFEST" ]; then
    python scripts/check_historical_golden_release.py \
      --manifest "$HISTORICAL_GOLDEN_MANIFEST" \
      --output-root "$OUTPUT_ROOT/historical_golden" \
      --output-json "$OUTPUT_ROOT/historical_golden.json"
  elif [ "$REQUIRE_HISTORICAL_GOLDEN" = "1" ]; then
    echo "Historical golden manifest is required but missing: ${HISTORICAL_GOLDEN_MANIFEST:-<unset>}" >&2
    exit 1
  else
    python scripts/check_historical_golden_release.py \
      --contracts-only \
      --output-json "$OUTPUT_ROOT/historical_golden_contracts.json"
  fi
else
  echo ""
  echo "[1/3] Skipping historical golden contracts"
fi

if [ "$RUN_QA_GATE" = "1" ]; then
  echo ""
  echo "[2/3] Running local QA gate"
  # shellcheck disable=SC2086
  python -m reportgen.cli qa gate --output-root "$OUTPUT_ROOT/qa_gate" $QA_GATE_ARGS
else
  echo ""
  echo "[2/3] Skipping local QA gate"
fi

if [ "$RUN_GITHUB_CHECKS" = "1" ]; then
  echo ""
  echo "[3/3] Checking GitHub branch protection and latest Actions run"
  if ! command -v gh >/dev/null 2>&1; then
    echo "gh CLI is required for GitHub checks. Set RUN_GITHUB_CHECKS=0 to skip." >&2
    exit 1
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo "gh is not authenticated. Set RUN_GITHUB_CHECKS=0 to skip." >&2
    exit 1
  fi

  contexts="$(
    gh api "repos/${REPO}/branches/${BASE_BRANCH}/protection" \
      --jq '.required_status_checks.contexts[]?' 2>/dev/null || true
  )"
  if ! printf '%s\n' "$contexts" | grep -Fxq "$CHECK_CONTEXT"; then
    echo "Branch ${BASE_BRANCH} does not require status check ${CHECK_CONTEXT}." >&2
    exit 1
  fi

  latest_conclusion="$(
    gh run list \
      --repo "$REPO" \
      --workflow "$WORKFLOW_NAME" \
      --branch "$current_branch" \
      --limit 1 \
      --json conclusion \
      --jq '.[0].conclusion // ""'
  )"
  latest_status="$(
    gh run list \
      --repo "$REPO" \
      --workflow "$WORKFLOW_NAME" \
      --branch "$current_branch" \
      --limit 1 \
      --json status \
      --jq '.[0].status // ""'
  )"
  latest_sha="$(
    gh run list \
      --repo "$REPO" \
      --workflow "$WORKFLOW_NAME" \
      --branch "$current_branch" \
      --limit 1 \
      --json headSha \
      --jq '.[0].headSha // ""'
  )"

  if [ "$latest_status" != "completed" ] || [ "$latest_conclusion" != "success" ]; then
    echo "Latest ${WORKFLOW_NAME} run is not successful: ${latest_status}/${latest_conclusion}" >&2
    exit 1
  fi
  if [ "$latest_sha" != "$current_sha" ]; then
    echo "Latest ${WORKFLOW_NAME} run is for a different commit: ${latest_sha}" >&2
    exit 1
  fi
else
  echo ""
  echo "[3/3] Skipping GitHub checks"
fi

echo ""
echo "Release readiness check passed."
