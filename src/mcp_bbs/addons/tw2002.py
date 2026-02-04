"""TradeWars 2002 addon for port/sector/transaction tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from mcp_bbs.addons.base import Addon, AddonEvent


def _to_int(value: str) -> int:
    return int(value.replace(",", "").strip())


_SECTOR_RE = re.compile(
    r"Sector\s*:\s*(?P<sector>\d+)\s+in\s+(?P<region>[^.]+)(?P<unexplored>\s*\(unexplored\))?\.",
    re.IGNORECASE,
)
_WARPS_RE = re.compile(r"Warps to Sector\(s\)\s*:\s*(?P<warps>.+)$", re.IGNORECASE)
_PORT_RE = re.compile(
    r"Ports\s*:\s*(?P<name>[^,]+),\s*Class\s*(?P<class>\d+)\s*\((?P<type>[A-Z]{3})\)",
    re.IGNORECASE,
)
_COMMAND_RE = re.compile(r"Command\s*\[TL=(?P<tl>[0-9:]+)\]:\[(?P<sector>\d+)\]")
_CREDITS_RE = re.compile(r"You have\s+(?P<credits>[\d,]+)\s+credits.*?(?P<holds>\d+)\s+empty cargo holds", re.IGNORECASE)

_COMMERCE_RE = re.compile(r"Commerce report for\s+(?P<port>[^:]+):\s+(?P<time>.+)$", re.IGNORECASE)
_ITEM_RE = re.compile(
    r"^(Fuel Ore|Organics|Equipment)\s+(Buying|Selling)\s+([\d,]+)\s+(\d+)%\s+(\d+)",
    re.IGNORECASE | re.MULTILINE,
)
_HAGGLE_OFFER_RE = re.compile(r"Your offer\s*\[(?P<price>[\d,]+)\]\s*\?\s*(?P<offer>[\d,]+)?", re.IGNORECASE)
_HAGGLE_ACCEPT_RE = re.compile(r"(we'll sell them for|we'll buy them for)\s+(?P<price>[\d,]+)\s+credits", re.IGNORECASE)
_HAGGLE_RESULT_RE = re.compile(
    r"(you will put me out of business|very well|you are a rogue|swine|make a real offer|we'll buy them anyway)",
    re.IGNORECASE,
)
_TRADE_QTY_RE = re.compile(r"How many holds of\s+(?P<item>Fuel Ore|Organics|Equipment)\s+do you want to (buy|sell)", re.IGNORECASE)
_TRADE_AGREED_QTY_RE = re.compile(r"Agreed,\s+(?P<qty>\d+)\s+units\.", re.IGNORECASE)
_PLANETS_RE = re.compile(r"Planets?\s*:\s*(?P<planets>.+)$", re.IGNORECASE)


@dataclass
class Tw2002Addon(Addon):
    name: str = "tw2002"
    last_port: str | None = None
    last_item: str | None = None
    last_action: str | None = None
    last_price: int | None = None
    last_offer: int | None = None
    last_qty: int | None = None
    last_credits: int | None = None
    state: dict[str, Any] = field(default_factory=dict)

    def process(self, snapshot: dict[str, Any]) -> list[AddonEvent]:
        screen = snapshot.get("screen", "")
        events: list[AddonEvent] = []

        if match := _COMMAND_RE.search(screen):
            events.append(
                AddonEvent(
                    "tw2002.command",
                    {"sector": int(match["sector"]), "turns_left": match["tl"]},
                )
            )

        if match := _SECTOR_RE.search(screen):
            events.append(
                AddonEvent(
                    "tw2002.sector",
                    {
                        "sector": int(match["sector"]),
                        "region": match["region"].strip(),
                        "unexplored": bool(match["unexplored"]),
                    },
                )
            )

        if match := _WARPS_RE.search(screen):
            warps = [w.strip(" ()") for w in match["warps"].split("-")]
            warps = [w for w in warps if w]
            events.append(AddonEvent("tw2002.warps", {"warps": warps}))

        if match := _PORT_RE.search(screen):
            self.last_port = match["name"].strip()
            events.append(
                AddonEvent(
                    "tw2002.port",
                    {
                        "name": self.last_port,
                        "class": int(match["class"]),
                        "type": match["type"],
                    },
                )
            )

        if match := _COMMERCE_RE.search(screen):
            self.last_port = match["port"].strip()
            events.append(
                AddonEvent(
                    "tw2002.commerce_report",
                    {"port": self.last_port, "time": match["time"].strip()},
                )
            )
            items: list[dict[str, Any]] = []
            for item_match in _ITEM_RE.finditer(screen):
                items.append(
                    {
                        "item": item_match.group(1),
                        "status": item_match.group(2),
                        "amount": _to_int(item_match.group(3)),
                        "percent": int(item_match.group(4)),
                        "onboard": int(item_match.group(5)),
                    }
                )
            if items:
                events.append(AddonEvent("tw2002.port_items", {"port": self.last_port, "items": items}))

        if match := _CREDITS_RE.search(screen):
            credits = _to_int(match["credits"])
            empty_holds = int(match["holds"])
            events.append(AddonEvent("tw2002.credits", {"credits": credits, "empty_holds": empty_holds}))
            if self.last_credits is not None and self.last_qty and self.last_price and self.last_item and self.last_action:
                delta = credits - self.last_credits
                unit_price = self.last_price
                total_value = unit_price * self.last_qty
                events.append(
                    AddonEvent(
                        "tw2002.ledger",
                        {
                            "port": self.last_port,
                            "item": self.last_item,
                            "action": self.last_action,
                            "qty": self.last_qty,
                            "unit_price": unit_price,
                            "total_value": total_value,
                            "offer": self.last_offer,
                            "credits_before": self.last_credits,
                            "credits_after": credits,
                            "delta": delta,
                        },
                    )
                )
            self.last_credits = credits

        if match := _TRADE_QTY_RE.search(screen):
            self.last_item = match["item"]
            self.last_action = match.group(2).lower()
            events.append(
                AddonEvent(
                    "tw2002.trade_quantity_prompt",
                    {"item": self.last_item, "action": self.last_action},
                )
            )

        if match := _TRADE_AGREED_QTY_RE.search(screen):
            self.last_qty = int(match["qty"])
            events.append(AddonEvent("tw2002.trade_quantity", {"qty": self.last_qty}))

        if match := _HAGGLE_ACCEPT_RE.search(screen):
            price = _to_int(match["price"])
            self.last_price = price
            events.append(
                AddonEvent(
                    "tw2002.haggle_price",
                    {
                        "port": self.last_port,
                        "item": self.last_item,
                        "action": self.last_action,
                        "price": price,
                    },
                )
            )

        if match := _HAGGLE_OFFER_RE.search(screen):
            offer = match["offer"]
            if offer:
                self.last_offer = _to_int(offer)
                events.append(
                    AddonEvent(
                        "tw2002.haggle_offer",
                        {
                            "port": self.last_port,
                            "item": self.last_item,
                            "action": self.last_action,
                            "offer": self.last_offer,
                        },
                    )
                )

        if _HAGGLE_RESULT_RE.search(screen):
            events.append(
                AddonEvent(
                    "tw2002.haggle_result",
                    {
                        "port": self.last_port,
                        "item": self.last_item,
                        "action": self.last_action,
                        "price": self.last_price,
                        "offer": self.last_offer,
                    },
                )
            )

        if match := _PLANETS_RE.search(screen):
            planets = [p.strip() for p in match["planets"].split("-")]
            planets = [p for p in planets if p]
            events.append(AddonEvent("tw2002.planets", {"planets": planets}))

        return events
