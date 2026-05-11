#!/usr/bin/env bash
# Append a markdown report to GITHUB_STEP_SUMMARY (Actions run overview page).

set -euo pipefail

[[ -n "${GITHUB_STEP_SUMMARY:-}" ]] || {
  echo "GITHUB_STEP_SUMMARY not set; skipping."
  exit 0
}

md_escape() {
  sed 's/`/\`/g' | head -c "${1:-24000}"
}

{
  echo "## Terraform auto-heal — run summary"
  echo
  echo "| Field | Value |"
  echo "| --- | --- |"
  echo "| Event | \`${GITHUB_EVENT_NAME:-unknown}\` |"
  echo "| Ref | \`${GITHUB_REF_NAME:-unknown}\` |"
  echo "| Workflow | [\`${GITHUB_WORKFLOW:-}\`](${GITHUB_SERVER_URL:-}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}) |"
  echo

  echo "### Initial \`terraform fmt --check\` (exit stored in step output)"
  if [[ -f /tmp/fmt_output.txt ]]; then
    echo "<details><summary>Click to expand output</summary>"
    echo
    echo '```text'
    md_escape 12000 </tmp/fmt_output.txt || true
    echo
    echo '```'
    echo "</details>"
  else
    echo "_No /tmp/fmt_output.txt (step may have been skipped)._"
  fi
  echo

  echo "### Fmt context (\`fmt_error_parser\`)"
  if [[ -f /tmp/fmt_context.json ]]; then
    echo "- **Files in context:** \`$(jq -r '(.files // {}) | keys | join(", ")' /tmp/fmt_context.json 2>/dev/null || echo "(parse error)")\`"
    echo "<details><summary>Context JSON (truncated)</summary>"
    echo
    echo '```json'
    head -c 8000 /tmp/fmt_context.json || true
    echo
    echo '```'
    echo "</details>"
  else
    echo "_No /tmp/fmt_context.json._"
  fi
  echo

  echo "### Claude heal"
  if [[ -f /tmp/claude_heal_report.json ]]; then
    echo "<details><summary>Report JSON</summary>"
    echo
    echo '```json'
    cat /tmp/claude_heal_report.json
    echo
    echo '```'
    echo "</details>"
  else
    echo "_No /tmp/claude_heal_report.json (Claude step skipped or did not write a report)._"
  fi
  echo

  echo "### Final \`terraform fmt --check\`"
  if [[ -f /tmp/fmt_final.txt ]]; then
    echo "<details><summary>Click to expand</summary>"
    echo
    echo '```text'
    md_escape 8000 </tmp/fmt_final.txt || true
    echo
    echo '```'
    echo "</details>"
  else
    echo "_No /tmp/fmt_final.txt._"
  fi
  echo

  echo "### Pull request (for engineer review)"
  if [[ -f /tmp/pr_url.txt ]]; then
    url="$(tr -d '[:space:]' </tmp/pr_url.txt)"
    if [[ -n "$url" ]]; then
      echo "Claude’s fixes were pushed to a dedicated branch and a **PR was opened**:"
      echo "- **${url}**"
      echo
      echo "Use the PR **Files changed** tab to see the full diff. The PR body includes the workflow link and Claude report JSON."
    else
      echo "_PR URL file was empty._"
    fi
  else
    echo "No PR was created in this run. Typical reasons:"
    echo "- Event is \`pull_request\` (PR-from-branch flow is only enabled for \`push\` to avoid merge-commit edge cases)."
    echo "- Fork PRs cannot receive bot pushes; merge fixes on the fork manually."
    echo "- Auto-heal did not reach the publish step (fmt still failing or no \`.tf\` changes)."
    echo "- Publishing is skipped on branches named \`terraform-fmt-auto-heal/*\`."
  fi
  echo

  echo "### Step outcomes (debug)"
  echo "- fmt initial exit (from step output): \`$(cat /tmp/meta_fmt_initial.txt 2>/dev/null || echo n/a)\`"
  echo "- fmt final exit (from step output): \`$(cat /tmp/meta_fmt_final.txt 2>/dev/null || echo n/a)\`"
  echo "- Claude step outcome: \`$(cat /tmp/meta_claude_outcome.txt 2>/dev/null || echo n/a)\`"
  echo "- Open PR step outcome: \`$(cat /tmp/meta_open_pr_outcome.txt 2>/dev/null || echo n/a)\`"
} >>"$GITHUB_STEP_SUMMARY"
