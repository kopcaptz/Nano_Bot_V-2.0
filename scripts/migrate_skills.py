#!/usr/bin/env python3
"""
Migrate existing SKILL.md files from nanobot/skills/ to SkillManager.

Idempotent: re-running skips skills already in the database.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nanobot.agent.skill_manager import SkillManager
from nanobot.memory.vector_manager import VectorDBManager


def parse_frontmatter_and_body(content: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter and body from SKILL.md content.

    Returns:
        (frontmatter_dict, body_str)
    """
    parts = re.split(r"^---\s*$", content.strip(), maxsplit=2, flags=re.MULTILINE)
    if len(parts) < 3:
        return {}, content
    _, frontmatter_raw, body = parts
    frontmatter: dict = {}
    for line in frontmatter_raw.strip().split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1].replace('\\"', '"')
            frontmatter[key] = val
    return frontmatter, body.strip()


def extract_tags_from_metadata(metadata_str: str | None) -> list[str]:
    """Extract tags from metadata.nanobot.requires.bins."""
    if not metadata_str:
        return []
    try:
        meta = json.loads(metadata_str)
        nanobot = meta.get("nanobot") or {}
        requires = nanobot.get("requires") or {}
        bins_list = requires.get("bins")
        if isinstance(bins_list, list):
            return [str(b) for b in bins_list if b]
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def find_skill_files(skills_dir: Path) -> list[Path]:
    """Find all SKILL.md files in nanobot/skills/."""
    return sorted(skills_dir.rglob("SKILL.md"))


def main() -> int:
    """Run migration and return exit code."""
    skills_dir = PROJECT_ROOT / "nanobot" / "skills"
    if not skills_dir.exists():
        logger.error(f"Skills directory not found: {skills_dir}")
        return 1

    skill_files = find_skill_files(skills_dir)
    if not skill_files:
        logger.warning(f"No SKILL.md files found in {skills_dir}")
        return 0

    logger.info(f"Found {len(skill_files)} SKILL.md file(s)")

    storage_dir = Path.home() / ".nanobot" / "skills"
    db_path = Path.home() / ".nanobot" / "chroma"
    db_manager = VectorDBManager(db_path)
    skill_manager = SkillManager(storage_dir, db_manager=db_manager)

    migrated = 0
    skipped = 0
    errors: list[tuple[str, str]] = []

    for skill_path in skill_files:
        name_for_log = str(skill_path.relative_to(PROJECT_ROOT))
        try:
            raw = skill_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read {name_for_log}: {e}")
            errors.append((name_for_log, str(e)))
            continue

        frontmatter, body = parse_frontmatter_and_body(raw)
        name = frontmatter.get("name") or skill_path.parent.name
        description = frontmatter.get("description") or ""
        tags = extract_tags_from_metadata(frontmatter.get("metadata"))

        if skill_manager.get_skill(name):
            logger.debug(f"Skill '{name}' already in SkillManager, skipping")
            skipped += 1
            continue

        try:
            skill_manager.add_skill(
                name=name,
                content=body,
                description=description,
                tags=tags,
                skill_type="basic",
            )
            logger.info(f"Migrated '{name}' from {name_for_log}")
            migrated += 1
        except Exception as e:
            logger.error(f"Failed to migrate {name_for_log}: {e}")
            errors.append((name_for_log, str(e)))

    # Report
    logger.info("--- Migration report ---")
    logger.info(f"Migrated: {migrated}")
    logger.info(f"Skipped (already present): {skipped}")
    logger.info(f"Errors: {len(errors)}")
    for path, err in errors:
        logger.error(f"  {path}: {err}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
