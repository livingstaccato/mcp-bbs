"""Tests for learning engine."""

import json

import pytest

from bbsbot.learning.engine import LearningEngine, _build_menu_body, _build_prompt_body


@pytest.fixture
def temp_knowledge_dir(tmp_path):
    """Create temporary knowledge directory."""
    return tmp_path / ".bbs-knowledge"


@pytest.fixture
def engine(temp_knowledge_dir):
    """Create learning engine instance."""
    return LearningEngine(knowledge_root=temp_knowledge_dir, namespace="tw2002")


@pytest.fixture
def sample_snapshot():
    """Create sample screen snapshot."""
    return {
        "screen": "Command [?=Help]?",
        "screen_hash": "abc123",
        "captured_at": 1234567890.0,
        "cursor": {"x": 0, "y": 0},
        "cols": 80,
        "rows": 25,
    }


class TestLearningEngineInitialization:
    """Test learning engine initialization."""

    def test_initialization(self, temp_knowledge_dir):
        """Test basic initialization."""
        engine = LearningEngine(knowledge_root=temp_knowledge_dir, namespace="tw2002")

        assert engine._knowledge_root == temp_knowledge_dir
        assert engine._namespace == "tw2002"
        assert engine._enabled is False
        assert engine._auto_discover is False
        assert engine._buffer_manager is not None
        assert engine._screen_saver is not None

    def test_initialization_no_namespace(self, temp_knowledge_dir):
        """Test initialization without namespace."""
        engine = LearningEngine(knowledge_root=temp_knowledge_dir, namespace=None)

        assert engine._namespace is None
        assert engine._prompt_detector is not None  # Still creates detector

    def test_prompt_detector_created(self, engine):
        """Test that prompt detector is created on init."""
        assert engine._prompt_detector is not None


class TestLearningEngineConfiguration:
    """Test learning engine configuration methods."""

    def test_enabled_property(self, engine):
        """Test enabled property."""
        assert engine.enabled is False

        engine.set_enabled(True)
        assert engine.enabled is True

    def test_set_enabled(self, engine):
        """Test enabling/disabling learning."""
        engine.set_enabled(True)
        assert engine._enabled is True

        engine.set_enabled(False)
        assert engine._enabled is False

    def test_set_auto_discover(self, engine):
        """Test enabling/disabling auto-discovery."""
        engine.set_auto_discover(True)
        assert engine._auto_discover is True

        engine.set_auto_discover(False)
        assert engine._auto_discover is False

    def test_set_namespace(self, engine):
        """Test changing namespace."""
        engine.set_namespace("other_game")
        assert engine._namespace == "other_game"

    def test_set_namespace_updates_screen_saver(self, engine):
        """Test that namespace change updates screen saver."""
        engine.set_namespace("new_game")
        # Screen saver namespace should be updated
        assert engine._screen_saver._namespace == "new_game"

    def test_set_prompt_rules(self, engine):
        """Test setting prompt rules."""
        rules = [
            {"prompt_id": "test_prompt", "regex": r"Test prompt\?"},
        ]
        engine.set_prompt_rules(rules)
        assert engine._prompt_rules == rules

    def test_set_menu_rules(self, engine):
        """Test setting menu rules."""
        rules = [
            {"menu_id": "test_menu", "regex": r"Main Menu"},
        ]
        engine.set_menu_rules(rules)
        assert engine._menu_rules == rules

    def test_set_screen_saving(self, engine):
        """Test enabling/disabling screen saving."""
        engine.set_screen_saving(False)
        assert engine._screen_saver._enabled is False

        engine.set_screen_saving(True)
        assert engine._screen_saver._enabled is True


class TestGetBaseDir:
    """Test get_base_dir method."""

    def test_get_base_dir_with_namespace(self, temp_knowledge_dir):
        """Test base directory with namespace."""
        engine = LearningEngine(knowledge_root=temp_knowledge_dir, namespace="tw2002")

        base_dir = engine.get_base_dir()

        assert base_dir == temp_knowledge_dir / "games" / "tw2002" / "docs"

    def test_get_base_dir_without_namespace(self, temp_knowledge_dir):
        """Test base directory without namespace."""
        engine = LearningEngine(knowledge_root=temp_knowledge_dir, namespace=None)

        base_dir = engine.get_base_dir()

        assert base_dir == temp_knowledge_dir / "shared" / "bbs"


class TestScreenSaverStatus:
    """Test screen saver status method."""

    def test_get_screen_saver_status(self, engine):
        """Test getting screen saver status."""
        status = engine.get_screen_saver_status()

        assert "enabled" in status
        assert "screens_dir" in status
        assert "saved_count" in status
        assert "namespace" in status
        assert status["enabled"] is True
        assert status["namespace"] == "tw2002"


class TestProcessScreen:
    """Test process_screen method."""

    @pytest.mark.asyncio
    async def test_process_screen_basic(self, engine, sample_snapshot):
        """Test basic screen processing."""
        result = await engine.process_screen(sample_snapshot)

        # Should return None if no prompt detected (no patterns loaded)
        # But screen should still be buffered
        assert engine._buffer_manager._buffers  # Buffer should have entry

    @pytest.mark.asyncio
    async def test_process_screen_buffers_always(self, engine, sample_snapshot):
        """Test that screens are buffered even when learning disabled."""
        engine.set_enabled(False)

        await engine.process_screen(sample_snapshot)

        # Screen should still be buffered
        assert len(engine._buffer_manager._buffers) > 0

    @pytest.mark.asyncio
    async def test_process_screen_saves_to_disk(self, engine, sample_snapshot):
        """Test that screens are saved to disk."""
        engine.set_screen_saving(True)

        await engine.process_screen(sample_snapshot)

        # Screen should be saved
        assert engine._screen_saver.get_saved_count() > 0

    @pytest.mark.asyncio
    async def test_process_screen_learning_disabled(self, engine, sample_snapshot):
        """Test that learning rules don't run when disabled."""
        engine.set_enabled(False)
        engine.set_prompt_rules([{"prompt_id": "test", "regex": r"Command"}])

        await engine.process_screen(sample_snapshot)

        # _seen should be empty because learning is disabled
        assert len(engine._seen) == 0


class TestPromptRules:
    """Test prompt rule processing."""

    @pytest.mark.asyncio
    async def test_apply_prompt_rules_match(self, engine, temp_knowledge_dir):
        """Test prompt rule matching."""
        engine.set_enabled(True)
        engine.set_prompt_rules(
            [
                {
                    "prompt_id": "command_prompt",
                    "regex": r"Command.*\?",
                    "input_type": "line",
                    "notes": "Main command prompt",
                }
            ]
        )

        snapshot = {
            "screen": "Command [?=Help]?",
            "screen_hash": "hash1",
            "captured_at": 1234567890.0,
        }

        await engine.process_screen(snapshot)

        # Check that prompt was seen
        assert ("prompt:command_prompt", "hash1") in engine._seen

    @pytest.mark.asyncio
    async def test_apply_prompt_rules_no_duplicate(self, engine):
        """Test that prompt rules don't trigger twice for same screen hash."""
        engine.set_enabled(True)
        engine.set_prompt_rules([{"prompt_id": "command", "regex": r"Command"}])

        snapshot = {"screen": "Command [?=Help]?", "screen_hash": "hash1"}

        await engine.process_screen(snapshot)
        await engine.process_screen(snapshot)

        # Should only be seen once
        assert len([k for k in engine._seen if k[0] == "prompt:command"]) == 1


class TestMenuRules:
    """Test menu rule processing."""

    @pytest.mark.asyncio
    async def test_apply_menu_rules_match(self, engine):
        """Test menu rule matching."""
        engine.set_enabled(True)
        engine.set_menu_rules(
            [
                {
                    "menu_id": "main_menu",
                    "regex": r"Main Menu",
                    "title": "Main Menu",
                    "options_md": "| A | Option A |",
                }
            ]
        )

        snapshot = {
            "screen": "Main Menu\nA) Option A\nB) Option B",
            "screen_hash": "hash1",
        }

        await engine.process_screen(snapshot)

        # Check that menu was seen
        assert ("menu:main_menu", "hash1") in engine._seen


class TestAutoDiscover:
    """Test auto-discovery functionality."""

    @pytest.mark.asyncio
    async def test_auto_discover_disabled_by_default(self, engine):
        """Test that auto-discover is disabled by default."""
        engine.set_enabled(True)

        snapshot = {
            "screen": "Main Menu\nA) Option A\nB) Option B",
            "screen_hash": "hash1",
        }

        await engine.process_screen(snapshot)

        # Should not auto-discover when disabled
        assert not any(k[0].startswith("menu:auto") for k in engine._seen)

    @pytest.mark.asyncio
    async def test_auto_discover_when_enabled(self, engine):
        """Test auto-discovery when enabled."""
        engine.set_enabled(True)
        engine.set_auto_discover(True)

        snapshot = {
            "screen": "Main Menu\nA) Option A\nB) Option B\nEnter choice:",
            "screen_hash": "hash1",
        }

        await engine.process_screen(snapshot)

        # Should auto-discover menu
        assert any(k[0].startswith("menu:auto") for k in engine._seen)


class TestPromptDetection:
    """Test prompt detection integration."""

    @pytest.mark.asyncio
    async def test_prompt_detection_with_patterns(self, engine, temp_knowledge_dir):
        """Test prompt detection when patterns are loaded."""
        # Create rules file
        rules_dir = temp_knowledge_dir / "games" / "tw2002"
        rules_dir.mkdir(parents=True, exist_ok=True)
        rules_file = rules_dir / "rules.json"

        rules_data = {
            "game": "tw2002",
            "version": "1.0",
            "prompts": [
                {
                    "prompt_id": "prompt.command",
                    "regex": r"Command.*\?",
                    "input_type": "line",
                }
            ],
        }
        rules_file.write_text(json.dumps(rules_data))

        # Reload engine to pick up rules
        engine = LearningEngine(knowledge_root=temp_knowledge_dir, namespace="tw2002")

        snapshot = {
            "screen": "Command [?=Help]?",
            "screen_hash": "hash1",
            "captured_at": 1234567890.0,
        }

        result = await engine.process_screen(snapshot)

        # Should detect prompt
        assert result is not None
        assert result.prompt_id == "prompt.command"
        assert result.input_type == "line"


class TestKVExtraction:
    """Test K/V extraction during prompt detection."""

    @pytest.mark.asyncio
    async def test_kv_extraction_on_prompt_match(self, engine, temp_knowledge_dir):
        """Test that K/V data is extracted when configured."""
        # Create rules with K/V extraction
        rules_dir = temp_knowledge_dir / "games" / "tw2002"
        rules_dir.mkdir(parents=True, exist_ok=True)
        rules_file = rules_dir / "rules.json"

        rules_data = {
            "game": "tw2002",
            "version": "1.0",
            "prompts": [
                {
                    "prompt_id": "prompt.sector",
                    "regex": r"Sector\s*:\s*\d+",
                    "input_type": "line",
                    "kv_extract": {
                        "field": "sector",
                        "type": "int",
                        "regex": r"Sector\s*:\s*(\d+)",
                    },
                }
            ],
        }
        rules_file.write_text(json.dumps(rules_data))

        # Reload engine
        engine = LearningEngine(knowledge_root=temp_knowledge_dir, namespace="tw2002")

        snapshot = {
            "screen": "Sector : 42\nCommand [?=Help]?",
            "screen_hash": "hash1",
            "captured_at": 1234567890.0,
        }

        result = await engine.process_screen(snapshot)

        # Should extract K/V data
        assert result is not None
        assert result.kv_data is not None
        assert result.kv_data.get("sector") == 42


class TestBuildHelpers:
    """Test helper functions for building markdown."""

    def test_build_prompt_body(self):
        """Test building prompt catalog entry."""
        rule = {
            "input_type": "line",
            "example_input": "W 42",
            "notes": "Warp to sector",
            "log_refs": "session_001.log",
        }

        body = _build_prompt_body("test_prompt", "Test screen", r"Test\?", rule)

        assert "### Prompt: test_prompt" in body
        assert "Test screen" in body
        assert r"Test\?" in body
        assert "Input Type: line" in body
        assert "Example Input: W 42" in body

    def test_build_menu_body(self):
        """Test building menu map entry."""
        rule = {
            "title": "Main Menu",
            "entry_prompt": "Select option:",
            "exit_keys": "X",
            "options_md": "| A | Option A |",
            "notes": "Test menu",
            "log_refs": "session_001.log",
        }

        body = _build_menu_body("test_menu", "Test screen", rule)

        assert "### Menu: test_menu" in body
        assert "Title (Observed): Main Menu" in body
        assert "Exit Keys: X" in body
        assert "| A | Option A |" in body


class TestRuleLoading:
    """Test rule loading from files."""

    def test_load_from_repo_games_root(self, temp_knowledge_dir, monkeypatch):
        """Test loading rules from repo games root."""
        # Create repo-style rules
        repo_root = temp_knowledge_dir / "repo_games"
        repo_root.mkdir(parents=True)
        rules_dir = repo_root / "tw2002"
        rules_dir.mkdir(parents=True)
        rules_file = rules_dir / "rules.json"

        rules_data = {
            "game": "tw2002",
            "version": "1.0",
            "prompts": [{"prompt_id": "test", "regex": r"Test", "input_type": "line"}],
        }
        rules_file.write_text(json.dumps(rules_data))

        # Mock find_repo_games_root
        def mock_find_repo_games_root():
            return repo_root

        monkeypatch.setattr("bbsbot.learning.engine.find_repo_games_root", mock_find_repo_games_root)

        # Create engine - should load from repo
        engine = LearningEngine(knowledge_root=temp_knowledge_dir, namespace="tw2002")

        assert engine._prompt_detector is not None
        # Verify pattern was loaded
        assert len(engine._prompt_detector._patterns) > 0

    def test_load_from_knowledge_root(self, temp_knowledge_dir):
        """Test loading rules from knowledge root."""
        rules_dir = temp_knowledge_dir / "games" / "tw2002"
        rules_dir.mkdir(parents=True)
        rules_file = rules_dir / "rules.json"

        rules_data = {
            "game": "tw2002",
            "version": "1.0",
            "prompts": [{"prompt_id": "test", "regex": r"Test", "input_type": "line"}],
        }
        rules_file.write_text(json.dumps(rules_data))

        engine = LearningEngine(knowledge_root=temp_knowledge_dir, namespace="tw2002")

        assert engine._prompt_detector is not None
        assert len(engine._prompt_detector._patterns) > 0

    def test_load_no_rules_creates_empty_detector(self, temp_knowledge_dir):
        """Test that engine creates empty detector when no rules found."""
        engine = LearningEngine(knowledge_root=temp_knowledge_dir, namespace="tw2002")

        assert engine._prompt_detector is not None
        assert len(engine._prompt_detector._patterns) == 0

    def test_load_invalid_json_creates_empty_detector(self, temp_knowledge_dir):
        """Test that invalid JSON creates empty detector."""
        rules_dir = temp_knowledge_dir / "games" / "tw2002"
        rules_dir.mkdir(parents=True)
        rules_file = rules_dir / "rules.json"
        rules_file.write_text("{ invalid json }")

        engine = LearningEngine(knowledge_root=temp_knowledge_dir, namespace="tw2002")

        assert engine._prompt_detector is not None
        assert len(engine._prompt_detector._patterns) == 0


class TestIdleDetection:
    """Test idle state detection."""

    @pytest.mark.asyncio
    async def test_idle_detection_in_result(self, engine, sample_snapshot):
        """Test that idle state is included in detection result."""
        # Process multiple screens to build buffer
        for i in range(3):
            snapshot = {
                "screen": "Same screen",
                "screen_hash": f"hash{i}",
                "captured_at": 1234567890.0 + i,
            }
            await engine.process_screen(snapshot)

        # Result should include is_idle status
        # (Will be False without actual time delay)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
