#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
README 자동 업데이트 스크립트

Git diff를 분석하여 LLM을 통해 README.md의 자동 업데이트 섹션을 갱신합니다.
- .github/ 디렉토리 및 README.md 파일들은 분석 대상에서 제외
- Dir Structure, Workflow, Features, Versions 섹션을 자동으로 업데이트
- 마지막 처리된 commit SHA를 추적하여 중복 처리 방지
"""

import argparse
import os
import re
import subprocess
from pathlib import Path
from typing import List, Tuple

from tenacity import retry, stop_after_attempt, wait_exponential

from openai import OpenAI

# -----------------------------
# Helpers
# -----------------------------

def run(cmd: List[str]) -> str:
    out = subprocess.check_output(cmd, text=True).strip()
    return out

def get_current_sha() -> str:
    return run(["git", "rev-parse", "HEAD"])

def extract_marker(text: str, start_mark: str, end_mark: str) -> str | None:
    # e.g., <!-- LAST_PROCESSED_SHA: <sha> -->
    pat = re.escape(start_mark) + r"\s*([0-9a-f]{7,40})\s*" + re.escape(end_mark)
    m = re.search(pat, text)
    return m.group(1) if m else None

def upsert_marker(text: str, start_mark: str, end_mark: str, sha: str) -> str:
    pat = re.escape(start_mark) + r"\s*([0-9a-f]{7,40})\s*" + re.escape(end_mark)
    repl = f"{start_mark} {sha} {end_mark}"
    if re.search(pat, text):
        return re.sub(pat, repl, text)
    else:
        # 없으면 맨 아래에 추가
        return text.rstrip() + "\n\n" + repl + "\n"

def slice_between(text: str, start_mark: str, end_mark: str) -> Tuple[int, int]:
    s = text.find(start_mark)
    e = text.find(end_mark)
    if s == -1 or e == -1 or e <= s:
        return (-1, -1)
    return (s + len(start_mark), e)

def replace_between(text: str, start_mark: str, end_mark: str, new_content: str) -> str:
    s, e = slice_between(text, start_mark, end_mark)
    if s == -1:
        # 구간이 없으면 생성
        return text.rstrip() + f"\n\n{start_mark}\n{new_content}\n{end_mark}\n"
    return text[:s] + "\n" + new_content.strip() + "\n" + text[e:]

def calc_changed_files(target_dir: str, base_sha: str, head_sha: str) -> List[str]:
    if base_sha == head_sha:
        return []
    diff_out = run(["git", "diff", "--name-only", f"{base_sha}..{head_sha}", "--", target_dir])
    # .github 디렉토리 및 README.md는 제외 (이 파일들만 변경되면 LLM 호출 회피)
    files = [f for f in diff_out.splitlines()
             if f.strip() and not f.startswith('.github/') and not f.endswith('README.md')]
    return files

def collect_diffs(files: List[str], base_sha: str, head_sha: str, max_bytes: int) -> str:
    # 변경 파일들의 간략 diff (size 제한)
    chunks = []
    used = 0
    for f in files:
        # --unified=3 정도의 컨텍스트로 충분
        diff_txt = run(["git", "diff", f"{base_sha}..{head_sha}", "--", f])
        if not diff_txt:
            continue
        header = f"\n### {f}\n```\n"
        footer = "\n```\n"
        piece = header + diff_txt + footer
        b = len(piece.encode("utf-8"))
        if used + b > max_bytes:
            remain = max_bytes - used
            if remain > 1024:
                # 남은 바이트 안에서 절단
                piece = (header + diff_txt)[:remain] + "\n```\n"
                chunks.append(piece)
                used = max_bytes
            break
        chunks.append(piece)
        used += b
    return "\n".join(chunks).strip()

# -----------------------------
# LLM call
# -----------------------------

@retry(wait=wait_exponential(multiplier=1, min=2, max=20), stop=stop_after_attempt(4))
def llm_summarize(openai_key: str, model: str, prompt: str) -> str:
    client = OpenAI(api_key=openai_key)

    token_param = {"max_output_tokens": 6000}

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": "You are a technical documentation expert specializing in README maintenance for Cloudflare Workers projects."},
            {"role": "user", "content": prompt}
        ],
        **token_param
    )
    return resp.output_text

# -----------------------------
# Main
# -----------------------------

TEMPLATE = """You are a technical documentation expert for Cloudflare Workers projects.
Analyze repository changes and update the README structure comprehensively.

## Repository Context
- Project: Monte Carlo Simulation Web App (Cloudflare Workers + Python)
- Target directory: {target_dir} (excluding .github/ directory and README.md)
- Base commit: {base_sha}
- Head commit: {head_sha}
- Note: Changes in .github/ (workflows, scripts) and README.md are intentionally excluded from analysis

## Current README Structure
The README must maintain these sections in order:
1. **Dir Structure** - Project file tree with descriptions
2. **Workflow** - Request flow, simulation pipeline, deployment process
3. **Features** - Core features (5 categories) and technical highlights
4. **Versions** - Version history with changes, optimizations, bug fixes

## Your Task
Analyze the diff and update **ALL FOUR SECTIONS** as needed:

### Dir Structure
- Update file tree if files were added/removed/moved
- Add descriptions for new files
- Use tree format with comments (e.g., `├── file.py  # description`)
- Comment only the important points briefly

### Workflow
- Update if API endpoints changed
- Modify simulation pipeline steps if compute logic changed
- Update deployment commands if wrangler.toml changed

### Features
Update relevant subsections:
- **핵심 기능** (5 numbered items): simulation, game modes, UI, visualization, optimization
- **기술적 특징**: algorithms, performance metrics, security

### Versions
- Add new version entry at the top if significant changes occurred
- Use semantic versioning (v2.1, v2.2, etc.)
- Categorize changes: 주요 변경사항, 최적화, 버그 수정, 새 기능

## Output Requirements
- Write in Korean
- Output **ONLY** the markdown content for the auto-update section
- Include all 4 section headers: `## Dir Structure`, `## Workflow`, `## Features`, `## Versions`
- Preserve existing content that wasn't affected by changes
- Be precise and technical - include function names, file paths, specific values
- Use code blocks for directory trees and bash commands
- Maximum length: 1000 lines

## Current README Content (for reference)
```markdown
{current_content}
```

## Code Change Analysis
{diff}

## Instructions
1. Read the current README content above
2. Analyze the code changes (diff)
3. Determine which sections need updates:
   - File added/removed → Update Dir Structure
   - API/logic changed → Update Workflow
   - New feature/optimization → Update Features
   - Significant changes → Add Versions entry
4. Output the COMPLETE content for all 4 sections, preserving unchanged parts

Remember: Output ONLY the markdown content, starting with `## Dir Structure` and ending with the last version entry.
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-dir", required=True)
    ap.add_argument("--readme", required=True)
    ap.add_argument("--llm-model", default=os.getenv("LLM_MODEL", "gpt-4o-mini"))
    ap.add_argument("--section-start", required=True)
    ap.add_argument("--section-end", required=True)
    ap.add_argument("--last-sha-start", required=True)
    ap.add_argument("--last-sha-end", default="-->")  # 기본값 설정으로 shell 이스케이프 문제 해결
    ap.add_argument("--max-diff-bytes", type=int, default=int(os.getenv("MAX_DIFF_BYTES", "60000")))
    args = ap.parse_args()

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise SystemExit("OPENAI_API_KEY is not set")

    repo_root = Path(".").resolve()
    readme_path = repo_root / args.readme

    # 현재 SHA
    head_sha = get_current_sha()

    # README 읽고 마지막 처리 SHA 찾기
    readme_txt = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    base_sha = extract_marker(readme_txt, args.last_sha_start, args.last_sha_end)
    if base_sha is None:
        # 최초 실행: 한 커밋 전을 기준으로
        try:
            base_sha = run(["git", "rev-parse", "HEAD~1"])
        except subprocess.CalledProcessError:
            base_sha = head_sha  # 초기 레포면 동일

    # 변경 파일 수집
    changed = calc_changed_files(args.target_dir, base_sha, head_sha)
    if not changed:
        print("No changes in target directory since last processed SHA. Skipping LLM call.")
        # 그래도 최신 SHA로 마커만 갱신
        updated = upsert_marker(readme_txt, args.last_sha_start, args.last_sha_end, head_sha)
        if updated != readme_txt:
            readme_path.write_text(updated, encoding="utf-8")
        return

    print(f"Detected {len(changed)} changed file(s). Proceeding with LLM analysis...")

    # diff 모으기
    diff_snippets = collect_diffs(changed, base_sha, head_sha, args.max_diff_bytes)

    # 현재 README 자동 업데이트 섹션 추출 (참고용)
    current_section = ""
    s_idx, e_idx = slice_between(readme_txt, args.section_start, args.section_end)
    if s_idx != -1:
        current_section = readme_txt[s_idx:e_idx].strip()

    # 프롬프트
    prompt = TEMPLATE.format(
        target_dir=args.target_dir,
        base_sha=base_sha,
        head_sha=head_sha,
        diff=diff_snippets or "No textual diff available.",
        current_content=current_section or "No existing auto-update section."
    )

    # LLM 호출
    content = llm_summarize(openai_key, args.llm_model, prompt).strip()

    # README 섹션 갱신
    readme_new = replace_between(readme_txt, args.section_start, args.section_end, content)
    # 마지막 처리 SHA 갱신
    readme_new = upsert_marker(readme_new, args.last_sha_start, args.last_sha_end, head_sha)

    if readme_new != readme_txt:
        Path(readme_path).write_text(readme_new, encoding="utf-8")
        print("README updated.")
    else:
        print("README unchanged.")

if __name__ == "__main__":
    main()
