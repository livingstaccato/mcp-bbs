# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Learning engine for auto-discovery and rule-based learning."""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any

from bbsbot.learning.buffer import BufferManager
from bbsbot.learning.detector import PromptDetection, PromptDetector, PromptMatch
from bbsbot.learning.discovery import discover_menu
from bbsbot.learning.extractor import extract_kv
from bbsbot.learning.knowledge import append_md
from bbsbot.learning.rules import RuleLoadResult, RuleSet
from bbsbot.learning.screen_saver import ScreenSaver
from bbsbot.paths import default_knowledge_root, find_repo_games_root

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
        # Cache last prompt match for the current screen fingerprint.
        # PromptWaiter may read the same stable screen repeatedly while waiting for idle.
        self._last_prompt_fingerprint: str = ""
        self._last_prompt_match: PromptMatch | None = None

        # NEW: Screen saving to disk
        self._screen_saver = ScreenSaver(base_dir=knowledge_root, namespace=namespace, enabled=True)

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
        from bbsbot.logging import get_logger

        logger = get_logger(__name__)

        logger.info(f"[PATTERN LOAD] Loading patterns for namespace: {self._namespace}")
        logger.info(f"[PATTERN LOAD] Knowledge root: {self._knowledge_root}")

        result = self._load_rules_or_patterns()
        patterns = result.patterns

        logger.info(f"[PATTERN LOAD] Loaded {len(patterns)} patterns from {result.source}")
        if result.metadata:
            logger.info(f"[PATTERN LOAD] Metadata: {result.metadata}")

        if len(patterns) == 0:
            logger.error(
                f"[PATTERN LOAD] ⚠️ ⚠️ ⚠️  NO PATTERNS LOADED! ⚠️ ⚠️ ⚠️\n"
                f"  Namespace: {self._namespace}\n"
                f"  Source: {result.source}\n"
                f"  This means prompt detection will NOT work!"
            )

        # Create detector (empty if no patterns found)
        self._prompt_detector = PromptDetector(patterns)

    def _load_rules_or_patterns(self) -> RuleLoadResult:
        from bbsbot.logging import get_logger

        logger = get_logger(__name__)

        if not self._namespace:
            logger.warning("[RULES LOAD] No namespace set, cannot load patterns")
            return RuleLoadResult(source="none", patterns=[], metadata={})

        logger.debug(f"[RULES LOAD] Namespace: {self._namespace}")

        # Prefer explicit knowledge-root rules for determinism in tests and custom deployments.
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

        # Resolve both paths for accurate comparison
        is_default_knowledge_root = self._knowledge_root.resolve() == default_knowledge_root().resolve()
        logger.debug(f"[RULES LOAD] knowledge_root: {self._knowledge_root.resolve()}")
        logger.debug(f"[RULES LOAD] default_knowledge_root: {default_knowledge_root().resolve()}")
        logger.debug(f"[RULES LOAD] is_default: {is_default_knowledge_root}")

        # Look for a repo-local rules override relative to the knowledge root.
        # For tests: knowledge_root is a temp dir (may or may not have .git)
        # For production: knowledge_root is user data dir, NOT in git repo
        # Strategy:
        #   1. Try finding git repo from knowledge_root (tests with .git)
        #   2. Check knowledge_root/games directly (tests without .git)
        #   3. Fallback to finding git repo from cwd (production)
        repo_games_root = None
        try:
            repo_games_root = find_repo_games_root(self._knowledge_root, include_package_fallback=False)
            logger.debug(f"[RULES LOAD] Searched from knowledge_root, found: {repo_games_root}")
        except TypeError:
            # Backwards compatibility for monkeypatched callers
            repo_games_root = find_repo_games_root()
            logger.debug(f"[RULES LOAD] Fallback (TypeError), found: {repo_games_root}")
        except Exception as e:
            logger.error(f"[RULES LOAD] Error finding repo games root: {e}")
            repo_games_root = None

        # If still nothing, try searching from current working directory (production case ONLY)
        # Only do this if knowledge_root is the default production directory, not a test temp dir
        if repo_games_root is None and is_default_knowledge_root:
            logger.debug("[RULES LOAD] Using default knowledge_root in production, trying cwd")
            try:
                repo_games_root = find_repo_games_root()
                logger.debug(f"[RULES LOAD] Searched from cwd, found: {repo_games_root}")
            except Exception as e:
                logger.error(f"[RULES LOAD] Error finding repo games root from cwd: {e}")
                repo_games_root = None
        elif repo_games_root is None:
            logger.debug("[RULES LOAD] Custom knowledge_root (test mode), not falling back to cwd/package")

        if repo_games_root:
            repo_rules = repo_games_root / self._namespace / "rules.json"
            logger.info(f"[RULES LOAD] Checking for rules.json at: {repo_rules}")
            logger.info(f"[RULES LOAD] File exists: {repo_rules.exists()}")

            if repo_rules.exists():
                logger.info(f"[RULES LOAD] Attempting to load RuleSet from {repo_rules}")
                try:
                    rules = RuleSet.from_json_file(repo_rules)
                    patterns = rules.to_prompt_patterns()
                    logger.info(f"[RULES LOAD] ✓ Successfully loaded {len(patterns)} patterns from RuleSet")
                    return RuleLoadResult(
                        source=str(repo_rules),
                        patterns=patterns,
                        metadata={"game": rules.game, "version": rules.version, **rules.metadata},
                    )
                except (json.JSONDecodeError, OSError, ValueError) as e:
                    logger.warning(
                        f"[RULES LOAD] RuleSet loading failed ({type(e).__name__}: {e}), trying legacy format"
                    )
                    # Legacy rules.json support (minimal prompt list).
                    try:
                        data = json.loads(repo_rules.read_text())
                        logger.debug("[RULES LOAD] Parsed JSON, checking for legacy 'prompts' key")
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
                            logger.info(f"[RULES LOAD] ✓ Loaded {len(legacy_patterns)} patterns from legacy format")
                            return RuleLoadResult(
                                source=str(repo_rules),
                                patterns=legacy_patterns,
                                metadata=data.get("metadata", {}),
                            )
                        else:
                            logger.warning("[RULES LOAD] Legacy format parsed but no valid patterns found")
                    except Exception as e2:
                        logger.error(f"[RULES LOAD] Legacy format parsing also failed: {type(e2).__name__}: {e2}")
                        pass
                    logger.error(f"[RULES LOAD] ✗ Failed to load any patterns from {repo_rules}")
                    return RuleLoadResult(source=str(repo_rules), patterns=[], metadata={})
            else:
                logger.warning(f"[RULES LOAD] rules.json not found at {repo_rules}")

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

        # Detect prompt (always try, but avoid re-scanning patterns on identical snapshots)
        # Fingerprint used to avoid expensive prompt regex scans on effectively-identical frames.
        # End-state: use a normalized prompt-region fingerprint, not full-screen hash, because
        # volatile fields like `TL=00:00:01` can change every second without changing prompt semantics.
        if self._prompt_detector is not None:
            fingerprint = self._prompt_detector.prompt_fingerprint(snapshot)
        else:
            # Fallback (should be rare): keep prior behavior.
            screen_hash = snapshot.get("screen_hash", "")
            fingerprint = (
                f"{screen_hash}:"
                f"{int(bool(snapshot.get('cursor_at_end', True)))}:"
                f"{int(bool(snapshot.get('has_trailing_space', False)))}"
            )

        if fingerprint and fingerprint == self._last_prompt_fingerprint:
            prompt_match = self._last_prompt_match
        else:
            prompt_match = self._prompt_detector.detect_prompt(snapshot) if self._prompt_detector else None
            self._last_prompt_fingerprint = fingerprint
            self._last_prompt_match = prompt_match
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
