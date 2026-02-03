"""Learning engine for auto-discovery and rule-based learning."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from mcp_bbs.learning.discovery import discover_menu
from mcp_bbs.learning.knowledge import append_md


def _build_prompt_body(rule_id: str, screen: str, pattern: str, rule: dict[str, str]) -> str:
    """Build markdown body for prompt catalog entry."""
    return "\n".join(
        [
            "",
            f"### Prompt: {rule_id}",
            "",
            "- Raw Text:",
            "````",
            f"{screen}",
            "````",
            "- Regex:",
            "````",
            f"{pattern}",
            "````",
            f"- Input Type: {rule.get('input_type', '')}",
            f"- Example Input: {rule.get('example_input', '')}",
            f"- Notes: {rule.get('notes', '')}",
            "- Log References:",
            f"  - {rule.get('log_refs', '')}",
            "",
        ]
    )


def _build_menu_body(rule_id: str, screen: str, rule: dict[str, str]) -> str:
    """Build markdown body for menu map entry."""
    return "\n".join(
        [
            "",
            f"### Menu: {rule_id}",
            "",
            f"- Title (Observed): {rule.get('title', '')}",
            f"- Entry Prompt: {rule.get('entry_prompt', '')}",
            f"- Exit Keys: {rule.get('exit_keys', '')}",
            "",
            "Observed Screen:",
            "````",
            f"{screen}",
            "````",
            "",
            "Options:",
            f"{rule.get('options_md', '')}",
            "",
            "Notes:",
            f"{rule.get('notes', '')}",
            "",
            "Log References:",
            f"{rule.get('log_refs', '')}",
            "",
        ]
    )


class LearningEngine:
    """Learning engine for BBS knowledge discovery."""

    def __init__(self, knowledge_root: Path, namespace: str | None = None) -> None:
        """Initialize learning engine.

        Args:
            knowledge_root: Root directory for knowledge base
            namespace: Optional namespace for game-specific knowledge
        """
        self._knowledge_root = knowledge_root
        self._namespace = namespace
        self._enabled = False
        self._auto_discover = False
        self._prompt_rules: list[dict[str, str]] = []
        self._menu_rules: list[dict[str, str]] = []
        self._seen: set[tuple[str, str]] = set()
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        """Check if learning is enabled."""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable learning."""
        self._enabled = enabled

    def set_auto_discover(self, enabled: bool) -> None:
        """Enable or disable auto-discovery."""
        self._auto_discover = enabled

    def set_prompt_rules(self, rules: list[dict[str, str]]) -> None:
        """Set prompt matching rules."""
        self._prompt_rules = rules

    def set_menu_rules(self, rules: list[dict[str, str]]) -> None:
        """Set menu matching rules."""
        self._menu_rules = rules

    def set_namespace(self, namespace: str | None) -> None:
        """Set namespace for knowledge base."""
        self._namespace = namespace

    def get_base_dir(self) -> Path:
        """Get base directory for knowledge files.

        Returns:
            Path to shared or game-specific knowledge directory
        """
        if not self._namespace:
            return self._knowledge_root / "shared" / "bbs"
        return self._knowledge_root / "games" / self._namespace / "docs"

    async def process_screen(self, snapshot: dict[str, Any]) -> None:
        """Process screen snapshot for learning.

        Args:
            snapshot: Screen snapshot dictionary
        """
        if not self._enabled:
            return

        screen = snapshot.get("screen", "")
        screen_hash = snapshot.get("screen_hash", "")

        if not screen or not screen_hash:
            return

        async with self._lock:
            await self._apply_prompt_rules(screen, screen_hash)
            await self._apply_menu_rules(screen, screen_hash)

            if self._auto_discover:
                await self._apply_auto_discover(screen, screen_hash)

    async def _apply_prompt_rules(self, screen: str, screen_hash: str) -> None:
        """Apply prompt matching rules.

        Args:
            screen: Screen text
            screen_hash: Screen hash for deduplication
        """
        base_dir = self.get_base_dir()

        for rule in self._prompt_rules:
            rule_id = rule.get("prompt_id", "prompt")
            key = (f"prompt:{rule_id}", screen_hash)

            if key in self._seen:
                continue

            pattern = rule.get("regex", "")
            if pattern and re.search(pattern, screen, re.MULTILINE):
                body = _build_prompt_body(rule_id, screen, pattern, rule)
                await append_md(
                    base_dir / "prompt-catalog.md",
                    "Prompt Catalog (Shared)",
                    body,
                    self._knowledge_root,
                )
                self._seen.add(key)

    async def _apply_menu_rules(self, screen: str, screen_hash: str) -> None:
        """Apply menu matching rules.

        Args:
            screen: Screen text
            screen_hash: Screen hash for deduplication
        """
        base_dir = self.get_base_dir()

        for rule in self._menu_rules:
            rule_id = rule.get("menu_id", "menu")
            key = (f"menu:{rule_id}", screen_hash)

            if key in self._seen:
                continue

            pattern = rule.get("regex", "")
            if pattern and re.search(pattern, screen, re.MULTILINE):
                body = _build_menu_body(rule_id, screen, rule)
                await append_md(
                    base_dir / "menu-map.md",
                    "Menu Map (Shared)",
                    body,
                    self._knowledge_root,
                )
                self._seen.add(key)

    async def _apply_auto_discover(self, screen: str, screen_hash: str) -> None:
        """Apply auto-discovery to screen.

        Args:
            screen: Screen text
            screen_hash: Screen hash for deduplication
        """
        key = ("menu:auto", screen_hash)
        if key in self._seen:
            return

        discovered = discover_menu(screen)
        if not discovered["options"] and not discovered["prompt"]:
            return

        # Build options table
        options_md = ["| Key | Label |", "| --- | --- |"]
        for item in discovered["options"]:
            options_md.append(f"| {item['key']} | {item['label']} |")

        rule = {
            "menu_id": f"auto:{screen_hash[:8]}",
            "title": discovered["title"],
            "entry_prompt": discovered["prompt"],
            "exit_keys": "",
            "options_md": "\n".join(options_md),
            "notes": "Auto-discovered menu options.",
            "log_refs": "",
        }

        base_dir = self.get_base_dir()
        body = _build_menu_body(rule["menu_id"], screen, rule)
        await append_md(
            base_dir / "menu-map.md",
            "Menu Map (Shared)",
            body,
            self._knowledge_root,
        )
        self._seen.add(key)
