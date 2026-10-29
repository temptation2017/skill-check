#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate coding-agent skill folders (SKILL.md style). Zero deps."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SEVERITY_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}

TRIGGER_CUES = re.compile(
    r"(当|若|如果|用于|适用|场景|何时|when|use\s+this|use\s+when|"
    r"trigger|applicable|for\s+when|should\s+use|useful\s+when)",
    re.IGNORECASE,
)

# Clearer than bare "token"
SECRET_PATTERNS = [
    re.compile(r"api[_-]?key\s*[=:]", re.IGNORECASE),
    re.compile(r"secret[_-]?key\s*[=:]", re.IGNORECASE),
    re.compile(r"password\s*=", re.IGNORECASE),
    re.compile(r"BEGIN\s+PRIVATE\s+KEY", re.IGNORECASE),
    re.compile(r"aws_secret_access_key", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----", re.IGNORECASE),
    re.compile(r"client_secret\s*[=:]", re.IGNORECASE),
]

MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


@dataclass
class Finding:
    severity: str
    code: str
    message: str


@dataclass
class SkillReport:
    path: str
    name: Optional[str] = None
    description: Optional[str] = None
    findings: List[Finding] = field(default_factory=list)

    @property
    def has_error(self) -> bool:
        return any(f.severity == "ERROR" for f in self.findings)


def parse_frontmatter(text: str) -> Tuple[Optional[Dict[str, str]], str, bool]:
    """Return (meta, body, has_frontmatter). Minimal YAML-ish key: value parser."""
    if not text.startswith("---"):
        # allow leading BOM / whitespace
        stripped = text.lstrip("\ufeff")
        if not stripped.lstrip().startswith("---"):
            return None, text, False
        text = stripped.lstrip()

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text, False

    meta_lines: List[str] = []
    i = 1
    closed = False
    while i < len(lines):
        if lines[i].strip() == "---":
            closed = True
            i += 1
            break
        meta_lines.append(lines[i])
        i += 1

    if not closed:
        return None, text, False

    body = "".join(lines[i:])
    meta: Dict[str, str] = {}
    for raw in meta_lines:
        line = raw.rstrip("\n\r")
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        meta[key] = val
    return meta, body, True


def find_skill_files(root: Path) -> List[Path]:
    """Locate SKILL.md files under path (file, skill dir, or parent of skills)."""
    root = root.resolve()
    if root.is_file():
        if root.name.lower() == "skill.md":
            return [root]
        return []

    found: List[Path] = []
    # Direct child SKILL.md
    for candidate in root.iterdir() if root.is_dir() else []:
        if candidate.is_file() and candidate.name.lower() == "skill.md":
            found.append(candidate)

    # Nested: one level of skill dirs, or deeper walk for skill.md
    for dirpath, dirnames, filenames in os.walk(root):
        # skip hidden / venv noise
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(".") and d not in ("__pycache__", "node_modules", ".venv")
        ]
        for fn in filenames:
            if fn.lower() == "skill.md":
                p = Path(dirpath) / fn
                if p not in found:
                    found.append(p)

    # Prefer canonical SKILL.md casing in sort
    found.sort(key=lambda p: str(p).lower())
    return found


def check_relative_links(body: str, skill_dir: Path) -> List[Finding]:
    findings: List[Finding] = []
    for m in MD_LINK_RE.finditer(body):
        href = m.group(2).strip()
        if not href or href.startswith("#"):
            continue
        # skip absolute / scheme links
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", href):
            continue
        if href.startswith("//"):
            continue
        # strip optional title / anchor
        path_part = href.split()[0].split("#")[0]
        if not path_part:
            continue
        target = (skill_dir / path_part).resolve()
        try:
            target.relative_to(skill_dir.resolve())
        except ValueError:
            # path escapes skill dir — still warn as unresolved relative
            findings.append(
                Finding(
                    "WARN",
                    "broken_link",
                    f"relative link does not resolve under skill dir: {path_part}",
                )
            )
            continue
        if not target.exists():
            findings.append(
                Finding(
                    "WARN",
                    "broken_link",
                    f"relative link target missing: {path_part}",
                )
            )
    return findings


def check_secrets(body: str) -> List[Finding]:
    findings: List[Finding] = []
    for pat in SECRET_PATTERNS:
        if pat.search(body):
            findings.append(
                Finding(
                    "WARN",
                    "secret_pattern",
                    f"body may embed credential-like text matching /{pat.pattern}/ — "
                    "do not bake secrets into skills",
                )
            )
            break  # one reminder is enough
    return findings


def validate_skill(path: Path) -> SkillReport:
    report = SkillReport(path=str(path))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        report.findings.append(Finding("ERROR", "read_error", f"cannot read file: {e}"))
        return report

    meta, body, has_fm = parse_frontmatter(text)
    if not has_fm or meta is None:
        report.findings.append(Finding("ERROR", "missing_frontmatter", "missing YAML frontmatter (--- ... ---)"))
        # still INFO on body
        body_for_info = text
    else:
        name = (meta.get("name") or "").strip()
        desc = (meta.get("description") or "").strip()
        report.name = name or None
        report.description = desc or None

        if not name:
            report.findings.append(Finding("ERROR", "missing_name", "missing or empty `name`"))
        if not desc:
            report.findings.append(
                Finding("ERROR", "missing_description", "missing or empty `description`")
            )
        else:
            if len(desc) < 20:
                report.findings.append(
                    Finding("WARN", "short_description", f"description shorter than 20 chars ({len(desc)})")
                )
            if not TRIGGER_CUES.search(desc):
                report.findings.append(
                    Finding(
                        "WARN",
                        "no_trigger_cue",
                        "description may not indicate WHEN to use "
                        "(缺少 当/若/用于/when/use 等触发提示)",
                    )
                )
        body_for_info = body

    body_stripped = body_for_info.strip() if has_fm else text.strip()
    # if frontmatter missing we already errored; still check body length of whole file lightly
    check_body = body if has_fm else ""
    if has_fm:
        if len(check_body.strip()) < 50:
            report.findings.append(
                Finding(
                    "WARN",
                    "short_body",
                    f"body empty or very short ({len(check_body.strip())} chars)",
                )
            )
        report.findings.extend(check_relative_links(check_body, path.parent))
        report.findings.extend(check_secrets(check_body))

    desc_len = len(report.description) if report.description else 0
    body_lines = len(body_for_info.splitlines()) if has_fm else len(text.splitlines())
    report.findings.append(
        Finding(
            "INFO",
            "summary",
            f"name={report.name or '-'} description_len={desc_len} body_lines={body_lines}",
        )
    )
    return report


def format_human(reports: List[SkillReport]) -> str:
    lines: List[str] = []
    for r in reports:
        lines.append(f"== {r.path} ==")
        if r.name:
            lines.append(f"  name: {r.name}")
        # group by severity
        for sev in ("ERROR", "WARN", "INFO"):
            for f in r.findings:
                if f.severity == sev:
                    lines.append(f"  [{sev}] {f.code}: {f.message}")
        lines.append("")
    errors = sum(1 for r in reports for f in r.findings if f.severity == "ERROR")
    warns = sum(1 for r in reports for f in r.findings if f.severity == "WARN")
    lines.append(f"Checked {len(reports)} skill(s): {errors} ERROR, {warns} WARN")
    return "\n".join(lines).rstrip() + "\n"


def format_json(reports: List[SkillReport]) -> str:
    payload = {
        "skills": [
            {
                "path": r.path,
                "name": r.name,
                "description": r.description,
                "findings": [asdict(f) for f in r.findings],
                "has_error": r.has_error,
            }
            for r in reports
        ],
        "error_count": sum(1 for r in reports for f in r.findings if f.severity == "ERROR"),
        "warn_count": sum(1 for r in reports for f in r.findings if f.severity == "WARN"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate coding-agent SKILL.md folders (zero-dependency)."
    )
    parser.add_argument(
        "path",
        help="skill file, skill directory, or parent directory of many skills",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.exists():
        print(f"error: path not found: {args.path}", file=sys.stderr)
        return 1

    files = find_skill_files(root)
    if not files:
        print(f"error: no SKILL.md found under {args.path}", file=sys.stderr)
        return 1

    reports = [validate_skill(p) for p in files]
    out = format_json(reports) if args.json else format_human(reports)
    sys.stdout.write(out)
    return 1 if any(r.has_error for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
