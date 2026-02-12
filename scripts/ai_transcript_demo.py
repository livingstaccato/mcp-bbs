#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Live transcript demo: watch gemma3 decide what the bot does next.

Shows the full prompt → response → parse pipeline with color output.
"""

from __future__ import annotations

import asyncio
import json
import time

# ── ANSI colors ──────────────────────────────────────────────────────────
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
RESET = "\033[0m"
RULE = f"{DIM}{'─' * 80}{RESET}"


def header(title: str) -> str:
    return f"\n{BOLD}{CYAN}┌{'─' * 78}┐{RESET}\n{BOLD}{CYAN}│ {title:<76} │{RESET}\n{BOLD}{CYAN}└{'─' * 78}┘{RESET}"


async def main() -> None:
    from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge
    from bbsbot.games.tw2002.strategies.ai.parser import ResponseParser
    from bbsbot.games.tw2002.strategies.ai.prompts import PromptBuilder
    from bbsbot.llm.config import LLMConfig, OllamaConfig
    from bbsbot.llm.manager import LLMManager
    from bbsbot.llm.types import ChatRequest

    # ── 1. Set up components ────────────────────────────────────────────
    print(header("AI STRATEGY TRANSCRIPT DEMO"))

    llm_config = LLMConfig(
        provider="ollama",
        ollama=OllamaConfig(model="gemma3", timeout_seconds=120),
    )
    manager = LLMManager(llm_config)
    builder = PromptBuilder()
    parser = ResponseParser()

    # ── 2. Verify & warm up model ───────────────────────────────────────
    print(f"\n{YELLOW}[1/4] Verifying model...{RESET}")
    t0 = time.time()
    info = await manager.verify_model("gemma3")
    warmup_ms = (time.time() - t0) * 1000
    print(f"  {GREEN}✓ Model: {info['name']}  Warmup: {warmup_ms:.0f}ms{RESET}")

    # ── 3. Build game scenarios ─────────────────────────────────────────
    scenarios = [
        {
            "name": "Trading opportunity at BBS port",
            "state": GameState(
                context="sector_command",
                sector=142,
                credits=15_420,
                turns_left=387,
                has_port=True,
                port_class="BBS",
                warps=[55, 203, 891],
                holds_total=50,
                holds_free=50,
                fighters=10,
                shields=100,
            ),
        },
        {
            "name": "Exploring unknown space, no port",
            "state": GameState(
                context="sector_command",
                sector=891,
                credits=22_100,
                turns_left=340,
                has_port=False,
                port_class=None,
                warps=[142, 990, 1001],
                holds_total=50,
                holds_free=20,
                fighters=10,
                shields=100,
            ),
        },
        {
            "name": "Danger! Hostile fighters detected",
            "state": GameState(
                context="sector_command",
                sector=500,
                credits=45_000,
                turns_left=200,
                has_port=True,
                port_class="SSB",
                warps=[499, 501],
                holds_total=50,
                holds_free=10,
                hostile_fighters=150,
                fighters=10,
                shields=50,
            ),
        },
    ]

    knowledge = SectorKnowledge()

    # ── 4. Run each scenario ────────────────────────────────────────────
    for i, scenario in enumerate(scenarios, 1):
        print(header(f"SCENARIO {i}: {scenario['name']}"))
        state = scenario["state"]

        # Build prompt
        messages = builder.build(
            state,
            knowledge,
            {},
            goal_description="Maximize credits per turn through smart trading",
            goal_instructions="Focus on high-value trade routes. Avoid unnecessary combat.",
        )

        system_msg = messages[0]
        user_msg = messages[1]

        # Show system prompt (abbreviated)
        print(f"\n{BOLD}{MAGENTA}── SYSTEM PROMPT ──{RESET}")
        lines = system_msg.content.split("\n")
        for line in lines[:5]:
            print(f"  {DIM}{line}{RESET}")
        print(f"  {DIM}... ({len(lines)} lines total){RESET}")

        # Show user prompt in full
        print(f"\n{BOLD}{YELLOW}── USER PROMPT ──{RESET}")
        for line in user_msg.content.split("\n"):
            print(f"  {line}")

        # Call LLM
        print(f"\n{BOLD}{CYAN}── CALLING gemma3 ──{RESET}")
        request = ChatRequest(
            messages=[system_msg, user_msg],
            model="gemma3",
            temperature=0.7,
            max_tokens=500,
        )

        t0 = time.time()
        response = await manager.chat(request)
        duration_ms = (time.time() - t0) * 1000

        raw = response.message.content
        tokens = response.usage.total_tokens if response.usage else "?"

        print(f"  {DIM}Response time: {duration_ms:.0f}ms | Tokens: {tokens}{RESET}")

        # Show raw LLM response
        print(f"\n{BOLD}{GREEN}── RAW LLM RESPONSE ──{RESET}")
        for line in raw.split("\n"):
            print(f"  {GREEN}{line}{RESET}")

        # Parse response
        print(f"\n{BOLD}{MAGENTA}── PARSE RESULT ──{RESET}")
        try:
            action, params = parser.parse(response, state)
            print(f"  {BOLD}Action:{RESET}  {action.name}")
            print(f"  {BOLD}Params:{RESET}  {json.dumps(params, indent=2)}")

            # Extract reasoning
            try:
                data = json.loads(raw)
                reasoning = data.get("reasoning", "")
                confidence = data.get("confidence", "?")
                print(f"  {BOLD}Reason:{RESET}  {reasoning}")
                print(f"  {BOLD}Confidence:{RESET} {confidence}")
            except json.JSONDecodeError:
                pass

            print(f"  {GREEN}✓ Parse succeeded{RESET}")
        except Exception as e:
            print(f"  {RED}✗ Parse failed: {e}{RESET}")

        print(RULE)

    # ── 5. Cleanup ──────────────────────────────────────────────────────
    await manager.close()
    print(f"\n{BOLD}Done. All {len(scenarios)} scenarios completed.{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
