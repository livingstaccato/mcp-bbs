"""Prompt building for AI strategy.

Converts game state into effective LLM prompts.
"""

from __future__ import annotations

from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge
from bbsbot.llm.types import ChatMessage

# System prompt explaining game mechanics and expected response format
SYSTEM_PROMPT_BASE = """You are an expert Trade Wars 2002 player.

GAME MECHANICS:
- Port classes: B=Buys (you sell), S=Sells (you buy). Example: "BBS" means Buys Fuel, Buys Organics, Sells Equipment.
- Profit: Buy low at S-ports, sell high at B-ports. Minimize warp hops (1 turn each).
- Combat: Hostile fighters are dangerous. Retreat if outmatched.
- Resources: Each action costs turns. Bank to protect credits. Upgrade to improve capacity.

ACTIONS:
- TRADE: Buy/sell at current port
- MOVE: Navigate to target sector
- EXPLORE: Visit unknown sector
- BANK: Deposit credits
- UPGRADE: Buy ship improvements
- RETREAT: Flee from danger
- WAIT: Do nothing (use sparingly)
- DONE: Stop playing

IMPORTANT: You MUST respond with ONLY a JSON object. No other text before or after.
Do NOT include explanations, markdown, or code blocks. Just raw JSON.

Example response:
{"action": "TRADE", "reasoning": "Port sells equipment cheaply, good profit opportunity", "confidence": 0.85, "parameters": {"commodity": "equipment"}}

Parameter formats:
- TRADE: {"commodity": "fuel_ore|organics|equipment"}
- MOVE: {"target_sector": int}
- EXPLORE: {}
- BANK: {}
- UPGRADE: {"upgrade_type": "holds|fighters|shields"}
- RETREAT: {}
- WAIT: {}
- DONE: {}"""


class PromptBuilder:
    """Builds prompts for LLM from game state."""

    def build(
        self,
        state: GameState,
        knowledge: SectorKnowledge,
        stats: dict,
        goal_description: str | None = None,
        goal_instructions: str | None = None,
        stuck_action: str | None = None,
    ) -> list[ChatMessage]:
        """Build chat messages for LLM.

        Args:
            state: Current game state
            knowledge: Sector knowledge for adjacent sectors
            stats: Strategy statistics
            goal_description: Current goal description
            goal_instructions: Current goal instructions
            stuck_action: If set, the action the LLM has been repeating

        Returns:
            List of chat messages (system + user)
        """
        # Build system prompt with goal
        system_prompt = SYSTEM_PROMPT_BASE
        if goal_description and goal_instructions:
            system_prompt = f"""{SYSTEM_PROMPT_BASE}

CURRENT GOAL: {goal_description}
{goal_instructions}"""
        else:
            system_prompt = f"{SYSTEM_PROMPT_BASE}\n\nYour goal is to maximize profit per turn while managing risk."

        user_prompt = self._build_user_prompt(state, knowledge, stats)

        # Inject stuck hint if the LLM keeps repeating the same action
        if stuck_action:
            user_prompt += (
                f"\n\nWARNING: Your last 3 actions were all {stuck_action}. "
                f"You MUST choose a DIFFERENT action this time."
            )

        return [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]

    def _build_user_prompt(
        self,
        state: GameState,
        knowledge: SectorKnowledge,
        stats: dict,
    ) -> str:
        """Build dynamic user prompt from game state.

        Args:
            state: Current game state
            knowledge: Sector knowledge
            stats: Strategy statistics

        Returns:
            Formatted prompt string
        """
        # Build sections
        sections = []

        # Current situation
        sections.append(self._format_current_situation(state))

        # Ship status
        sections.append(self._format_ship_status(state))

        # Current sector
        sections.append(self._format_current_sector(state))

        # Adjacent sectors
        adjacent = self._format_adjacent_sectors(state, knowledge)
        if adjacent:
            sections.append(f"Adjacent Sectors:\n{adjacent}")

        # Strategy stats
        sections.append(self._format_stats(stats))

        return "\n\n".join(sections) + "\n\nWhat action should you take?"

    def _format_current_situation(self, state: GameState) -> str:
        """Format current situation section."""
        return f"""CURRENT SITUATION:
Location: Sector {state.sector if state.sector else "Unknown"}
Context: {state.context}
Credits: {state.credits if state.credits is not None else "Unknown"}
Turns Left: {state.turns_left if state.turns_left is not None else "Unknown"}"""

    def _format_ship_status(self, state: GameState) -> str:
        """Format ship status section."""
        holds_info = "Unknown"
        if state.holds_free is not None and state.holds_total is not None:
            holds_info = f"{state.holds_free}/{state.holds_total} free"

        return f"""Ship Status:
  Holds: {holds_info}
  Fighters: {state.fighters if state.fighters is not None else "Unknown"}
  Shields: {state.shields if state.shields is not None else "Unknown"}
  Type: {state.ship_type or "Unknown"}"""

    def _format_current_sector(self, state: GameState) -> str:
        """Format current sector information."""
        port_info = "None"
        if state.has_port and state.port_class:
            port_info = state.port_class

        warps_info = "None"
        if state.warps:
            warps_info = ", ".join(str(w) for w in sorted(state.warps))

        threat_info = "None"
        if state.hostile_fighters > 0:
            threat_info = f"{state.hostile_fighters} hostile fighters"

        return f"""Current Sector:
  Has Port: {state.has_port}
  Port Class: {port_info}
  Warps To: {warps_info}
  Threats: {threat_info}"""

    def _format_adjacent_sectors(
        self,
        state: GameState,
        knowledge: SectorKnowledge,
    ) -> str:
        """Format information about adjacent sectors.

        Args:
            state: Current game state
            knowledge: Sector knowledge

        Returns:
            Formatted string or empty if no adjacent info
        """
        if not state.sector or not state.warps:
            return ""

        lines = []
        for warp_sector in sorted(state.warps):
            sector_info = knowledge.get_sector_info(warp_sector)
            if sector_info and sector_info.port_class:
                lines.append(f"  Sector {warp_sector}: Port {sector_info.port_class}")

        return "\n".join(lines) if lines else ""

    def _format_stats(self, stats: dict) -> str:
        """Format strategy statistics."""
        return f"""Strategy Stats:
  Trades: {stats.get("trades_executed", 0)}
  Total Profit: {stats.get("total_profit", 0)}
  Profit/Turn: {stats.get("profit_per_turn", 0.0):.1f}
  Turns Used: {stats.get("turns_used", 0)}"""
