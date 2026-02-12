# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Response parser for AI strategy.

Parses LLM responses into TradeAction decisions.
"""

import json
import re

from bbsbot.games.tw2002.orientation import GameState
from bbsbot.games.tw2002.strategies.base import TradeAction
from bbsbot.llm.types import ChatResponse
from bbsbot.logging import get_logger

logger = get_logger(__name__)


class ResponseParser:
    """Parses LLM responses into game actions."""

    def parse(
        self,
        response: ChatResponse,
        state: GameState,
    ) -> tuple[TradeAction, dict]:
        """Parse LLM response into action.

        Strategy:
        1. Try JSON parsing first
        2. Fallback to regex extraction
        3. Validate against game state

        Args:
            response: LLM chat response
            state: Current game state for validation

        Returns:
            Tuple of (action, parameters)

        Raises:
            ValueError: If response cannot be parsed
        """
        content = response.message.content

        # Try JSON parsing first
        try:
            data = self._parse_json(content)
            action = TradeAction[data["action"]]
            params = data.get("parameters", {})
            if strategy_name := data.get("strategy") or data.get("strategy_id"):
                params["strategy"] = str(strategy_name).strip().lower()
            if policy := data.get("policy") or data.get("mode"):
                params["policy"] = str(policy).strip().lower()
            review_turns = data.get("review_after_turns")
            if review_turns is None:
                review_turns = data.get("check_after_turns")
            if review_turns is not None:
                try:
                    params["review_after_turns"] = int(review_turns)
                except Exception:
                    logger.debug("invalid_review_after_turns", value=review_turns)
            self._normalize_trade_params(action, params, state)
            logger.debug(
                "ai_response_parsed",
                action=action.name,
                reasoning=data.get("reasoning"),
                confidence=data.get("confidence"),
            )
            return action, params
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug("json_parse_failed", error=str(e))

        # Try regex fallback
        try:
            action, params = self._parse_with_regex(content, state)
            strategy_name = self._extract_strategy_hint(content)
            if strategy_name:
                params["strategy"] = strategy_name
            policy = self._extract_policy_hint(content)
            if policy:
                params["policy"] = policy
            review_turns = self._extract_review_hint(content)
            if review_turns is not None:
                params["review_after_turns"] = review_turns
            self._normalize_trade_params(action, params, state)
            logger.debug("ai_response_regex_parsed", action=action.name)
            return action, params
        except ValueError as e:
            logger.error("regex_parse_failed", error=str(e), content=content)
            raise ValueError(f"Could not parse LLM response: {content[:200]}") from e

    def _parse_json(self, content: str) -> dict:
        """Parse JSON from content.

        Handles cases where JSON is wrapped in markdown code blocks.

        Args:
            content: Response content

        Returns:
            Parsed JSON dictionary

        Raises:
            json.JSONDecodeError: If JSON parsing fails
        """
        # Try direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))

        # Try finding raw JSON object
        json_match = re.search(r"\{.*?\}", content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))

        raise json.JSONDecodeError("No JSON found", content, 0)

    def _parse_with_regex(
        self,
        content: str,
        state: GameState,
    ) -> tuple[TradeAction, dict]:
        """Parse response using regex patterns.

        Args:
            content: Response content
            state: Current game state

        Returns:
            Tuple of (action, parameters)

        Raises:
            ValueError: If no valid action found
        """
        content_upper = content.upper()

        # Look for action keywords
        if "TRADE" in content_upper:
            # Extract commodity if mentioned
            commodity = None
            if "FUEL" in content_upper or "ORE" in content_upper:
                commodity = "fuel_ore"
            elif "ORGANIC" in content_upper:
                commodity = "organics"
            elif "EQUIPMENT" in content_upper:
                commodity = "equipment"

            params = {}
            if commodity:
                params["commodity"] = commodity
            return TradeAction.TRADE, params

        if "MOVE" in content_upper or "WARP" in content_upper or "GO TO" in content_upper:
            # Try to extract sector number
            sector_match = re.search(r"(?:SECTOR|TO)\s+(\d+)", content_upper)
            if sector_match:
                target = int(sector_match.group(1))
                return TradeAction.MOVE, {"target_sector": target}
            # If we have warps, pick the first one
            if state.warps:
                return TradeAction.MOVE, {"target_sector": state.warps[0]}
            return TradeAction.EXPLORE, {}

        if "EXPLORE" in content_upper:
            return TradeAction.EXPLORE, {}

        if "BANK" in content_upper or "DEPOSIT" in content_upper:
            return TradeAction.BANK, {}

        if "UPGRADE" in content_upper:
            upgrade_type = "holds"  # Default
            if "FIGHTER" in content_upper:
                upgrade_type = "fighters"
            elif "SHIELD" in content_upper:
                upgrade_type = "shields"
            return TradeAction.UPGRADE, {"upgrade_type": upgrade_type}

        if "RETREAT" in content_upper or "FLEE" in content_upper or "ESCAPE" in content_upper:
            return TradeAction.RETREAT, {}

        if "WAIT" in content_upper or "NOTHING" in content_upper:
            return TradeAction.WAIT, {}

        if "DONE" in content_upper or "STOP" in content_upper or "QUIT" in content_upper:
            return TradeAction.DONE, {}

        # Default to WAIT if nothing matches
        logger.warning("no_action_matched", content=content[:200])
        return TradeAction.WAIT, {}

    def _extract_strategy_hint(self, content: str) -> str | None:
        content_lower = content.lower()
        if "profitable_pairs" in content_lower or "profitable pairs" in content_lower:
            return "profitable_pairs"
        if "twerk_optimized" in content_lower or "twerk optimized" in content_lower:
            return "twerk_optimized"
        if "opportunistic" in content_lower:
            return "opportunistic"
        if "ai_direct" in content_lower or "direct" in content_lower:
            return "ai_direct"
        return None

    def _extract_policy_hint(self, content: str) -> str | None:
        content_lower = content.lower()
        for candidate in ("conservative", "balanced", "aggressive"):
            if candidate in content_lower:
                return candidate
        return None

    def _extract_review_hint(self, content: str) -> int | None:
        match = re.search(r"(?:review|check)\s*(?:again)?\s*(?:in|after)\s*(\d+)\s*turn", content, re.IGNORECASE)
        if not match:
            return None
        try:
            value = int(match.group(1))
            return value if value > 0 else None
        except Exception:
            return None

    def _normalize_trade_params(self, action: TradeAction, params: dict, state: GameState) -> None:
        if action != TradeAction.TRADE:
            return
        commodity = params.get("commodity")
        if commodity is None:
            return
        params["commodity"] = self._normalize_commodity(commodity, state)

    def _normalize_commodity(self, commodity: str, state: GameState) -> str:
        raw = str(commodity).strip().lower()
        if not raw:
            return raw

        # Guard against mis-parsing port class tokens (e.g., "BBS") as commodity.
        if re.fullmatch(r"[bs]{3}", raw):
            cargo_map = {
                "fuel_ore": int(getattr(state, "cargo_fuel_ore", 0) or 0),
                "organics": int(getattr(state, "cargo_organics", 0) or 0),
                "equipment": int(getattr(state, "cargo_equipment", 0) or 0),
            }
            port_class = str(getattr(state, "port_class", "") or "").strip().upper()
            mapping = [("fuel_ore", 0), ("organics", 1), ("equipment", 2)]
            # Prefer selling cargo we already hold.
            if len(port_class) == 3:
                for comm, idx in mapping:
                    if cargo_map.get(comm, 0) > 0 and port_class[idx] == "B":
                        return comm
                # Otherwise buy something the current port sells.
                for comm, idx in mapping:
                    if port_class[idx] == "S":
                        return comm
            # Last resort: stable default.
            return "fuel_ore"

        alias = {
            "fuel": "fuel_ore",
            "fuel ore": "fuel_ore",
            "ore": "fuel_ore",
            "fuel_ore": "fuel_ore",
            "organics": "organics",
            "organic": "organics",
            "equipment": "equipment",
            "equip": "equipment",
            "eq": "equipment",
        }
        if raw in alias:
            return alias[raw]

        # Handle LLM "OR" style values like "fuel_ore|organics".
        parts = re.split(r"[|,/]", raw)
        candidates = [alias.get(p.strip(), p.strip()) for p in parts if p.strip()]
        candidates = [c for c in candidates if c in ("fuel_ore", "organics", "equipment")]
        if not candidates:
            return raw
        if len(candidates) == 1:
            return candidates[0]

        # Prefer selling what we actually carry.
        cargo_map = {
            "fuel_ore": int(getattr(state, "cargo_fuel_ore", 0) or 0),
            "organics": int(getattr(state, "cargo_organics", 0) or 0),
            "equipment": int(getattr(state, "cargo_equipment", 0) or 0),
        }
        for c in candidates:
            if cargo_map.get(c, 0) > 0:
                return c

        # Otherwise choose first valid candidate.
        return candidates[0]
