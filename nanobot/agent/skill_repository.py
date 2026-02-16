"""Skill repository with SQLite storage and versioning."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class SkillRepository:
    """
    Centralized skill storage with versioning and metadata management.
    
    Features:
    - SQLite for metadata (skill info, versions, dependencies)
    - Version control for skill evolution
    - Metadata tracking (usage stats, success rate, tags)
    - JSONL execution history
    """
    
    def __init__(self, db_path: Path | str):
        """
        Initialize skill repository.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_dir = self.db_path.parent / "history"
        self.history_dir.mkdir(exist_ok=True)
        
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    skill_type TEXT NOT NULL DEFAULT 'basic',
                    description TEXT,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usage_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1
                );
                
                CREATE TABLE IF NOT EXISTS skill_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    change_description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
                    UNIQUE(skill_id, version)
                );
                
                CREATE TABLE IF NOT EXISTS skill_dependencies (
                    skill_id INTEGER NOT NULL,
                    depends_on_skill_id INTEGER NOT NULL,
                    dependency_type TEXT DEFAULT 'required',
                    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
                    FOREIGN KEY (depends_on_skill_id) REFERENCES skills(id) ON DELETE CASCADE,
                    PRIMARY KEY (skill_id, depends_on_skill_id)
                );
                
                CREATE TABLE IF NOT EXISTS skill_tags (
                    skill_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
                    PRIMARY KEY (skill_id, tag)
                );
                
                CREATE TABLE IF NOT EXISTS skill_metadata (
                    skill_id INTEGER PRIMARY KEY,
                    embeddings_updated_at TIMESTAMP,
                    last_execution_at TIMESTAMP,
                    average_execution_time_ms REAL,
                    metadata_json TEXT,
                    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
                );
                
                CREATE INDEX IF NOT EXISTS idx_skills_type ON skills(skill_type);
                CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
                CREATE INDEX IF NOT EXISTS idx_skill_tags_tag ON skill_tags(tag);
            """)
            conn.commit()
        finally:
            conn.close()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def add_skill(
        self,
        name: str,
        content: str,
        skill_type: str = "basic",
        description: str | None = None,
        tags: list[str] | None = None,
        dependencies: list[str] | None = None,
    ) -> int:
        """
        Add a new skill to the repository.
        
        Args:
            name: Unique skill name
            content: Skill content (markdown)
            skill_type: Type of skill (basic, composite, meta)
            description: Short description
            tags: List of tags for categorization
            dependencies: List of skill names this skill depends on
        
        Returns:
            Skill ID
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO skills (name, skill_type, description, content, version)
                VALUES (?, ?, ?, ?, 1)
                """,
                (name, skill_type, description or "", content),
            )
            skill_id = cursor.lastrowid
            
            # Save initial version
            conn.execute(
                """
                INSERT INTO skill_versions (skill_id, version, content, change_description)
                VALUES (?, 1, ?, 'Initial version')
                """,
                (skill_id, content),
            )
            
            # Add tags
            if tags:
                for tag in tags:
                    conn.execute(
                        "INSERT OR IGNORE INTO skill_tags (skill_id, tag) VALUES (?, ?)",
                        (skill_id, tag),
                    )
            
            # Add dependencies
            if dependencies:
                for dep_name in dependencies:
                    dep_row = conn.execute(
                        "SELECT id FROM skills WHERE name = ?", (dep_name,)
                    ).fetchone()
                    if dep_row:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO skill_dependencies 
                            (skill_id, depends_on_skill_id) VALUES (?, ?)
                            """,
                            (skill_id, dep_row[0]),
                        )
            
            conn.commit()
            logger.info(f"Added skill '{name}' with ID {skill_id}")
            return skill_id
        except sqlite3.IntegrityError as e:
            logger.error(f"Skill '{name}' already exists: {e}")
            raise ValueError(f"Skill '{name}' already exists") from e
        finally:
            conn.close()
    
    def update_skill(
        self, name: str, content: str, change_description: str | None = None
    ) -> bool:
        """
        Update skill content and increment version.
        
        Args:
            name: Skill name
            content: New content
            change_description: Description of changes
        
        Returns:
            True if updated successfully
        """
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT id, version FROM skills WHERE name = ?", (name,)).fetchone()
            if not row:
                return False
            
            skill_id, current_version = row[0], row[1]
            new_version = current_version + 1
            
            # Update skill
            conn.execute(
                """
                UPDATE skills 
                SET content = ?, version = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (content, new_version, skill_id),
            )
            
            # Save version
            conn.execute(
                """
                INSERT INTO skill_versions (skill_id, version, content, change_description)
                VALUES (?, ?, ?, ?)
                """,
                (skill_id, new_version, content, change_description or "Updated"),
            )
            
            conn.commit()
            logger.info(f"Updated skill '{name}' to version {new_version}")
            return True
        finally:
            conn.close()
    
    def get_skill(self, name: str) -> dict[str, Any] | None:
        """
        Get skill by name.
        
        Args:
            name: Skill name
        
        Returns:
            Skill dict or None
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                """
                SELECT id, name, skill_type, description, content, 
                       created_at, updated_at, usage_count, success_count, version
                FROM skills WHERE name = ?
                """,
                (name,),
            ).fetchone()
            
            if not row:
                return None
            
            skill = dict(row)
            
            # Get tags
            tags_rows = conn.execute(
                "SELECT tag FROM skill_tags WHERE skill_id = ?", (skill["id"],)
            ).fetchall()
            skill["tags"] = [r[0] for r in tags_rows]
            
            # Get dependencies
            deps_rows = conn.execute(
                """
                SELECT s.name FROM skill_dependencies sd
                JOIN skills s ON sd.depends_on_skill_id = s.id
                WHERE sd.skill_id = ?
                """,
                (skill["id"],),
            ).fetchall()
            skill["dependencies"] = [r[0] for r in deps_rows]
            
            return skill
        finally:
            conn.close()
    
    def list_skills(
        self, skill_type: str | None = None, tags: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        List skills with optional filtering.
        
        Args:
            skill_type: Filter by skill type
            tags: Filter by tags (AND logic)
        
        Returns:
            List of skill dicts
        """
        conn = self._get_connection()
        try:
            query = """
                SELECT id, name, skill_type, description, 
                       usage_count, success_count, version
                FROM skills
                WHERE 1=1
            """
            params = []
            
            if skill_type:
                query += " AND skill_type = ?"
                params.append(skill_type)
            
            if tags:
                # Skills that have ALL specified tags
                for tag in tags:
                    query += f"""
                        AND id IN (
                            SELECT skill_id FROM skill_tags WHERE tag = ?
                        )
                    """
                    params.append(tag)
            
            query += " ORDER BY name"
            
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
    
    def record_execution(
        self,
        name: str,
        success: bool,
        execution_time_ms: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """
        Record skill execution for statistics and history.
        
        Args:
            name: Skill name
            success: Whether execution was successful
            execution_time_ms: Execution time in milliseconds
            context: Additional execution context
        """
        conn = self._get_connection()
        try:
            # Update stats
            if success:
                conn.execute(
                    """
                    UPDATE skills 
                    SET usage_count = usage_count + 1, 
                        success_count = success_count + 1
                    WHERE name = ?
                    """,
                    (name,),
                )
            else:
                conn.execute(
                    "UPDATE skills SET usage_count = usage_count + 1 WHERE name = ?",
                    (name,),
                )
            
            # Update metadata
            skill_row = conn.execute("SELECT id FROM skills WHERE name = ?", (name,)).fetchone()
            if skill_row:
                skill_id = skill_row[0]
                if execution_time_ms is not None:
                    conn.execute(
                        """
                        INSERT INTO skill_metadata (skill_id, last_execution_at, average_execution_time_ms)
                        VALUES (?, CURRENT_TIMESTAMP, ?)
                        ON CONFLICT(skill_id) DO UPDATE SET
                            last_execution_at = CURRENT_TIMESTAMP,
                            average_execution_time_ms = 
                                (COALESCE(average_execution_time_ms, 0) * 0.8 + ? * 0.2)
                        """,
                        (skill_id, execution_time_ms, execution_time_ms),
                    )
            
            conn.commit()
            
            # Append to JSONL history
            self._append_history(name, success, execution_time_ms, context)
        finally:
            conn.close()
    
    def _append_history(
        self,
        name: str,
        success: bool,
        execution_time_ms: float | None,
        context: dict[str, Any] | None,
    ) -> None:
        """Append execution to JSONL history file."""
        history_file = self.history_dir / f"{name}.jsonl"
        record = {
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "execution_time_ms": execution_time_ms,
            "context": context or {},
        }
        
        with history_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    def get_skill_history(self, name: str, limit: int = 100) -> list[dict[str, Any]]:
        """
        Get execution history for a skill.
        
        Args:
            name: Skill name
            limit: Maximum number of records
        
        Returns:
            List of execution records
        """
        history_file = self.history_dir / f"{name}.jsonl"
        if not history_file.exists():
            return []
        
        records = []
        with history_file.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        
        return records[-limit:]
    
    def get_skill_stats(self, name: str) -> dict[str, Any] | None:
        """
        Get statistics for a skill.
        
        Args:
            name: Skill name
        
        Returns:
            Statistics dict or None
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                """
                SELECT s.usage_count, s.success_count, s.version,
                       sm.average_execution_time_ms, sm.last_execution_at
                FROM skills s
                LEFT JOIN skill_metadata sm ON s.id = sm.skill_id
                WHERE s.name = ?
                """,
                (name,),
            ).fetchone()
            
            if not row:
                return None
            
            stats = dict(row)
            if stats["usage_count"] > 0:
                stats["success_rate"] = stats["success_count"] / stats["usage_count"]
            else:
                stats["success_rate"] = 0.0
            
            return stats
        finally:
            conn.close()
    
    def delete_skill(self, name: str) -> bool:
        """
        Delete a skill and its history.
        
        Args:
            name: Skill name
        
        Returns:
            True if deleted successfully
        """
        conn = self._get_connection()
        try:
            result = conn.execute("DELETE FROM skills WHERE name = ?", (name,))
            conn.commit()
            
            # Delete history file
            history_file = self.history_dir / f"{name}.jsonl"
            if history_file.exists():
                history_file.unlink()
            
            return result.rowcount > 0
        finally:
            conn.close()
