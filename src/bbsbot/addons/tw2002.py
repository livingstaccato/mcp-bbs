"""TradeWars 2002 addon for port/sector/transaction tracking."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bbsbot.addons.base import AddonEvent


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
_CREDITS_RE = re.compile(
    r"You have\s+(?P<credits>[\d,]+)\s+credits.*?(?P<holds>\d+)\s+empty cargo holds", re.IGNORECASE
)

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
_TRADE_QTY_RE = re.compile(
    r"How many holds of\s+(?P<item>Fuel Ore|Organics|Equipment)\s+do you want to (buy|sell)", re.IGNORECASE
)
_TRADE_AGREED_QTY_RE = re.compile(r"Agreed,\s+(?P<qty>\d+)\s+units\.", re.IGNORECASE)
_PLANETS_RE = re.compile(r"Planets?\s*:\s*(?P<planets>.+)$", re.IGNORECASE)
_ALIEN_TRADER_RE = re.compile(
    r"Alien Tr:\s*(?P<menace>Menace\s+\d+(st|nd|rd|th)\s+Class)\s+(?P<name>[^,]+),\s*w/\s*(?P<ftrs>[\d,]+)\s+ftrs,\s*\n\s*in\s+(?P<ship>.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_WARP_INOUT_RE = re.compile(
    r"^(?P<name>[A-Za-z .]+)\s+warps\s+(?P<dir>into|out of)\s+the\s+sector\.", re.IGNORECASE | re.MULTILINE
)
_SHIP_INFO_RE = re.compile(r"Ship Info\s*:\s*(?P<info>.+)$", re.IGNORECASE | re.MULTILINE)
_SHIP_NAME_RE = re.compile(r"Ship Name\s*:\s*(?P<name>.+)$", re.IGNORECASE | re.MULTILINE)
_RANK_RE = re.compile(
    r"Rank and Exp\s*:\s*(?P<exp>[\d,]+)\s+points,\s*Alignment=(?P<align>[-\d]+)\s+(?P<align_label>.+)$", re.IGNORECASE
)
_HOLDS_RE = re.compile(r"Total Holds\s*:\s*(?P<total>\d+)\s*-\s*(?P<holds>.+)$", re.IGNORECASE)
_BEACON_RE = re.compile(r"Beacon\s*:\s*(?P<beacon>.+)$", re.IGNORECASE | re.MULTILINE)


class Tw2002Addon(BaseModel):
    name: str = "tw2002"
    last_port: str | None = None
    last_item: str | None = None
    last_action: str | None = None
    last_price: int | None = None
    last_offer: int | None = None
    last_qty: int | None = None
    last_credits: int | None = None
    state: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def process(self, snapshot: dict[str, Any]) -> list[AddonEvent]:
        screen = snapshot.get("screen", "")
        events: list[AddonEvent] = []

        if match := _COMMAND_RE.search(screen):
            events.append(
                AddonEvent(
                    name="tw2002.command",
                    data={"sector": int(match["sector"]), "turns_left": match["tl"]},
                )
            )

        if match := _SECTOR_RE.search(screen):
            events.append(
                AddonEvent(
                    name="tw2002.sector",
                    data={
                        "sector": int(match["sector"]),
                        "region": match["region"].strip(),
                        "unexplored": bool(match["unexplored"]),
                    },
                )
            )

        if match := _WARPS_RE.search(screen):
            warps = [w.strip(" ()") for w in match["warps"].split("-")]
            warps = [w for w in warps if w]
            events.append(AddonEvent(name="tw2002.warps", data={"warps": warps}))

        if match := _PORT_RE.search(screen):
            self.last_port = match["name"].strip()
            events.append(
                AddonEvent(
                    name="tw2002.port",
                    data={
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
                    name="tw2002.commerce_report",
                    data={"port": self.last_port, "time": match["time"].strip()},
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
                events.append(AddonEvent(name="tw2002.port_items", data={"port": self.last_port, "items": items}))

        if match := _CREDITS_RE.search(screen):
            credits = _to_int(match["credits"])
            empty_holds = int(match["holds"])
            events.append(AddonEvent(name="tw2002.credits", data={"credits": credits, "empty_holds": empty_holds}))
            if (
                self.last_credits is not None
                and self.last_qty
                and self.last_price
                and self.last_item
                and self.last_action
            ):
                delta = credits - self.last_credits
                unit_price = self.last_price
                total_value = unit_price * self.last_qty
                events.append(
                    AddonEvent(
                        name="tw2002.ledger",
                        data={
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
                    name="tw2002.trade_quantity_prompt",
                    data={"item": self.last_item, "action": self.last_action},
                )
            )

        if match := _TRADE_AGREED_QTY_RE.search(screen):
            self.last_qty = int(match["qty"])
            events.append(AddonEvent(name="tw2002.trade_quantity", data={"qty": self.last_qty}))

        if match := _HAGGLE_ACCEPT_RE.search(screen):
            price = _to_int(match["price"])
            self.last_price = price
            events.append(
                AddonEvent(
                    name="tw2002.haggle_price",
                    data={
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
                        name="tw2002.haggle_offer",
                        data={
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
                    name="tw2002.haggle_result",
                    data={
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
            events.append(AddonEvent(name="tw2002.planets", data={"planets": planets}))

        if match := _ALIEN_TRADER_RE.search(screen):
            events.append(
                AddonEvent(
                    name="tw2002.alien_trader",
                    data={
                        "menace": match["menace"],
                        "name": match["name"].strip(),
                        "fighters": _to_int(match["ftrs"]),
                        "ship": match["ship"].strip(),
                    },
                )
            )

        for match in _WARP_INOUT_RE.finditer(screen):
            events.append(
                AddonEvent(
                    name="tw2002.trader_warp",
                    data={"name": match["name"].strip(), "direction": match["dir"].lower()},
                )
            )

        if match := _SHIP_NAME_RE.search(screen):
            events.append(AddonEvent(name="tw2002.ship_name", data={"name": match["name"].strip()}))

        if match := _SHIP_INFO_RE.search(screen):
            events.append(AddonEvent(name="tw2002.ship_info", data={"info": match["info"].strip()}))

        if match := _RANK_RE.search(screen):
            events.append(
                AddonEvent(
                    name="tw2002.rank",
                    data={
                        "exp": _to_int(match["exp"]),
                        "alignment": int(match["align"]),
                        "alignment_label": match["align_label"].strip(),
                    },
                )
            )

        if match := _HOLDS_RE.search(screen):
            holds = match["holds"].strip()
            events.append(
                AddonEvent(
                    name="tw2002.holds",
                    data={"total": int(match["total"]), "details": holds},
                )
            )

        if match := _BEACON_RE.search(screen):
            events.append(AddonEvent(name="tw2002.beacon", data={"beacon": match["beacon"].strip()}))

        return events
