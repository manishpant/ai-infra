#!/usr/bin/env python3
"""
Parse terraform fmt errors and capture affected file contents.
"""

import json
import subprocess
import sys
from pathlib import Path
import argparse

def run_terraform_fmt_check(terraform_dir: str) -> tuple[str, int]:
    """Run terraform fmt --check and capture output."""
    result = subprocess.run(
        ['terraform', 'fmt', '--check', '--recursive', terraform_dir],
        capture_output=True,
        text=True
    )
    return result.stderr + result.stdout, result.returncode

def find_affected_files(terraform_dir: str) -> list[str]:
    """Find all .tf files in terraform directory."""
    tf_files = []
    for filepath in Path(terraform_dir).rglob('*.tf'):
        tf_files.append(str(filepath))
    return sorted(tf_files)

def get_file_content(filepath: str) -> str:
    """Read file content safely."""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except Exception as e:
        print(f"Warning: Could not read {filepath}: {e}", file=sys.stderr)
        return ""

def main():
    parser = argparse.ArgumentParser(description='Parse Terraform fmt errors')
    parser.add_argument('--terraform-dir', required=True, help='Root Terraform directory')
    parser.add_argument('--output', required=True, help='Output JSON file')
    
    args = parser.parse_args()
    
    print("Running terraform fmt check...")
    fmt_output, returncode = run_terraform_fmt_check(args.terraform_dir)
    
    if returncode == 0:
        print("No fmt errors found.")
        context = {'errors': [], 'files': {}}
    else:
        print(f"Fmt errors detected:\n{fmt_output}")
        
        # Get all .tf files (fmt doesn't always report which files are wrong)
        affected_files_list = find_affected_files(args.terraform_dir)
        
        files_dict = {}
        for filepath in affected_files_list:
            content = get_file_content(filepath)
            if content:
                files_dict[filepath] = content
        
        context = {
            'errors': [fmt_output],
            'files': files_dict
        }
    
    # Write context to output file
    with open(args.output, 'w') as f:
        json.dump(context, f, indent=2)
    
    print(f"Context saved to {args.output}")

if __name__ == '__main__':
    main()
