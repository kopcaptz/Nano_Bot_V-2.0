"""Migrate existing SKILL.md files into SkillManager database.

Usage:
    python -m nanobot.agent.migrate_skills [--workspace PATH] [--dry-run]

Scans both built-in skills (nanobot/skills/) and workspace skills
(WORKSPACE/skills/), parses their YAML frontmatter, and imports each
skill into the SkillManager SQLite + vector index.

Idempotent: skills that already exist in the DB are skipped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from loguru import logger


def parse_frontmatter(content: str) -> dict[str, str]:
    """Extract YAML frontmatter key-value pairs from markdown content."""
    if not content.startswith("---"):
        return {}
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    metadata: dict[str, str] = {}
    for line in match.group(1).split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip("\"'")
    return metadata


def strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter, return the body."""
    if content.startswith("---"):
        match = re.match(r"^---\n.*?\n---\n?", content, re.DOTALL)
        if match:
            return content[match.end():].strip()
    return content


def extract_tags_from_metadata(raw_metadata: str) -> list[str]:
    """Try to pull tags / category hints from the nanobot JSON metadata."""
    try:
        data = json.loads(raw_metadata)
        nb = data.get("nanobot", {})
        tags: list[str] = []
        if nb.get("emoji"):
            tags.append(f"emoji:{nb['emoji']}")
        if nb.get("os"):
            tags.extend(f"os:{o}" for o in nb["os"])
        return tags
    except (json.JSONDecodeError, TypeError, AttributeError):
        return []


def discover_skill_dirs(*roots: Path) -> list[Path]:
    """Return a sorted list of directories containing a SKILL.md file."""
    dirs: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for skill_dir in sorted(root.iterdir()):
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file():
                dirs.append(skill_dir)
    return dirs


def migrate(
    workspace: Path,
    dry_run: bool = False,
) -> dict[str, list[str]]:
    """
    Run the migration.

    Returns a dict with 'imported', 'skipped', and 'failed' skill names.
    """
    from nanobot.agent.skill_manager import SkillManager

    builtin_skills_dir = Path(__file__).resolve().parent.parent / "skills"
    workspace_skills_dir = workspace / "skills"

    skill_dirs = discover_skill_dirs(builtin_skills_dir, workspace_skills_dir)
    logger.info(
        f"Found {len(skill_dirs)} SKILL.md files "
        f"(builtin: {builtin_skills_dir}, workspace: {workspace_skills_dir})"
    )

    if not skill_dirs:
        logger.warning("No SKILL.md files found — nothing to migrate.")
        return {"imported": [], "skipped": [], "failed": []}

    storage_dir = workspace / ".skill_manager"
    manager = SkillManager(storage_dir=storage_dir, auto_sync=False)

    imported: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        name = skill_dir.name
        try:
            raw = skill_file.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error(f"Cannot read {skill_file}: {exc}")
            failed.append(name)
            continue

        frontmatter = parse_frontmatter(raw)
        description = frontmatter.get("description", name)
        body = strip_frontmatter(raw)
        tags = extract_tags_from_metadata(frontmatter.get("metadata", ""))

        existing = manager.get_skill(name)
        if existing:
            logger.info(f"  SKIP  {name} (already in DB)")
            skipped.append(name)
            continue

        if dry_run:
            logger.info(f"  [DRY] Would import: {name} — {description[:60]}")
            imported.append(name)
            continue

        try:
            manager.add_skill(
                name=name,
                content=body,
                skill_type="basic",
                description=description,
                tags=tags,
            )
            logger.info(f"  OK    {name}")
            imported.append(name)
        except Exception as exc:
            logger.error(f"  FAIL  {name}: {exc}")
            failed.append(name)

    if not dry_run:
        try:
            manager.rebuild_index()
            logger.info("Vector index rebuilt successfully.")
        except Exception as exc:
            logger.warning(f"Vector index rebuild skipped ({exc})")

    logger.info(
        f"Migration complete: {len(imported)} imported, "
        f"{len(skipped)} skipped, {len(failed)} failed."
    )
    return {"imported": imported, "skipped": skipped, "failed": failed}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate SKILL.md files into SkillManager DB"
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.home() / ".nanobot",
        help="Workspace root (default: ~/.nanobot)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be imported without writing anything",
    )
    args = parser.parse_args()

    result = migrate(workspace=args.workspace, dry_run=args.dry_run)

    if result["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
