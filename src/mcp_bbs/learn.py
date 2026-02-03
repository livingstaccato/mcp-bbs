from __future__ import annotations

import re
from pathlib import Path

from mcp_bbs.discover import discover_menu


def append_md(path: Path, header: str, body: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# {header}\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(body)
        if not body.endswith("\n"):
            handle.write("\n")
    return "ok"


def build_prompt_body(rule_id: str, screen: str, pattern: str, rule: dict[str, str]) -> str:
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


def build_menu_body(rule_id: str, screen: str, rule: dict[str, str]) -> str:
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


def apply_auto_learn(
    screen: str,
    screen_hash: str,
    base_dir: Path,
    prompt_rules: list[dict[str, str]],
    menu_rules: list[dict[str, str]],
    seen: set[tuple[str, str]],
) -> None:
    if not screen or not screen_hash:
        return
    for rule in prompt_rules:
        rule_id = rule.get("prompt_id", "prompt")
        key = (f"prompt:{rule_id}", screen_hash)
        if key in seen:
            continue
        pattern = rule.get("regex", "")
        if pattern and re.search(pattern, screen, re.MULTILINE):
            body = build_prompt_body(rule_id, screen, pattern, rule)
            append_md(base_dir / "prompt-catalog.md", "Prompt Catalog (Shared)", body)
            seen.add(key)
    for rule in menu_rules:
        rule_id = rule.get("menu_id", "menu")
        key = (f"menu:{rule_id}", screen_hash)
        if key in seen:
            continue
        pattern = rule.get("regex", "")
        if pattern and re.search(pattern, screen, re.MULTILINE):
            body = build_menu_body(rule_id, screen, rule)
            append_md(base_dir / "menu-map.md", "Menu Map (Shared)", body)
            seen.add(key)


def apply_auto_discover(
    screen: str,
    screen_hash: str,
    base_dir: Path,
    seen: set[tuple[str, str]],
) -> None:
    if not screen or not screen_hash:
        return
    key = ("menu:auto", screen_hash)
    if key in seen:
        return
    discovered = discover_menu(screen)
    if not discovered["options"] and not discovered["prompt"]:
        return
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
    body = build_menu_body(rule["menu_id"], screen, rule)
    append_md(base_dir / "menu-map.md", "Menu Map (Shared)", body)
    seen.add(key)
