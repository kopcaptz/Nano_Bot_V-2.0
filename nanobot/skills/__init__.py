"""Nanobot skills registry."""

from pathlib import Path

def list_skills():
    """List all available skills."""
    skills_dir = Path(__file__).parent
    return [d.name for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]

__all__ = ["list_skills"]
