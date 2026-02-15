"""
Entry point for running nanobot as a module: python -m nanobot
"""

from nanobot.cli.commands import app
from nanobot.memory.migrate import run_migrations

if __name__ == "__main__":
    run_migrations()
    app()
