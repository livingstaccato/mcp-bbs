"""LLM-based analysis for stuck bots."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.llm.manager import LLMManager

logger = get_logger(__name__)


class StuckBotAnalyzer:
    """Analyzes stuck bot states using LLM to suggest fixes."""

    def __init__(self, llm_manager: LLMManager):
        """Initialize analyzer with LLM manager.

        Args:
            llm_manager: LLM manager for running analysis queries
        """
        self.llm_manager = llm_manager

    async def analyze_stuck_bot(
        self,
        bot_id: str,
        error_type: str,
        recent_screens: list[str],
        recent_prompts: list[str],
        loop_history: list[str],
        exit_reason: str,
    ) -> dict:
        """Analyze why bot got stuck and suggest rule improvements.

        Args:
            bot_id: Bot identifier
            error_type: Exception type that caused failure
            recent_screens: Last N screens the bot saw
            recent_prompts: Last N prompts detected
            loop_history: Alternation history from loop detector
            exit_reason: Reason for bot exit

        Returns:
            Dictionary with diagnosis and suggested fixes
        """
        # Build diagnostic prompt
        prompt = f"""A bot ({bot_id}) got stuck and had to be stopped.

Error Type: {error_type}
Exit Reason: {exit_reason}

Recent Prompt History:
{chr(10).join(recent_prompts[-10:]) if recent_prompts else "No prompts captured"}

Loop Pattern Detected:
{chr(10).join(loop_history[-20:]) if loop_history else "No loop pattern"}

Last Screen Content:
{recent_screens[-1][:1000] if recent_screens else "No screen captured"}

Analyze:
1. What screen/state was the bot stuck at?
2. Why did recovery fail?
3. Is this a missing prompt pattern in rules.json?
4. Is this a logic bug in orientation/recovery?
5. Suggest a new rule or fix to prevent this.

Respond in JSON:
{{
  "diagnosis": "brief description of problem",
  "stuck_at": "screen/prompt name",
  "root_cause": "why recovery failed",
  "suggested_rule": {{
    "prompt_id": "descriptive_name",
    "regex": "pattern to detect this screen",
    "input_type": "single_key|multi_key",
    "example": "example key to send"
  }} OR null,
  "suggested_code_fix": "description of code change needed" OR null
}}
        """

        try:
            from bbsbot.llm import ChatMessage, ChatRequest

            request = ChatRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                model="gemma3",
                temperature=0.3,
                max_tokens=1000,
            )

            response = await self.llm_manager.chat(request)

            # Try to parse JSON response
            try:
                return json.loads(response.message.content)
            except json.JSONDecodeError:
                return {"error": "LLM response not valid JSON", "raw": response.message.content}

        except Exception as e:
            logger.error(f"Diagnostic analysis failed: {e}")
            return {"error": f"Analysis failed: {type(e).__name__}", "message": str(e)}
