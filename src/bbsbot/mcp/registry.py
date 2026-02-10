"""MCP tool registry for game-specific tools.

Allows games to register their own MCP tools with custom prefixes
(e.g., tw2002_, tedit_) while maintaining the core bbs_ tools.
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class MCPToolRegistry:
    """Registry for game-specific MCP tools.

    Enables games to register tools with custom prefixes that get
    automatically added to the MCP server on startup.
    """

    def __init__(self, prefix: str):
        """Initialize registry for a game.

        Args:
            prefix: Tool prefix (e.g., 'tw2002', 'tedit')
        """
        self.prefix = prefix
        self._tools: dict[str, Callable] = {}

    def tool(self, name: str | None = None):
        """Decorator to register a tool function.

        Args:
            name: Optional tool name (defaults to function name)

        Returns:
            Decorator function

        Example:
            @registry.tool()
            async def set_goal(goal: str) -> dict:
                '''Set current bot goal.'''
                ...

            # Creates tool: tw2002_set_goal
        """

        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            full_name = f"{self.prefix}_{tool_name}"
            self._tools[full_name] = func
            logger.debug(f"mcp_tool_registered: {full_name}")
            return func

        return decorator

    def get_tools(self) -> dict[str, Callable]:
        """Get all registered tools.

        Returns:
            Dictionary of tool_name -> function
        """
        return self._tools.copy()

    def register_tool(self, name: str, func: Callable) -> None:
        """Manually register a tool.

        Args:
            name: Tool name (without prefix)
            func: Tool function
        """
        full_name = f"{self.prefix}_{name}"
        self._tools[full_name] = func
        logger.debug(f"mcp_tool_registered: {full_name}")


class MCPRegistryManager:
    """Manages multiple game registries.

    Centralizes all game-specific tool registries for easy
    integration with the main MCP server.
    """

    def __init__(self):
        """Initialize the registry manager."""
        self._registries: dict[str, MCPToolRegistry] = {}

    def create_registry(self, prefix: str) -> MCPToolRegistry:
        """Create a new game registry.

        Args:
            prefix: Game prefix (e.g., 'tw2002')

        Returns:
            New MCPToolRegistry instance
        """
        if prefix in self._registries:
            logger.warning(f"mcp_registry_exists: {prefix}")
            return self._registries[prefix]

        registry = MCPToolRegistry(prefix)
        self._registries[prefix] = registry
        logger.info(f"mcp_registry_created: {prefix}")
        return registry

    def get_registry(self, prefix: str) -> MCPToolRegistry | None:
        """Get a game registry by prefix.

        Args:
            prefix: Game prefix

        Returns:
            Registry or None if not found
        """
        return self._registries.get(prefix)

    def get_all_tools(self) -> dict[str, Callable]:
        """Get all tools from all registries.

        Returns:
            Dictionary of all registered tools
        """
        all_tools = {}
        for registry in self._registries.values():
            all_tools.update(registry.get_tools())
        return all_tools

    def list_registries(self) -> list[str]:
        """List all registered game prefixes.

        Returns:
            List of prefix strings
        """
        return list(self._registries.keys())


# Global registry manager instance
_manager = MCPRegistryManager()
_builtins_loaded = False


def _ensure_builtin_registries_loaded() -> None:
    """Load built-in game MCP registries once.

    This keeps registry discovery deterministic even if callers only import
    `bbsbot.mcp.registry` (without importing server/tool modules first).
    """
    global _builtins_loaded
    if _builtins_loaded:
        return

    # Import side-effect modules that call create_registry(...).
    importlib.import_module("bbsbot.games.tw2002.mcp_tools")
    _builtins_loaded = True


def get_manager() -> MCPRegistryManager:
    """Get the global registry manager.

    Returns:
        MCPRegistryManager instance
    """
    _ensure_builtin_registries_loaded()
    return _manager


def create_registry(prefix: str) -> MCPToolRegistry:
    """Create a new game registry (convenience function).

    Args:
        prefix: Game prefix

    Returns:
        New registry
    """
    return _manager.create_registry(prefix)
