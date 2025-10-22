#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
README 전체 재구성 스크립트

프로젝트의 모든 파일을 분석하여 README.md를 처음부터 완전히 재생성합니다.
- Git diff 대신 현재 파일 트리를 직접 분석
- 전체 코드베이스를 LLM에 제공하여 포괄적인 문서 생성
- 수동 실행 전용 (GitHub Actions의 workflow_dispatch로 트리거)
"""

import argparse
import os
import subprocess
from pathlib import Path
from typing import List, Dict

from tenacity import retry, stop_after_attempt, wait_exponential
from openai import OpenAI

# -----------------------------
# Helpers
# -----------------------------

def run(cmd: List[str]) -> str:
    """Execute shell command and return output"""
    out = subprocess.check_output(cmd, text=True).strip()
    return out

def get_current_sha() -> str:
    """Get current Git commit SHA"""
    return run(["git", "rev-parse", "HEAD"])

def collect_file_tree(root_dir: Path, exclude_patterns: List[str]) -> str:
    """
    Generate a file tree structure of the project

    Args:
        root_dir: Root directory to scan
        exclude_patterns: List of patterns to exclude (e.g., '.git', 'node_modules')

    Returns:
        String representation of the file tree
    """
    tree_lines = []

    def should_exclude(path: Path) -> bool:
        path_str = str(path)
        for pattern in exclude_patterns:
            if pattern in path_str:
                return True
        return False

    def walk_directory(directory: Path, prefix: str = "", is_last: bool = True):
        """Recursively walk directory and build tree"""
        if should_exclude(directory):
            return

        entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        entries = [e for e in entries if not should_exclude(e)]

        for i, entry in enumerate(entries):
            is_last_entry = i == len(entries) - 1
            connector = "└── " if is_last_entry else "├── "
            tree_lines.append(f"{prefix}{connector}{entry.name}")

            if entry.is_dir():
                extension = "    " if is_last_entry else "│   "
                walk_directory(entry, prefix + extension, is_last_entry)

    tree_lines.append(root_dir.name + "/")
    walk_directory(root_dir)

    return "\n".join(tree_lines)

def collect_file_contents(root_dir: Path, include_extensions: List[str],
                          exclude_patterns: List[str], max_bytes: int) -> Dict[str, str]:
    """
    Collect contents of key files in the project

    Args:
        root_dir: Root directory to scan
        include_extensions: List of file extensions to include (e.g., ['.py', '.js', '.html'])
        exclude_patterns: List of patterns to exclude
        max_bytes: Maximum total bytes to collect

    Returns:
        Dict mapping file paths to their contents
    """
    file_contents = {}
    total_bytes = 0

    def should_exclude(path: Path) -> bool:
        path_str = str(path.relative_to(root_dir))
        for pattern in exclude_patterns:
            if pattern in path_str:
                return True
        return False

    # Priority files (always include first)
    priority_files = [
        'wrangler.toml',
        'package.json',
        'KV_INTEGRATION.md',
        'PERFORMANCE.md',
    ]

    # Collect priority files first
    for priority_file in priority_files:
        file_path = root_dir / priority_file
        if file_path.exists() and file_path.is_file():
            try:
                content = file_path.read_text(encoding='utf-8')
                size = len(content.encode('utf-8'))
                if total_bytes + size <= max_bytes:
                    file_contents[str(file_path.relative_to(root_dir))] = content
                    total_bytes += size
            except Exception:
                pass

    # Collect remaining files
    for file_path in sorted(root_dir.rglob('*')):
        if not file_path.is_file():
            continue

        if should_exclude(file_path):
            continue

        if file_path.suffix not in include_extensions:
            continue

        rel_path = str(file_path.relative_to(root_dir))
        if rel_path in file_contents:
            continue

        try:
            content = file_path.read_text(encoding='utf-8')
            size = len(content.encode('utf-8'))

            if total_bytes + size > max_bytes:
                print(f"Reached max bytes limit at {rel_path}")
                break

            file_contents[rel_path] = content
            total_bytes += size
        except Exception as e:
            print(f"Warning: Could not read {rel_path}: {e}")

    return file_contents

def format_file_contents(file_contents: Dict[str, str]) -> str:
    """Format file contents for LLM prompt"""
    chunks = []

    for file_path, content in file_contents.items():
        chunks.append(f"\n### {file_path}\n```\n{content}\n```\n")

    return "\n".join(chunks)

# -----------------------------
# LLM call
# -----------------------------

@retry(wait=wait_exponential(multiplier=1, min=2, max=20), stop=stop_after_attempt(4))
def llm_rebuild_readme(openai_key: str, model: str, prompt: str) -> str:
    """Call LLM to rebuild README from scratch"""
    client = OpenAI(api_key=openai_key)

    token_param = {"max_output_tokens": 8000}

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": "You are a technical documentation expert specializing in creating comprehensive README files for Cloudflare Workers projects."},
            {"role": "user", "content": prompt}
        ],
        **token_param
    )
    return resp.output_text

# -----------------------------
# Main
# -----------------------------

REBUILD_TEMPLATE = """You are a technical documentation expert for Cloudflare Workers projects.
Your task is to create a comprehensive README.md from scratch by analyzing the entire codebase.

## Project Information
- Type: Monte Carlo Simulation Web App
- Stack: Cloudflare Workers + Python Workers + JavaScript frontend
- Current commit: {commit_sha}

## File Tree Structure
```
{file_tree}
```

## Key File Contents
{file_contents}

## Your Task
Create a COMPLETE README.md auto-update section with these four sections:

### 1. Dir Structure
- Provide a detailed file tree with inline comments
- Include descriptions for ALL important files and directories
- Use tree format: `├── filename  # description`
- Organize by logical sections (root, subdirectories)
- Comment briefly but precisely on each file's purpose

### 2. Workflow
- Document the complete request flow from client to server
- Explain the simulation pipeline (data loading, computation, response)
- Include API endpoint documentation
- Show deployment process and key commands
- Use diagrams/flowcharts where helpful (in text format)

### 3. Features
Structure this section with:
- **핵심 기능** (5 numbered items covering):
  1. Simulation capabilities
  2. Game modes
  3. UI/UX features
  4. Visualization features
  5. Optimization features

- **기술적 특징**:
  - Algorithms used (Monte Carlo, statistical methods)
  - Performance metrics (response time, optimization techniques)
  - Security features
  - Architecture highlights (Assets binding, KV integration, CDN usage)

### 4. Versions
- Create a comprehensive version history
- Start from v1.0 and include all major versions
- For each version include:
  - Version number (semantic versioning)
  - 주요 변경사항 (major changes)
  - 최적화 (optimizations)
  - 버그 수정 (bug fixes)
  - 새 기능 (new features)
- Most recent version should be at the top

## Output Requirements
- Write in Korean
- Output ONLY the markdown content for the auto-update section
- Start with `## Dir Structure` and end with the last version entry
- Be comprehensive and detailed - include function names, file paths, technical specifics
- Use code blocks for directory trees, code examples, and bash commands
- Maximum length: 1500 lines
- Be precise and technical, not generic

## Important Notes
- This is a COMPLETE rebuild, not an incremental update
- Analyze ALL files provided to understand the full architecture
- Ensure all four sections are comprehensive and interconnected
- Focus on accuracy and technical depth

Remember: Output ONLY the markdown content, starting with `## Dir Structure` and ending with the version history.
"""

def main():
    ap = argparse.ArgumentParser(description="Rebuild README.md from scratch using LLM analysis")
    ap.add_argument("--target-dir", required=True, help="Root directory of the project")
    ap.add_argument("--readme", required=True, help="Path to README.md file")
    ap.add_argument("--llm-model", default=os.getenv("LLM_MODEL", "gpt-4o"),
                    help="LLM model to use")
    ap.add_argument("--section-start", required=True,
                    help="Marker for auto-update section start")
    ap.add_argument("--section-end", required=True,
                    help="Marker for auto-update section end")
    ap.add_argument("--last-sha-start", required=True,
                    help="Marker for last processed SHA start")
    ap.add_argument("--last-sha-end", default="-->",
                    help="Marker for last processed SHA end")
    ap.add_argument("--max-file-bytes", type=int,
                    default=int(os.getenv("MAX_FILE_BYTES", "150000")),
                    help="Maximum bytes of file contents to collect")
    args = ap.parse_args()

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise SystemExit("OPENAI_API_KEY is not set")

    repo_root = Path(args.target_dir).resolve()
    readme_path = Path(args.readme).resolve()

    # Get current commit SHA
    current_sha = get_current_sha()

    print("Collecting project file tree...")
    exclude_patterns = ['.git', '__pycache__', 'node_modules', '.venv', 'dist', 'build']
    file_tree = collect_file_tree(repo_root, exclude_patterns)

    print("Collecting file contents...")
    include_extensions = ['.py', '.js', '.html', '.css', '.toml', '.json', '.md', '.yml', '.yaml', '.txt']
    exclude_patterns.extend(['.github/scripts', 'assets/data'])  # Skip generated data and scripts
    file_contents = collect_file_contents(
        repo_root,
        include_extensions,
        exclude_patterns,
        args.max_file_bytes
    )

    print(f"Collected {len(file_contents)} files totaling {sum(len(c.encode('utf-8')) for c in file_contents.values())} bytes")

    # Format file contents for prompt
    formatted_contents = format_file_contents(file_contents)

    # Build prompt
    prompt = REBUILD_TEMPLATE.format(
        commit_sha=current_sha,
        file_tree=file_tree,
        file_contents=formatted_contents
    )

    print("Calling LLM to rebuild README...")
    new_content = llm_rebuild_readme(openai_key, args.llm_model, prompt).strip()

    # Read current README
    readme_txt = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

    # Find and replace the auto-update section
    start_idx = readme_txt.find(args.section_start)
    end_idx = readme_txt.find(args.section_end)

    if start_idx == -1 or end_idx == -1:
        print("Error: Could not find auto-update section markers in README")
        print(f"Looking for: {args.section_start} ... {args.section_end}")
        raise SystemExit(1)

    # Reconstruct README
    before_section = readme_txt[:start_idx + len(args.section_start)]
    after_section = readme_txt[end_idx:]

    new_readme = before_section + "\n" + new_content.strip() + "\n" + after_section

    # Add/update the last processed SHA marker
    import re
    sha_marker = f"{args.last_sha_start} {current_sha} {args.last_sha_end}"
    sha_pattern = re.escape(args.last_sha_start) + r"\s*[0-9a-f]{7,40}\s*" + re.escape(args.last_sha_end)

    if re.search(sha_pattern, new_readme):
        new_readme = re.sub(sha_pattern, sha_marker, new_readme)
    else:
        new_readme = new_readme.rstrip() + "\n\n" + sha_marker + "\n"

    # Write the new README
    readme_path.write_text(new_readme, encoding="utf-8")
    print(f"README.md has been completely rebuilt!")
    print(f"Processed commit: {current_sha}")

if __name__ == "__main__":
    main()
