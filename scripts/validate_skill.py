#!/usr/bin/env python3
"""Validate the repository's Flowlines MCP observability skill package."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "flowlines-mcp-observability"
SKILL_FILE = SKILL_DIR / "SKILL.md"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def frontmatter(markdown: str) -> dict[str, str]:
    if not markdown.startswith("---\n"):
        fail("SKILL.md must start with YAML frontmatter")
    try:
        header, _body = markdown[4:].split("\n---\n", 1)
    except ValueError:
        fail("SKILL.md frontmatter is not closed")

    fields: dict[str, str] = {}
    for line in header.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def validate_relative_links(path: Path, markdown: str) -> None:
    skill_root = SKILL_DIR.resolve()
    for raw_target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", markdown):
        target = raw_target.split("#", 1)[0]
        if not target or "://" in target or target.startswith(("#", "mailto:")):
            continue
        resolved = (path.parent / target).resolve()
        if resolved != skill_root and skill_root not in resolved.parents:
            fail(f"link escapes the skill directory: {raw_target}")
        if not resolved.is_file():
            fail(f"missing linked skill resource: {raw_target}")


def main() -> None:
    if not SKILL_FILE.is_file():
        fail(f"missing {SKILL_FILE.relative_to(ROOT)}")

    markdown = SKILL_FILE.read_text(encoding="utf-8")
    fields = frontmatter(markdown)
    if fields.get("name") != SKILL_DIR.name:
        fail("skill name must match its directory")
    if not fields.get("description"):
        fail("skill description must be non-empty")
    if "TODO" in markdown or "[TODO" in markdown:
        fail("unfinished scaffold placeholder in SKILL.md")

    validate_relative_links(SKILL_FILE, markdown)
    for reference in sorted((SKILL_DIR / "references").glob("*.md")):
        validate_relative_links(reference, reference.read_text(encoding="utf-8"))
    readme = ROOT / "README.md"
    validate_relative_links(readme, readme.read_text(encoding="utf-8"))

    openai_yaml = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if "$flowlines-mcp-observability" not in openai_yaml:
        fail("agents/openai.yaml default prompt must name the skill")

    print("Validated skills/flowlines-mcp-observability")


if __name__ == "__main__":
    main()
