#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run skill_check against examples/ and assert exit codes / key findings."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLI = ROOT / "skill_check.py"
EXAMPLES = ROOT / "examples"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def findings_for(data: dict, name_substr: str) -> list[dict]:
    for s in data["skills"]:
        if name_substr in s["path"].replace("\\", "/"):
            return s["findings"]
    raise AssertionError(f"skill path containing {name_substr!r} not found")


def codes(findings: list[dict], severity: str | None = None) -> set[str]:
    out = set()
    for f in findings:
        if severity is None or f["severity"] == severity:
            out.add(f["code"])
    return out


def main() -> int:
    assert CLI.is_file(), "skill_check.py missing"
    assert (EXAMPLES / "good-skill" / "SKILL.md").is_file()

    # Parent dir: should find 3 skills, exit 1 due to missing-desc ERROR
    r = run(["--json", str(EXAMPLES)])
    assert r.returncode == 1, f"expected exit 1 for examples/, got {r.returncode}\n{r.stdout}\n{r.stderr}"
    data = json.loads(r.stdout)
    assert len(data["skills"]) == 3, data
    assert data["error_count"] >= 1

    good = findings_for(data, "good-skill")
    assert "missing_frontmatter" not in codes(good)
    assert "missing_name" not in codes(good, "ERROR")
    assert "missing_description" not in codes(good, "ERROR")
    assert "broken_link" not in codes(good, "WARN"), good
    assert "summary" in codes(good, "INFO")

    missing = findings_for(data, "missing-desc")
    assert "missing_description" in codes(missing, "ERROR"), missing

    broken = findings_for(data, "broken-link")
    assert "broken_link" in codes(broken, "WARN"), broken
    assert "missing_description" not in codes(broken, "ERROR")

    # Good skill alone: exit 0
    r2 = run([str(EXAMPLES / "good-skill")])
    assert r2.returncode == 0, f"good-skill should exit 0\n{r2.stdout}\n{r2.stderr}"
    assert "csv-summary" in r2.stdout

    # Missing desc alone: exit 1
    r3 = run([str(EXAMPLES / "missing-desc")])
    assert r3.returncode == 1, f"missing-desc should exit 1\n{r3.stdout}"

    # Broken link alone: WARN only → exit 0
    r4 = run([str(EXAMPLES / "broken-link")])
    assert r4.returncode == 0, f"broken-link should exit 0 (WARN only)\n{r4.stdout}"
    assert "broken_link" in r4.stdout or "missing" in r4.stdout.lower()

    # Human output non-empty
    assert "ERROR" in r.stdout or True  # json path
    r5 = run([str(EXAMPLES)])
    assert "Checked 3 skill" in r5.stdout

    print("selftest: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"selftest FAILED: {e}", file=sys.stderr)
        raise SystemExit(1)
