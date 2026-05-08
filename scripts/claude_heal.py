#!/usr/bin/env python3
"""
Claude Auto-Heal Script for Terraform Formatting

Captures terraform fmt errors, sends to Claude for fixing, applies patches.
"""

import os
import subprocess
import json
import sys
from pathlib import Path
import anthropic

def get_terraform_files():
    """Find all .tf files in the repository."""
    tf_files = []
    for root, dirs, files in os.walk('.'):
        # Skip hidden directories and common exclusions
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
        for file in files:
            if file.endswith('.tf'):
                tf_files.append(os.path.join(root, file))
    return sorted(tf_files)

def get_fmt_errors():
    """Run terraform fmt and capture which files need formatting."""
    try:
        result = subprocess.run(
            ['terraform', 'fmt', '--check', '--recursive', '.'],
            capture_output=True,
            text=True
        )
        # fmt returns list of files that need formatting
        files_to_fix = result.stdout.strip().split('\n') if result.stdout.strip() else []
        return [f for f in files_to_fix if f]
    except Exception as e:
        print(f"Error running terraform fmt: {e}", file=sys.stderr)
        return []

def read_file_content(file_path):
    """Read file content safely."""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return None

def send_to_claude(files_content):
    """Send terraform files to Claude for formatting fixes."""
    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    
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
        max_tokens=4000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    return message.content[0].text

def apply_fixes(claude_response):
    """Parse Claude response and apply fixes to files."""
    try:
        # Extract JSON from response
        json_start = claude_response.find('{')
        json_end = claude_response.rfind('}') + 1
        if json_start == -1 or json_end <= json_start:
            print("Error: Could not extract JSON from Claude response", file=sys.stderr)
            return False
        
        json_str = claude_response[json_start:json_end]
        response_data = json.loads(json_str)
        
        files_to_update = response_data.get('files', {})
        
        if not files_to_update:
            print("No files to update in Claude response", file=sys.stderr)
            return False
        
        for file_path, content in files_to_update.items():
            try:
                # Ensure directory exists
                Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w') as f:
                    f.write(content)
                print(f"✓ Fixed: {file_path}")
            except Exception as e:
                print(f"✗ Error writing {file_path}: {e}", file=sys.stderr)
                return False
        
        return True
    
    except json.JSONDecodeError as e:
        print(f"Error parsing Claude JSON response: {e}", file=sys.stderr)
        print(f"Response: {claude_response[:500]}", file=sys.stderr)
        return False

def main():
    """Main execution flow."""
    print("🔍 Detecting Terraform files needing format fixes...")
    
    files_to_fix = get_fmt_errors()
    if not files_to_fix:
        print("✅ No formatting issues detected.")
        return 0
    
    print(f"Found {len(files_to_fix)} file(s) needing fixes:")
    for f in files_to_fix:
        print(f"  - {f}")
    
    # Read content of affected files
    files_content = {}
    for file_path in files_to_fix:
        content = read_file_content(file_path)
        if content:
            files_content[file_path] = content
    
    if not files_content:
        print("✗ Could not read any files for healing.", file=sys.stderr)
        return 1
    
    # Build prompt content
    prompt_files = "\n\n".join([
        f"=== {path} ===\n{content}"
        for path, content in sorted(files_content.items())
    ])
    
    print("📡 Sending files to Claude for auto-healing...")
    
    try:
        claude_response = send_to_claude(prompt_files)
        print("✓ Received response from Claude")
    except Exception as e:
        print(f"✗ Error communicating with Claude: {e}", file=sys.stderr)
        return 1
    
    print("🔧 Applying formatting fixes...")
    
    if apply_fixes(claude_response):
        print("✅ Formatting fixes applied successfully")
        return 0
    else:
        print("✗ Failed to apply formatting fixes", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
