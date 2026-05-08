#!/usr/bin/env python3
"""
README Updater - Pre-commit hook and CI/CD step

This script ensures README.md is always synchronized with the current codebase.
It can be used as:
1. Pre-commit hook (via .pre-commit-config.yaml or direct .git/hooks)
2. CI/CD pipeline step (GitHub Actions, GitLab CI, etc.)
3. Standalone development tool

Usage in pre-commit:
    repos:
      - repo: local
        hooks:
          - id: readme-update
            name: Update README.md
            entry: python scripts/generate_readme.py --check
            language: system
            pass_filenames: false
            always_run: true

Usage in CI:
    - name: Update README
      run: python scripts/generate_readme.py --check
"""

import subprocess
import sys
from pathlib import Path

# Get project root (parent of scripts directory)
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
README_PATH = PROJECT_ROOT / "README.md"


def check_readme_outdated() -> bool:
    """Check if README needs regeneration."""
    # Import the generator from the scripts module
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        from generate_readme import generate_readme
        return generate_readme(check_only=True) != 0
    except ImportError:
        # Fallback: simple check based on git status
        return not README_PATH.exists() or _is_any_code_newer_than_readme()


def _is_any_code_newer_than_readme() -> bool:
    """Check if any tracked code files are newer than README."""
    try:
        # Get README modification time
        readme_mtime = README_PATH.stat().st_mtime

        # Check key files that would require README update
        key_files = [
            "core/models.py",
            "core/views.py",
            "core/urls.py",
            "requirements.txt",
            "docker-compose.yml",
        ]

        for filepath in key_files:
            full_path = PROJECT_ROOT / filepath
            if full_path.exists() and full_path.stat().st_mtime > readme_mtime:
                return True

        return False
    except Exception:
        return False


def regenerate_readme() -> int:
    """Regenerate README and return exit code."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        from generate_readme import generate_readme
        return generate_readme(check_only=False)
    except ImportError as e:
        print(f"Error: Could not import generate_readme: {e}")
        return 1


if __name__ == "__main__":
    print("Checking README.md status...")

    if check_readme_outdated():
        print("README.md is outdated. Regenerating...")
        exit_code = regenerate_readme()
        if exit_code == 0:
            print("README.md updated successfully.")
            print("Please commit the updated README.md")
        sys.exit(exit_code)
    else:
        print("README.md is current.")
        sys.exit(0)
