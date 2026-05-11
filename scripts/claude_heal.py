#!/usr/bin/env python3
"""
Claude Auto-Heal Script for Terraform Formatting

Uses fmt context JSON when provided; otherwise discovers files via terraform fmt.
Writes /tmp/claude_heal_report.json for CI summaries and PR bodies.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import anthropic


def get_fmt_errors() -> list[str]:
    """Run terraform fmt --check and capture file paths that need formatting."""
    try:
        result = subprocess.run(
            ["terraform", "fmt", "--check", "--recursive", "."],
            capture_output=True,
            text=True,
        )
        files_to_fix = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return [f for f in files_to_fix if f]
    except Exception as e:
        print(f"Error running terraform fmt: {e}", file=sys.stderr)
        return []


def read_file_content(file_path: str) -> str | None:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return None


def load_context_file(path: str) -> tuple[list[str], dict[str, str], list[str]]:
    """Returns (file_paths, path->content, fmt_error_snippets)."""
    with open(path, "r", encoding="utf-8") as f:
        ctx = json.load(f)
    files = ctx.get("files") or {}
    errs = ctx.get("errors") or []
    paths = sorted(files.keys())
    return paths, files, errs if isinstance(errs, list) else [str(errs)]


def send_to_claude(files_content: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    prompt = f"""You are a Terraform formatting expert. I have Terraform files that need formatting fixes.

IMPORTANT: Only fix formatting issues (indentation, spacing, line breaks). Do NOT modify logic, variables, or resource configuration.

Here are the files that need formatting:

{files_content}

For each file, provide the corrected version with proper HCL formatting:
- Consistent 2-space indentation
- Proper spacing around blocks
- Proper line breaks
- Terraform fmt compliant

Return ONLY the corrected file contents in this JSON format:
{{
  "files": {{
    "path/to/file.tf": "full corrected content here",
    "path/to/other.tf": "full corrected content here"
  }}
}}"""

    model_name = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    message = client.messages.create(
        model=model_name,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def apply_fixes(claude_response: str) -> tuple[bool, list[str]]:
    touched: list[str] = []
    try:
        json_start = claude_response.find("{")
        json_end = claude_response.rfind("}") + 1
        if json_start == -1 or json_end <= json_start:
            print("Error: Could not extract JSON from Claude response", file=sys.stderr)
            return False, touched

        json_str = claude_response[json_start:json_end]
        response_data = json.loads(json_str)
        files_to_update = response_data.get("files", {})

        if not files_to_update:
            print("No files to update in Claude response", file=sys.stderr)
            return False, touched

        for file_path, content in files_to_update.items():
            try:
                Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                touched.append(file_path)
                print(f"✓ Wrote healed content: {file_path}")
            except Exception as e:
                print(f"✗ Error writing {file_path}: {e}", file=sys.stderr)
                return False, touched

        return True, touched

    except json.JSONDecodeError as e:
        print(f"Error parsing Claude JSON response: {e}", file=sys.stderr)
        print(f"Response: {claude_response[:500]}", file=sys.stderr)
        return False, touched


def _snippet(text: str, max_len: int = 500) -> str:
    t = text.strip().replace("\r\n", "\n")
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def build_human_summary(
    *,
    status: str,
    model: str,
    files_modified: list[str],
    files_considered: list[str],
    used_context_file: bool,
    fmt_errors_excerpt: list[str],
    notes: str | None,
) -> str:
    """Short markdown for PR bodies and GitHub Actions job summaries."""
    lines: list[str] = []
    lines.append("### What Claude did (plain language)")
    lines.append("")

    if status == "success":
        lines.append(
            "Terraform reported that at least one `.tf` file was not `terraform fmt`-clean. "
            "Claude was asked to return **only** formatting fixes (indentation, spacing, line breaks). "
            "Those versions were written back to the paths below."
        )
        lines.append("")
        lines.append(f"- **Model:** `{model}`")
        lines.append(f"- **Files updated on disk:** {len(files_modified)}")
        for p in sorted(files_modified):
            lines.append(f"  - `{p}`")
        if used_context_file:
            lines.append("- **How files were chosen:** from the fmt context snapshot (same scope as `fmt_error_parser`).")
        else:
            lines.append("- **How files were chosen:** from `terraform fmt --check` stdout (file list).")
        if fmt_errors_excerpt:
            ex0 = _snippet(fmt_errors_excerpt[0], 500)
            one_line = " ".join(ex0.split())
            lines.append(
                f"- **What `terraform fmt` reported (short excerpt):** {one_line}"
                + ("…" if len(one_line) >= 500 else "")
            )

    elif status == "no_changes_needed":
        lines.append("No formatting drift was found after `terraform fmt --check`, so Claude was not called.")
        lines.append("")
        lines.append(f"- **Model (would be used):** `{model}`")

    elif status == "error":
        lines.append("The heal step could not run because no file contents were available to send to Claude.")
        lines.append("")
        if files_considered:
            lines.append(f"- **Paths in context:** {', '.join(f'`{p}`' for p in sorted(files_considered))}")
        if notes:
            lines.append(f"- **Detail:** {notes}")

    elif status == "api_error":
        lines.append("Claude’s API did not return a usable answer (auth, rate limit, network, or model error).")
        lines.append("")
        lines.append(f"- **Model:** `{model}`")
        lines.append(f"- **Files we intended to send:** {len(files_considered)}")
        for p in sorted(files_considered)[:20]:
            lines.append(f"  - `{p}`")
        if len(files_considered) > 20:
            lines.append("  - _(more omitted)_")
        if notes:
            lines.append(f"- **Error (from client):** {_snippet(notes, 600)}")

    elif status == "apply_failed":
        lines.append(
            "Claude responded, but the workflow could not apply the fix. "
            "Usually the reply was not valid JSON, did not include a `files` map, or a file could not be written."
        )
        lines.append("")
        lines.append(f"- **Model:** `{model}`")
        if files_modified:
            lines.append(f"- **Partially written before failure:** {', '.join(f'`{p}`' for p in sorted(files_modified))}")
        if notes:
            lines.append(f"- **Detail:** {_snippet(notes, 500)}")

    else:
        lines.append(f"Status: `{status}`. See JSON report for fields.")
        if notes:
            lines.append(f"- **Note:** {_snippet(notes, 500)}")

    return "\n".join(lines)


def write_report(
    path: str,
    *,
    status: str,
    model: str,
    files_modified: list[str],
    files_considered: list[str],
    used_context_file: bool,
    fmt_errors_excerpt: list[str],
    notes: str | None = None,
) -> None:
    human = build_human_summary(
        status=status,
        model=model,
        files_modified=files_modified,
        files_considered=files_considered,
        used_context_file=used_context_file,
        fmt_errors_excerpt=fmt_errors_excerpt,
        notes=notes,
    )
    report = {
        "status": status,
        "model": model,
        "files_modified": files_modified,
        "files_considered": files_considered,
        "used_context_file": used_context_file,
        "fmt_errors_excerpt": fmt_errors_excerpt[:3],
        "notes": notes,
        "human_summary": human,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote heal report to {path}")
    summary_md = path.replace(".json", "") + "_summary.md"
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write(human)
    print(f"Wrote human summary to {summary_md}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude Terraform fmt auto-heal")
    parser.add_argument("--context-file", help="JSON from fmt_error_parser.py")
    parser.add_argument("--output-dir", default=".", help="Unused; reserved for future chdir")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--report", default="/tmp/claude_heal_report.json")
    args = parser.parse_args()

    _ = args.output_dir  # reserved
    report_path = args.report
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    used_context = bool(args.context_file and Path(args.context_file).exists())
    fmt_excerpt: list[str] = []

    files_content: dict[str, str] = {}

    if used_context:
        paths, from_ctx, fmt_excerpt = load_context_file(args.context_file)
        print(f"Using context file with {len(paths)} file(s).")
        for p in paths:
            c = from_ctx.get(p)
            if c:
                files_content[p] = c
    else:
        print("🔍 Detecting Terraform files needing format fixes (terraform fmt --check)...")
        files_to_fix = get_fmt_errors()
        if not files_to_fix:
            write_report(
                report_path,
                status="no_changes_needed",
                model=model,
                files_modified=[],
                files_considered=[],
                used_context_file=False,
                fmt_errors_excerpt=[],
                notes="terraform fmt --check reported no files to fix.",
            )
            print("✅ No formatting issues detected.")
            return 0
        for file_path in files_to_fix:
            content = read_file_content(file_path)
            if content is not None:
                files_content[file_path] = content

    if not files_content:
        write_report(
            report_path,
            status="error",
            model=model,
            files_modified=[],
            files_considered=[],
            used_context_file=used_context,
            fmt_errors_excerpt=fmt_excerpt,
            notes="No file contents available to send to Claude.",
        )
        print("✗ Could not read any files for healing.", file=sys.stderr)
        return 1

    prompt_files = "\n\n".join(
        f"=== {path} ===\n{content}" for path, content in sorted(files_content.items())
    )

    print("📡 Sending files to Claude for auto-healing...")
    last_err: str | None = None
    claude_response = ""
    for attempt in range(1, args.max_retries + 1):
        try:
            claude_response = send_to_claude(prompt_files)
            print(f"✓ Received response from Claude (attempt {attempt})")
            break
        except Exception as e:
            last_err = str(e)
            print(f"✗ Claude API error (attempt {attempt}): {e}", file=sys.stderr)
            if attempt == args.max_retries:
                write_report(
                    report_path,
                    status="api_error",
                    model=model,
                    files_modified=[],
                    files_considered=sorted(files_content.keys()),
                    used_context_file=used_context,
                    fmt_errors_excerpt=fmt_excerpt,
                    notes=last_err,
                )
                return 1

    print("🔧 Applying formatting fixes from Claude response...")
    ok, touched = apply_fixes(claude_response)
    if ok:
        write_report(
            report_path,
            status="success",
            model=model,
            files_modified=touched,
            files_considered=sorted(files_content.keys()),
            used_context_file=used_context,
            fmt_errors_excerpt=fmt_excerpt,
            notes="Claude returned JSON with file bodies; writes applied to working tree.",
        )
        print("✅ Formatting fixes applied successfully")
        return 0

    write_report(
        report_path,
        status="apply_failed",
        model=model,
        files_modified=touched,
        files_considered=sorted(files_content.keys()),
        used_context_file=used_context,
        fmt_errors_excerpt=fmt_excerpt,
        notes="Could not parse JSON from Claude or writes failed.",
    )
    print("✗ Failed to apply formatting fixes", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
