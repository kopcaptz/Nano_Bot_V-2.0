"""Database migration runner."""

import sqlite3

from loguru import logger

from nanobot.memory.db import DB_PATH, _connect, init_db


MIGRATIONS = [
    {
        "version": 1,
        "description": "Add domain and sub_category to facts",
        "sql": [
            "ALTER TABLE facts ADD COLUMN domain TEXT DEFAULT NULL",
            "ALTER TABLE facts ADD COLUMN sub_category TEXT DEFAULT NULL",
        ],
    },
]


def get_db_version() -> int:
    """Получает текущую версию схемы БД."""
    try:
        with _connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            return row[0] if row and row[0] else 0
    except Exception:
        return 0


def run_migrations() -> None:
    """Применяет все непримененные миграции."""
    init_db()
    current = get_db_version()

    for migration in MIGRATIONS:
        if migration["version"] <= current:
            continue

        logger.info(f"Running migration v{migration['version']}: {migration['description']}")
        try:
            with _connect() as conn:
                for sql in migration["sql"]:
                    try:
                        conn.execute(sql)
                    except sqlite3.OperationalError as e:
                        if "duplicate column" in str(e).lower():
                            logger.debug(f"Column already exists, skipping: {sql}")
                        else:
                            raise
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (migration["version"],),
                )
                conn.commit()
            logger.info(f"Migration v{migration['version']} completed")
        except Exception as e:
            logger.error(f"Migration v{migration['version']} failed: {e}")
            raise
