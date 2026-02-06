"""Scalable themed name generator supporting 100,000+ unique names."""

import random
from typing import Literal

# Expanded word lists for character names
PREFIXES = [
    # Tech terms
    "Quantum", "Neural", "Algo", "Cyber", "Digital", "Binary",
    "Logic", "Matrix", "Vector", "Tensor", "Code", "Pixel",
    # AI terms
    "Neuro", "Synth", "Auto", "Deep", "Smart", "Intel",
    "Learn", "Cogni", "Predict", "Adapt", "Evolve", "Sense",
    # Crypto terms
    "Crypto", "Block", "Hash", "Token", "Chain", "Ledger",
    "Proof", "Sign", "Secure", "Trust", "Vault", "Shield",
    # General tech
    "Meta", "Hyper", "Ultra", "Mega", "Nano", "Micro",
    "Proto", "Core", "Prime", "Apex"
]  # 42 words

MIDDLE_CONNECTORS = [
    # Data terms
    "Data", "Info", "Byte", "Cache", "Stream", "Flow",
    "Query", "Parse", "Index", "Graph", "Signal", "Pattern",
    # Operations
    "Compute", "Process", "Analyze", "Optimize", "Execute", "Calculate",
    "Derive", "Infer", "Detect", "Predict", "Model", "Train",
    # Network
    "Net", "Node", "Link", "Edge", "Mesh", "Grid",
    "Cloud", "Cluster", "Shard", "Layer", "Stack", "Queue",
    # Metrics
    "Metric", "Score", "Value", "Rate", "Ratio", "Factor",
    "Weight", "Scale", "Rank", "Grade", "Stat", "Count"
]  # 48 words

SUFFIXES = [
    # Trading roles
    "Trader", "Broker", "Dealer", "Agent", "Player", "Operator",
    "Manager", "Handler", "Runner", "Pilot", "Captain", "Chief",
    # Economic terms
    "Profit", "Capital", "Equity", "Asset", "Yield", "Margin",
    "Fund", "Portfolio", "Invest", "Market", "Wealth", "Fortune",
    # Actions
    "Trade", "Buy", "Sell", "Hedge", "Arbitrage", "Leverage",
    # Greek letters
    "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta",
    "Theta", "Omega", "Sigma", "Phi"
]  # 38 words

# Ship name components
SHIP_DESCRIPTORS = [
    # Speed
    "Swift", "Rapid", "Quick", "Flash", "Bolt", "Rush",
    "Sonic", "Turbo", "Hyper", "Velocity", "Mach", "Streak",
    # Stealth
    "Silent", "Ghost", "Shadow", "Phantom", "Whisper", "Spectre",
    "Shade", "Lurk", "Cloak", "Stealth", "Shroud", "Veil",
    # Power
    "Mighty", "Titan", "Colossus", "Giant", "Mega", "Ultra",
    "Supreme", "Prime", "Apex", "Peak", "Maximum", "Grand",
    # Elements
    "Iron", "Steel", "Crystal", "Plasma", "Quantum", "Photon",
    "Neutron", "Electron", "Fusion", "Ion", "Proton", "Atomic",
    # Celestial
    "Nova", "Star", "Comet", "Meteor", "Solar", "Lunar",
    "Stellar", "Cosmic", "Astral", "Nebula", "Galaxy", "Pulsar",
    # Colors/Metals
    "Silver", "Golden", "Azure", "Crimson", "Emerald", "Sapphire",
    "Titanium", "Tungsten", "Adamant", "Diamond", "Obsidian", "Platinum",
    # Weather/Force
    "Storm", "Thunder", "Lightning", "Tempest", "Cyclone", "Vortex",
    "Gale", "Typhoon", "Hurricane", "Blizzard", "Maelstrom", "Tornado",
    # Attributes
    "Bold", "Brave", "Dark", "Bright", "Noble", "Regal",
    "Wild", "Free", "Lone", "Last", "First", "Final"
]  # 96 words

SHIP_CONCEPTS = [
    # Journeys
    "Venture", "Quest", "Odyssey", "Voyage", "Trek", "Journey",
    "Mission", "Path", "Route", "Expedition", "Crusade", "Safari",
    # Destinations
    "Horizon", "Destiny", "Fortune", "Legacy", "Haven", "Refuge",
    "Sanctuary", "Citadel", "Bastion", "Gateway", "Portal", "Nexus",
    # Creatures
    "Phoenix", "Dragon", "Falcon", "Hawk", "Eagle", "Raven",
    "Griffin", "Wyvern", "Serpent", "Wolf", "Tiger", "Lion",
    "Panther", "Jaguar", "Leopard", "Cobra", "Viper", "Raptor",
    # Forces
    "Wind", "Tide", "Wave", "Current", "Flux", "Flow",
    # Abstract concepts
    "Dream", "Vision", "Hope", "Pride", "Glory", "Honor",
    "Courage", "Valor", "Spirit", "Soul", "Will", "Might",
    "Power", "Force", "Energy", "Essence", "Core", "Heart",
    # Objects
    "Blade", "Arrow", "Spear", "Shield", "Hammer", "Sword",
    "Lance", "Dagger", "Saber", "Cutlass", "Scimitar", "Rapier",
    # Directions
    "North", "South", "East", "West", "Zenith", "Nadir",
    # Abstract
    "Eternal", "Infinite", "Endless", "Boundless", "Sovereign", "Emperor"
]  # 84 words

# Roman numerals for ship variants
ROMAN_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
                  "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]


class NameGenerator:
    """Scalable name generator supporting 100,000+ unique names."""

    def __init__(self, seed: int | None = None):
        """Initialize with optional seed for reproducible names.

        Args:
            seed: Random seed for reproducible generation. None for random.
        """
        self.seed = seed
        self.rng = random.Random(seed)
        self.used_names: set[str] = set()
        self._name_counter = 0  # For fallback numbering

    def generate_character_name(
        self,
        complexity: Literal["simple", "medium", "complex", "numbered"] = "medium"
    ) -> str:
        """Generate unique character name with configurable complexity.

        Args:
            complexity:
                - simple: 2-part names (prefix+suffix) - ~1,600 combinations
                - medium: 3-part names (prefix+middle+suffix) - ~77,000 combinations
                - complex: 4-part names (prefix+middle1+middle2+suffix) - ~3.7M combinations
                - numbered: Always adds number suffix for unlimited names

        Returns:
            Unique character name like "QuantumTrader" or "NeuralDataProfit"
        """
        max_attempts = 100

        for attempt in range(max_attempts):
            if complexity == "simple" or (complexity == "medium" and attempt > 50):
                # 2-part: Prefix + Suffix
                name = f"{self.rng.choice(PREFIXES)}{self.rng.choice(SUFFIXES)}"

            elif complexity == "medium":
                # 3-part: Prefix + Middle + Suffix
                name = (f"{self.rng.choice(PREFIXES)}"
                       f"{self.rng.choice(MIDDLE_CONNECTORS)}"
                       f"{self.rng.choice(SUFFIXES)}")

            elif complexity == "complex":
                # 4-part: Prefix + Middle1 + Middle2 + Suffix
                m1, m2 = self.rng.sample(MIDDLE_CONNECTORS, 2)
                name = (f"{self.rng.choice(PREFIXES)}"
                       f"{m1}{m2}"
                       f"{self.rng.choice(SUFFIXES)}")

            else:  # numbered
                # Always use number
                base = f"{self.rng.choice(PREFIXES)}{self.rng.choice(SUFFIXES)}"
                self._name_counter += 1
                name = f"{base}{self._name_counter}"

            if name not in self.used_names:
                self.used_names.add(name)
                return name

        # Fallback with counter if all attempts exhausted
        self._name_counter += 1
        base = f"{self.rng.choice(PREFIXES)}Bot"
        name = f"{base}{self._name_counter}"
        self.used_names.add(name)
        return name

    def generate_ship_name(self, add_number: bool = False) -> str:
        """Generate unique ship name.

        Args:
            add_number: If True, adds roman numeral (e.g., "Swift Venture II")

        Returns:
            Ship name like "Swift Venture" or "Swift Venture III"
        """
        max_attempts = 100

        for _ in range(max_attempts):
            descriptor = self.rng.choice(SHIP_DESCRIPTORS)
            concept = self.rng.choice(SHIP_CONCEPTS)

            if add_number:
                numeral = self.rng.choice(ROMAN_NUMERALS)
                name = f"{descriptor} {concept} {numeral}"
            else:
                name = f"{descriptor} {concept}"

            if name not in self.used_names:
                self.used_names.add(name)
                return name

        # Fallback with counter
        self._name_counter += 1
        name = f"Trading Ship {self._name_counter}"
        self.used_names.add(name)
        return name

    def mark_used(self, name: str) -> None:
        """Mark a name as already used (for collision avoidance).

        Args:
            name: Name to mark as used
        """
        self.used_names.add(name)

    def get_stats(self) -> dict[str, int]:
        """Get statistics about name generation.

        Returns:
            Dictionary with generation statistics:
                - total_generated: Total names created
                - counter: Internal counter value
                - estimated_remaining_simple: Approx remaining simple names
                - estimated_remaining_medium: Approx remaining medium names
                - estimated_remaining_complex: Approx remaining complex names
        """
        # Count by approximate length to categorize
        simple_count = len([n for n in self.used_names if len(n) < 20])
        medium_count = len([n for n in self.used_names if 20 <= len(n) < 35])

        return {
            "total_generated": len(self.used_names),
            "counter": self._name_counter,
            "estimated_remaining_simple": max(0, 1596 - simple_count),  # 42 * 38
            "estimated_remaining_medium": max(0, 76608 - medium_count),  # 42 * 48 * 38
            "estimated_remaining_complex": max(0, 3673728 - len(self.used_names)),  # Full pool
        }

    def reset(self, keep_used_names: bool = False) -> None:
        """Reset the generator state.

        Args:
            keep_used_names: If True, keeps the used names set (for collision avoidance)
        """
        self.rng = random.Random(self.seed)
        self._name_counter = 0
        if not keep_used_names:
            self.used_names.clear()
