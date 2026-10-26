#!/usr/bin/env python3
"""Fail when tracked files contain common secrets or private cohort artifacts."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str


FORBIDDEN_PATH_PATTERNS = (
    (
        re.compile(r"(^|/)\.env(?:\.(?!example$).+)?$"),
        "tracked environment file",
    ),
    (re.compile(r"(^|/)(?:private_data|data_private)(/|$)"), "private data directory"),
    (re.compile(r"_cohort\.rds$", re.IGNORECASE), "private cohort RDS"),
    (re.compile(r"(^|/)xprs_rare_findings_[^/]*\.tsv$", re.IGNORECASE), "rare-variant handoff"),
    (re.compile(r"(^|/)evaluation_responses(/|$)"), "evaluation response"),
)

SECRET_PATTERNS = (
    (re.compile(rb"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b"), "OpenRouter-style key"),
    (re.compile(rb"\bsk-[A-Za-z0-9_-]{32,}\b"), "API key"),
    (re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "GitHub token"),
    (re.compile(rb"\bAKIA[A-Z0-9]{16}\b"), "AWS access key"),
    (
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "private key",
    ),
)

PRIVATE_SOURCE_PATTERNS = (
    (re.compile(rb"/media/" + rb"leelabsg-storage1/"), "internal storage path"),
    (
        re.compile(rb"\bKP-(?!ABCDEF123456\b)[A-F0-9]{12}\b"),
        "K-PREDICT pseudonymous individual ID",
    ),
)

SECRET_ASSIGNMENT_RE = re.compile(
    rb"^(OPENROUTER_API_KEY|S2_API_KEY|XPRS_ADMIN_TOKEN|XPRS_EVALUATION_TOKEN|XPRS_KPREDICT_TOKEN)"
    rb"=[ \t]*([^#\r\n]+)",
    re.MULTILINE,
)


def tracked_paths(root: Path = ROOT) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def _has_nonempty_secret_assignment(payload: bytes) -> bool:
    for match in SECRET_ASSIGNMENT_RE.finditer(payload):
        value = match.group(2).strip().strip(b'"\'')
        if value and value not in {b"VALUE", b"CHANGEME", b"REPLACE_ME"}:
            return True
    return False


def scan_repository(root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in tracked_paths(root):
        relative = path.relative_to(root).as_posix()
        for pattern, rule in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(relative):
                findings.append(Finding(relative, rule))

        if not path.is_file() or path.stat().st_size > MAX_TEXT_FILE_BYTES:
            continue
        payload = path.read_bytes()
        if b"\0" in payload:
            continue
        for pattern, rule in (*SECRET_PATTERNS, *PRIVATE_SOURCE_PATTERNS):
            if pattern.search(payload):
                findings.append(Finding(relative, rule))
        if _has_nonempty_secret_assignment(payload):
            findings.append(Finding(relative, "non-empty secret assignment"))
    return sorted(set(findings), key=lambda finding: (finding.path, finding.rule))


def main() -> int:
    try:
        findings = scan_repository()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Unable to inspect tracked files: {exc}", file=sys.stderr)
        return 2

    if findings:
        print("Public-repository check failed:")
        for finding in findings:
            print(f"  {finding.path}: {finding.rule}")
        print("Matched values are intentionally not printed.")
        return 1

    print("Public-repository check passed: no tracked secrets or private cohort artifacts found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
