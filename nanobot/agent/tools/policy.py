"""Tool execution policy definitions."""

from enum import Enum


class ToolPolicy(Enum):
    """Defines the execution policy for a tool."""

    ALLOW = "allow"  # Execute without confirmation
    REQUIRE_CONFIRMATION = "require_confirmation"  # Ask user for confirmation
    DENY = "deny"  # Always deny execution
