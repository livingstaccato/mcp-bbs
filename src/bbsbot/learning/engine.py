"""Learning engine for auto-discovery and rule-based learning."""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any

from bbsbot.paths import find_repo_games_root
from bbsbot.learning.buffer import BufferManager
from bbsbot.learning.detector import PromptDetection, PromptDetector
from bbsbot.learning.discovery import discover_menu
from bbsbot.learning.extractor import extract_kv
from bbsbot.learning.knowledge import append_md
from bbsbot.learning.rules import RuleLoadResult, RuleSet
from bbsbot.learning.screen_saver import ScreenSaver

if TYPE_CHECKING:
    from pathlib import Path


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

        # NEW: Always-on screen buffering and prompt detection
        self._buffer_manager = BufferManager(max_size=50)
        self._prompt_detector: PromptDetector | None = None
        self._idle_threshold_seconds = 2.0

        # NEW: Screen saving to disk
        self._screen_saver = ScreenSaver(
            base_dir=knowledge_root, namespace=namespace, enabled=True
        )

        # Auto-load prompt patterns from JSON
        self._load_prompt_patterns()

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
        # Update screen saver namespace
        if self._screen_saver:
            self._screen_saver.set_namespace(namespace)

    def set_screen_saving(self, enabled: bool) -> None:
        """Enable or disable screen saving to disk."""
        if self._screen_saver:
            self._screen_saver.set_enabled(enabled)

    def get_screen_saver_status(self) -> dict[str, Any]:
        """Get screen saver status.

        Returns:
            Dictionary with screen saver status
        """
        if not self._screen_saver:
            return {"enabled": False}

        return {
            "enabled": self._screen_saver._enabled,
            "screens_dir": str(self._screen_saver.get_screens_dir()),
            "saved_count": self._screen_saver.get_saved_count(),
            "namespace": self._screen_saver._namespace,
        }

    def get_base_dir(self) -> Path:
        """Get base directory for knowledge files.

        Returns:
            Path to shared or game-specific knowledge directory
        """
        if not self._namespace:
            return self._knowledge_root / "shared" / "bbs"
        return self._knowledge_root / "games" / self._namespace / "docs"

    def _load_prompt_patterns(self) -> None:
        """Load prompt patterns from JSON file (auto-called on init).

        Patterns are loaded from:
        - .bbs-knowledge/games/{namespace}/rules.json (if namespace set)
        - .bbs-knowledge/games/{namespace}/prompts.json (legacy)
        - Falls back to empty detector if file doesn't exist
        """
        result = self._load_rules_or_patterns()
        patterns = result.patterns

        # Create detector (empty if no patterns found)
        self._prompt_detector = PromptDetector(patterns)

    def _load_rules_or_patterns(self) -> RuleLoadResult:
        if not self._namespace:
            return RuleLoadResult(source="none", patterns=[], metadata={})

        # Look for a repo-local rules override relative to the knowledge root.
        # This keeps tests isolated (tmp dirs are not git repos) and avoids
        # accidentally pulling in repo rules based on the current working dir.
        # Be tolerant of older call sites / tests that monkeypatch this helper
        # with a 0-arg function.
        try:
            repo_games_root = find_repo_games_root(self._knowledge_root)
        except TypeError:
            repo_games_root = find_repo_games_root()
        if repo_games_root:
            repo_rules = repo_games_root / self._namespace / "rules.json"
            if repo_rules.exists():
                try:
                    rules = RuleSet.from_json_file(repo_rules)
                    return RuleLoadResult(
                        source=str(repo_rules),
                        patterns=rules.to_prompt_patterns(),
                        metadata={"game": rules.game, "version": rules.version, **rules.metadata},
                    )
                except (json.JSONDecodeError, OSError, ValueError):
                    # Legacy rules.json support (minimal prompt list).
                    try:
                        data = json.loads(repo_rules.read_text())
                        legacy_patterns: list[dict[str, Any]] = []
                        for prompt in data.get("prompts", []):
                            prompt_id = prompt.get("prompt_id")
                            regex = prompt.get("regex")
                            if not prompt_id or not regex:
                                continue
                            input_type = prompt.get("input_type", "multi_key")
                            legacy_patterns.append(
                                {
                                    "id": prompt_id,
                                    "regex": regex,
                                    "input_type": input_type,
                                    "expect_cursor_at_end": True,
                                    # Legacy rules.json files may include kv_extract
                                    # directly; the detector can carry it through.
                                    "kv_extract": prompt.get("kv_extract"),
                                }
                            )
                        if legacy_patterns:
                            return RuleLoadResult(
                                source=str(repo_rules),
                                patterns=legacy_patterns,
                                metadata=data.get("metadata", {}),
                            )
                    except Exception:
                        pass
                    return RuleLoadResult(source=str(repo_rules), patterns=[], metadata={})

            repo_prompts = repo_games_root / self._namespace / "prompts.json"
            if repo_prompts.exists():
                try:
                    data = json.loads(repo_prompts.read_text())
                    return RuleLoadResult(
                        source=str(repo_prompts),
                        patterns=data.get("prompts", []),
                        metadata=data.get("metadata", {}),
                    )
                except (json.JSONDecodeError, OSError):
                    return RuleLoadResult(source=str(repo_prompts), patterns=[], metadata={})

        rules_file = self._knowledge_root / "games" / self._namespace / "rules.json"
        if rules_file.exists():
            try:
                rules = RuleSet.from_json_file(rules_file)
                return RuleLoadResult(
                    source=str(rules_file),
                    patterns=rules.to_prompt_patterns(),
                    metadata={"game": rules.game, "version": rules.version, **rules.metadata},
                )
            except (json.JSONDecodeError, OSError, ValueError):
                # Legacy rules.json support (minimal prompt list).
                try:
                    data = json.loads(rules_file.read_text())
                    legacy_patterns: list[dict[str, Any]] = []
                    for prompt in data.get("prompts", []):
                        prompt_id = prompt.get("prompt_id")
                        regex = prompt.get("regex")
                        if not prompt_id or not regex:
                            continue
                        input_type = prompt.get("input_type", "multi_key")
                        legacy_patterns.append(
                            {
                                "id": prompt_id,
                                "regex": regex,
                                "input_type": input_type,
                                "expect_cursor_at_end": True,
                                "kv_extract": prompt.get("kv_extract"),
                            }
                        )
                    if legacy_patterns:
                        return RuleLoadResult(
                            source=str(rules_file),
                            patterns=legacy_patterns,
                            metadata=data.get("metadata", {}),
                        )
                except Exception:
                    pass
                return RuleLoadResult(source=str(rules_file), patterns=[], metadata={})

        patterns_file = self._knowledge_root / "games" / self._namespace / "prompts.json"
        if patterns_file.exists():
            try:
                data = json.loads(patterns_file.read_text())
                return RuleLoadResult(
                    source=str(patterns_file),
                    patterns=data.get("prompts", []),
                    metadata=data.get("metadata", {}),
                )
            except (json.JSONDecodeError, OSError):
                return RuleLoadResult(source=str(patterns_file), patterns=[], metadata={})

        return RuleLoadResult(source="none", patterns=[], metadata={})

    async def process_screen(self, snapshot: dict[str, Any]) -> PromptDetection | None:
        """Process screen snapshot with enhanced detection.

        Always buffers screens and detects prompts regardless of learning state.
        Legacy auto-discovery runs only if enabled.

        Args:
            snapshot: Screen snapshot dictionary with timing metadata

        Returns:
            PromptDetection if a prompt is detected, None otherwise
        """
        # Always buffer screens (even if learning disabled)
        buffer = self._buffer_manager.add_screen(snapshot)

        # Detect idle state
        is_idle = self._buffer_manager.detect_idle_state(self._idle_threshold_seconds)

        # Detect prompt (always try)
        prompt_match = self._prompt_detector.detect_prompt(snapshot) if self._prompt_detector else None
        if prompt_match:
            buffer.matched_prompt_id = prompt_match.prompt_id

        # Legacy learning (only if enabled)
        if self._enabled:
            screen = snapshot.get("screen", "")
            screen_hash = snapshot.get("screen_hash", "")

            if screen and screen_hash:
                async with self._lock:
                    await self._apply_prompt_rules(screen, screen_hash)
                    await self._apply_menu_rules(screen, screen_hash)

                    if self._auto_discover:
                        await self._apply_auto_discover(screen, screen_hash)

        # Return detection result
        if prompt_match:
            # Extract K/V data if configured
            kv_data = None
            if prompt_match.kv_extract:
                screen = snapshot.get("screen", "")
                kv_data = extract_kv(screen, prompt_match.kv_extract)

            # Save screen to disk (with prompt ID)
            self._screen_saver.save_screen(snapshot, prompt_id=prompt_match.prompt_id)

            return PromptDetection(
                prompt_id=prompt_match.prompt_id,
                input_type=prompt_match.input_type,
                is_idle=is_idle,
                buffer=buffer,
                kv_data=kv_data,
            )

        # Save screen even if no prompt detected (deduplication prevents duplicates)
        self._screen_saver.save_screen(snapshot)

        return None

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
