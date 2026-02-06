"""Tests for themed name generator."""

import pytest

from bbsbot.games.tw2002.name_generator import NameGenerator


class TestNameGenerator:
    """Test themed name generation."""

    def test_generate_simple_character_name(self):
        """Test simple 2-part character name generation."""
        gen = NameGenerator(seed=42)
        name = gen.generate_character_name(complexity="simple")

        assert isinstance(name, str)
        assert len(name) > 5  # At least prefix + suffix
        assert name not in ["bot001", "bot002"]  # Not legacy format
        assert name.isalpha()  # No spaces or numbers in simple names

    def test_generate_medium_character_name(self):
        """Test medium 3-part character name generation."""
        gen = NameGenerator(seed=42)
        name = gen.generate_character_name(complexity="medium")

        assert isinstance(name, str)
        assert len(name) > 10  # Longer than simple
        assert name.isalpha()

    def test_generate_complex_character_name(self):
        """Test complex 4-part character name generation."""
        gen = NameGenerator(seed=42)
        name = gen.generate_character_name(complexity="complex")

        assert isinstance(name, str)
        assert len(name) > 15  # Even longer
        assert name.isalpha()

    def test_generate_numbered_character_name(self):
        """Test numbered character name generation."""
        gen = NameGenerator(seed=42)
        name1 = gen.generate_character_name(complexity="numbered")
        name2 = gen.generate_character_name(complexity="numbered")

        assert isinstance(name1, str)
        assert isinstance(name2, str)
        assert name1 != name2
        # Should have numbers at the end
        assert any(c.isdigit() for c in name1)
        assert any(c.isdigit() for c in name2)

    def test_character_names_are_unique(self):
        """Test that generated character names are unique."""
        gen = NameGenerator(seed=42)
        names = [gen.generate_character_name(complexity="medium") for _ in range(100)]

        assert len(names) == len(set(names))  # All unique

    def test_generate_ship_name(self):
        """Test ship name generation."""
        gen = NameGenerator(seed=42)
        ship = gen.generate_ship_name()

        assert isinstance(ship, str)
        assert " " in ship  # Two-word format
        parts = ship.split()
        assert len(parts) == 2
        assert all(part.isalpha() for part in parts)

    def test_generate_ship_name_with_number(self):
        """Test ship name generation with roman numeral."""
        gen = NameGenerator(seed=42)
        ship = gen.generate_ship_name(add_number=True)

        assert isinstance(ship, str)
        parts = ship.split()
        assert len(parts) == 3  # Descriptor + Concept + Numeral
        # Last part should be roman numeral
        assert parts[2] in ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
                           "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]

    def test_ship_names_are_unique(self):
        """Test that generated ship names are unique."""
        gen = NameGenerator(seed=42)
        ships = [gen.generate_ship_name() for _ in range(100)]

        assert len(ships) == len(set(ships))  # All unique

    def test_mark_used_prevents_duplicates(self):
        """Test that marking names as used prevents re-generation."""
        gen = NameGenerator(seed=42)
        first_name = gen.generate_character_name()

        # Create new generator with same seed
        gen2 = NameGenerator(seed=42)
        gen2.mark_used(first_name)

        # Should generate different name even with same seed
        second_name = gen2.generate_character_name()
        assert second_name != first_name

    def test_deterministic_with_seed(self):
        """Test that same seed produces same sequence."""
        gen1 = NameGenerator(seed=123)
        gen2 = NameGenerator(seed=123)

        names1 = [gen1.generate_character_name() for _ in range(10)]
        names2 = [gen2.generate_character_name() for _ in range(10)]

        assert names1 == names2

    def test_different_seeds_produce_different_names(self):
        """Test that different seeds produce different sequences."""
        gen1 = NameGenerator(seed=123)
        gen2 = NameGenerator(seed=456)

        names1 = [gen1.generate_character_name() for _ in range(10)]
        names2 = [gen2.generate_character_name() for _ in range(10)]

        # Should be mostly different
        overlap = len(set(names1) & set(names2))
        assert overlap < 5  # Less than half overlap

    def test_get_stats(self):
        """Test statistics tracking."""
        gen = NameGenerator(seed=42)

        # Generate some names
        for _ in range(10):
            gen.generate_character_name()
        for _ in range(5):
            gen.generate_ship_name()

        stats = gen.get_stats()
        assert stats["total_generated"] == 15
        assert "estimated_remaining_simple" in stats
        assert "estimated_remaining_medium" in stats
        assert "estimated_remaining_complex" in stats

    def test_reset_clears_state(self):
        """Test reset clears generator state."""
        gen = NameGenerator(seed=42)
        name1 = gen.generate_character_name()

        gen.reset()
        name2 = gen.generate_character_name()

        # Same seed should produce same first name after reset
        assert name1 == name2

    def test_reset_with_keep_used_names(self):
        """Test reset with keep_used_names preserves collision avoidance."""
        gen = NameGenerator(seed=42)
        name1 = gen.generate_character_name()

        gen.reset(keep_used_names=True)
        name2 = gen.generate_character_name()

        # Should NOT generate the same name since we kept used names
        assert name1 != name2

    def test_fallback_on_exhaustion(self):
        """Test fallback behavior when names are exhausted."""
        gen = NameGenerator(seed=42)

        # Mark many names as used
        for i in range(2000):
            gen.mark_used(f"TestName{i}")

        # Should still be able to generate a name
        name = gen.generate_character_name(complexity="simple")
        assert isinstance(name, str)
        assert len(name) > 0

    def test_character_name_examples(self):
        """Test that generated names match expected themes."""
        gen = NameGenerator(seed=42)
        names = [gen.generate_character_name() for _ in range(20)]

        # Check for themed prefixes/suffixes
        tech_terms = ["Quantum", "Neural", "Algo", "Cyber", "Crypto", "Data"]
        trading_terms = ["Trader", "Broker", "Profit", "Capital", "Market"]

        has_tech = any(any(term in name for term in tech_terms) for name in names)
        has_trading = any(any(term in name for term in trading_terms) for name in names)

        assert has_tech or has_trading  # At least some themed elements

    def test_ship_name_examples(self):
        """Test that generated ship names match expected themes."""
        gen = NameGenerator(seed=42)
        ships = [gen.generate_ship_name() for _ in range(20)]

        # Check for themed descriptors/concepts
        descriptors = ["Swift", "Silent", "Mighty", "Nova", "Iron"]
        concepts = ["Venture", "Horizon", "Phoenix", "Storm", "Dragon"]

        has_descriptor = any(any(desc in ship for desc in descriptors) for ship in ships)
        has_concept = any(any(concept in ship for concept in concepts) for ship in ships)

        assert has_descriptor or has_concept  # At least some themed elements
