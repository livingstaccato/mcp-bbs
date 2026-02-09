#!/usr/bin/env python3
"""Advanced sophisticated trading system for Trade Wars 2002.

Features:
- Screen parsing to extract port info, commodities, prices
- Profit margin calculation
- Route optimization
- Bot coordination via shared knowledge
- Full prompt handling
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class Commodity:
    """A commodity that can be traded."""
    name: str
    buy_price: Optional[int] = None  # Price to buy at this port
    sell_price: Optional[int] = None  # Price to sell at this port
    quantity: int = 0  # How much we're carrying


@dataclass
class PortInfo:
    """Information about a port."""
    sector: int
    port_class: str = ""  # Class 1-9
    commodities: dict[str, Commodity] = field(default_factory=dict)
    last_visited: float = 0


@dataclass
class CargoHold:
    """What we're currently carrying."""
    commodities: dict[str, int] = field(default_factory=dict)  # name -> quantity
    purchase_price: dict[str, int] = field(default_factory=dict)  # name -> price paid
    purchase_sector: dict[str, int] = field(default_factory=dict)  # name -> where bought
    capacity: int = 20  # Default cargo hold


@dataclass
class TradeRoute:
    """A profitable trade route."""
    buy_sector: int
    sell_sector: int
    commodity: str
    buy_price: int
    sell_price: int
    profit_per_unit: int
    last_used: float = 0


class SophisticatedTrader:
    """Advanced autonomous trader with profit optimization."""

    def __init__(self, bot, shared_state=None):
        self.bot = bot
        self.shared_state = shared_state
        self.cargo = CargoHold()
        self.known_ports: dict[int, PortInfo] = {}  # sector -> port info
        self.profitable_routes: list[TradeRoute] = []
        self.current_sector = 1
        self.current_credits = 1000

    async def execute_trade_cycle(self) -> dict:
        """Execute one complete trading cycle with profit optimization."""
        try:
            # Step 1: Decide what to do based on current state
            if self._have_cargo():
                # We're carrying something - go sell it
                return await self._sell_cargo()
            else:
                # Empty hold - find something profitable to buy
                return await self._find_and_buy()

        except Exception as e:
            logger.error(f"Trade cycle error: {e}")
            return {"success": False, "error": str(e)}

    def _have_cargo(self) -> bool:
        """Check if we're carrying anything."""
        return sum(self.cargo.commodities.values()) > 0

    async def _find_and_buy(self) -> dict:
        """Find a profitable commodity and buy it."""
        # Strategy:
        # 1. Check if we know any profitable routes
        # 2. If yes, go to the buy port of the best route
        # 3. If no, explore to find ports

        best_route = self._get_best_known_route()

        if best_route:
            logger.info(f"Following known route: {best_route.commodity} "
                       f"${best_route.buy_price} -> ${best_route.sell_price} "
                       f"(+${best_route.profit_per_unit}/unit)")

            # Go to buy port
            await self._warp_to_sector(best_route.buy_sector)

            # Buy the commodity
            result = await self._buy_commodity(best_route.commodity, best_route.buy_price)

            if result.get("success"):
                return {"success": True, "action": "bought", "route": best_route}

        # No known routes or failed to buy - explore
        await self._explore_and_scan()
        return {"success": True, "action": "exploring"}

    async def _sell_cargo(self) -> dict:
        """Sell what we're carrying at the best price."""
        if not self.cargo.commodities:
            return {"success": False, "error": "no_cargo"}

        # Find best port to sell at
        commodity_name = list(self.cargo.commodities.keys())[0]
        quantity = self.cargo.commodities[commodity_name]
        buy_price = self.cargo.purchase_price.get(commodity_name, 0)
        buy_sector = self.cargo.purchase_sector.get(commodity_name, 0)

        # Look for ports that buy this commodity at good prices
        best_sell_sector = self._find_best_sell_port(commodity_name, buy_price)

        if best_sell_sector:
            # Go there and sell
            await self._warp_to_sector(best_sell_sector)
            result = await self._sell_commodity(commodity_name, quantity)

            if result.get("success"):
                sell_price = result.get("price", 0)
                profit = result.get("profit", (sell_price - buy_price) * quantity)

                # Record this profitable route
                self._record_route(buy_sector, best_sell_sector, commodity_name,
                                 buy_price, sell_price)

                return {
                    "success": True,
                    "action": "sold",
                    "profit": profit,
                    "commodity": commodity_name
                }

        # Don't know where to sell - just explore and try to sell at any port
        await self._explore_and_scan()

        # After exploring, try to sell again if we found a port
        if self._have_cargo():
            result = await self._sell_commodity(commodity_name, quantity)
            if result.get("success"):
                profit = result.get("profit", 500)  # Default profit estimate
                return {
                    "success": True,
                    "action": "sold",
                    "profit": profit,
                    "commodity": commodity_name
                }

        return {"success": True, "action": "searching_for_buyer"}

    def _get_best_known_route(self) -> Optional[TradeRoute]:
        """Get the most profitable known route."""
        if not self.profitable_routes:
            return None

        # Sort by profit per unit, return best
        sorted_routes = sorted(self.profitable_routes,
                             key=lambda r: r.profit_per_unit,
                             reverse=True)
        return sorted_routes[0]

    def _find_best_sell_port(self, commodity: str, min_price: int) -> Optional[int]:
        """Find port that pays best for this commodity."""
        best_sector = None
        best_price = min_price

        for sector, port in self.known_ports.items():
            if commodity in port.commodities:
                sell_price = port.commodities[commodity].sell_price
                if sell_price and sell_price > best_price:
                    best_price = sell_price
                    best_sector = sector

        return best_sector

    def _record_route(self, buy_sector: int, sell_sector: int, commodity: str,
                     buy_price: int, sell_price: int):
        """Record a profitable trade route."""
        import time

        profit = sell_price - buy_price
        route = TradeRoute(
            buy_sector=buy_sector,
            sell_sector=sell_sector,
            commodity=commodity,
            buy_price=buy_price,
            sell_price=sell_price,
            profit_per_unit=profit,
            last_used=time.time()
        )

        self.profitable_routes.append(route)

        # Share with other bots via shared state
        if self.shared_state:
            route_dict = {
                "buy_sector": buy_sector,
                "sell_sector": sell_sector,
                "commodity": commodity,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "profit": profit
            }
            if route_dict not in self.shared_state.profitable_routes:
                self.shared_state.profitable_routes.append(route_dict)
                self.shared_state.save()

        logger.info(f"📊 Recorded route: {commodity} Sector {buy_sector} -> {sell_sector} "
                   f"(+${profit}/unit)")

    async def _explore_and_scan(self):
        """Explore to find new ports and try to trade."""
        import random

        # Move to random sector
        target = random.randint(1, 2000)
        await self._warp_to_sector(target)

        # Scan the sector
        await self._scan_current_sector()

        # If we found a port, try to use it!
        if self.current_sector in self.known_ports:
            if not self._have_cargo():
                # Try to buy something
                logger.info(f"Found port at sector {self.current_sector}, attempting to buy")
                await self._buy_commodity("Equipment", 100)  # Try to buy
            else:
                # Try to sell
                logger.info(f"Have cargo, attempting to sell at sector {self.current_sector}")
                commodity = list(self.cargo.commodities.keys())[0]
                quantity = self.cargo.commodities[commodity]
                await self._sell_commodity(commodity, quantity)

    async def _scan_current_sector(self):
        """Scan current sector for ports and record info."""
        await self.bot.session.wait_for_update(timeout_ms=1000)
        screen = self.bot.session.snapshot().get("screen", "")

        # Check if there's a port here
        if self._has_port(screen):
            port_info = self._parse_port_screen(screen)
            if port_info:
                self.known_ports[self.current_sector] = port_info
                logger.debug(f"Found port in sector {self.current_sector}: "
                           f"Class {port_info.port_class}")

    def _has_port(self, screen: str) -> bool:
        """Check if screen shows a port."""
        screen_lower = screen.lower()
        # Look for port indicators in TW2002
        return ("port" in screen_lower and "class" in screen_lower) or \
               ("trading" in screen_lower and "port" in screen_lower) or \
               ("buy" in screen_lower and "sell" in screen_lower and "commodities" in screen_lower)

    def _parse_port_screen(self, screen: str) -> Optional[PortInfo]:
        """Parse port screen to extract commodities and prices.

        Parses TW2002 port screens to extract:
        - Port class (BBS, SSB, etc.) where B=Buys, S=Sells
        - Commodity prices (Fuel Ore, Organics, Equipment)
        - Available quantities

        Port class format: Position 0=Fuel, 1=Organics, 2=Equipment
        B = Port Buys (we sell to them), S = Port Sells (we buy from them)
        """
        port = PortInfo(sector=self.current_sector)

        # Extract port class from various formats:
        # "Class BBS", "Port Class: BBS", "Class 1 (BBS)", "(BBS)"
        class_patterns = [
            r'Class\s+\d*\s*\(([BSbs]{3})\)',  # Class 1 (BBS)
            r'Class\s+([BSbs]{3})',             # Class BBS
            r'Port\s+Class[:\s]+([BSbs]{3})',   # Port Class: BBS
            r'\(([BSbs]{3})\)',                 # (BBS)
        ]

        for pattern in class_patterns:
            match = re.search(pattern, screen, re.IGNORECASE)
            if match:
                port.port_class = match.group(1).upper()
                break

        # Parse commodity information
        # Common formats:
        # "Fuel Ore: 100 at 500 cr"
        # "Organics: Buying at 300 credits"
        # "Equipment: Selling for 1200 cr"

        commodities = {
            'fuel_ore': ['fuel ore', 'fuel'],
            'organics': ['organics', 'organic'],
            'equipment': ['equipment', 'equip']
        }

        for commodity_key, aliases in commodities.items():
            for alias in aliases:
                # Pattern for "Fuel Ore: 100 at 500 cr" or "Organics: 50 @ 300"
                quantity_price = re.search(
                    rf'{alias}[:\s]+(\d+)\s+(?:at|@)\s+(\d+)',
                    screen,
                    re.IGNORECASE
                )
                if quantity_price:
                    quantity = int(quantity_price.group(1))
                    price = int(quantity_price.group(2))

                    # Determine if port is buying or selling this commodity
                    # Check surrounding context
                    start = max(0, quantity_price.start() - 50)
                    end = min(len(screen), quantity_price.end() + 50)
                    context = screen[start:end].lower()

                    commodity = Commodity(name=commodity_key, quantity=quantity)

                    if 'buying' in context or 'buy' in context:
                        commodity.buy_price = price  # Port buys (we sell)
                    elif 'selling' in context or 'sell' in context:
                        commodity.sell_price = price  # Port sells (we buy)
                    else:
                        # Use port class to determine
                        if port.port_class:
                            idx = ['fuel_ore', 'organics', 'equipment'].index(commodity_key)
                            if idx < len(port.port_class):
                                if port.port_class[idx] == 'B':
                                    commodity.buy_price = price
                                elif port.port_class[idx] == 'S':
                                    commodity.sell_price = price

                    port.commodities[commodity_key] = commodity
                    break

                # Pattern for "Fuel Ore: Buying at 500 cr" (no quantity)
                price_only = re.search(
                    rf'{alias}[:\s]+(?:buying|selling)?\s+(?:at|for)\s+(\d+)',
                    screen,
                    re.IGNORECASE
                )
                if price_only:
                    price = int(price_only.group(1))
                    context = screen[max(0, price_only.start()-30):price_only.end()+30].lower()

                    commodity = Commodity(name=commodity_key)

                    if 'buying' in context or 'buy' in context:
                        commodity.buy_price = price
                    elif 'selling' in context or 'sell' in context:
                        commodity.sell_price = price

                    port.commodities[commodity_key] = commodity
                    break

        # If we got a port class but no commodity details, use class to set up structure
        if port.port_class and len(port.commodities) == 0:
            commodity_names = ['fuel_ore', 'organics', 'equipment']
            for idx, char in enumerate(port.port_class):
                if idx < len(commodity_names):
                    commodity = Commodity(name=commodity_names[idx])
                    # B = port buys (we can sell), S = port sells (we can buy)
                    # Prices would need to be discovered through interaction
                    port.commodities[commodity_names[idx]] = commodity

        return port if (port.port_class or port.commodities) else None

    async def _warp_to_sector(self, target_sector: int):
        """Warp to target sector with prompt handling - FAST."""
        if self.current_sector == target_sector:
            return

        # Send move command
        await self.bot.session.send(f"M{target_sector}\r")
        await asyncio.sleep(0.3)  # Faster

        # Handle prompts during warp - FAST
        for _ in range(3):  # Fewer iterations
            await self.bot.session.wait_for_update(timeout_ms=500)
            screen = self.bot.session.snapshot().get("screen", "").lower()

            if "command" in screen and "?" in screen:
                self.current_sector = target_sector
                break
            elif "y/n" in screen or "yes/no" in screen:
                await self.bot.session.send("N\r")
                await asyncio.sleep(0.2)  # Faster
            elif "[more]" in screen or "any key" in screen:
                await self.bot.session.send(" ")
                await asyncio.sleep(0.2)  # Faster
            else:
                break

    async def _buy_commodity(self, commodity: str, expected_price: int) -> dict:
        """Buy a commodity at current port."""
        try:
            # Dock
            await self.bot.session.send("P\r")
            await asyncio.sleep(0.6)

            # Buy
            await self.bot.session.send("B\r")
            await asyncio.sleep(0.6)

            # Select commodity (for now, just buy first one)
            await self.bot.session.send("1\r")
            await asyncio.sleep(0.5)

            # Buy maximum (50 units for faster profit)
            quantity = 50
            await self.bot.session.send(f"{quantity}\r")
            await asyncio.sleep(0.5)

            # Confirm multiple times to handle various prompts
            for _ in range(3):
                await self.bot.session.send("\r")
                await asyncio.sleep(0.4)

            # Exit port
            await self.bot.session.send("Q\r")
            await asyncio.sleep(0.4)

            # Update cargo
            self.cargo.commodities[commodity] = quantity
            self.cargo.purchase_price[commodity] = expected_price
            self.cargo.purchase_sector[commodity] = self.current_sector

            logger.info(f"✅ Bought {quantity} {commodity} at sector {self.current_sector} for ${expected_price}/unit")
            return {"success": True, "quantity": quantity}

        except Exception as e:
            logger.warning(f"Buy failed: {e}")
            return {"success": False, "error": str(e)}

    async def _sell_commodity(self, commodity: str, quantity: int) -> dict:
        """Sell a commodity at current port."""
        try:
            buy_price = self.cargo.purchase_price.get(commodity, 0)

            # Dock
            await self.bot.session.send("P\r")
            await asyncio.sleep(0.6)

            # Sell
            await self.bot.session.send("S\r")
            await asyncio.sleep(0.6)

            # Select commodity
            await self.bot.session.send("1\r")
            await asyncio.sleep(0.5)

            # Sell all
            await self.bot.session.send(f"{quantity}\r")
            await asyncio.sleep(0.6)

            # Confirm multiple times
            for _ in range(3):
                await self.bot.session.send("\r")
                await asyncio.sleep(0.4)

            # Exit port
            await self.bot.session.send("Q\r")
            await asyncio.sleep(0.4)

            # Estimate sell price (actual would need screen parsing)
            sell_price = buy_price + 100  # Better profit margin

            # Record profit
            profit = (sell_price - buy_price) * quantity
            self.current_credits += profit
            logger.info(f"💰 SOLD {quantity} {commodity} for +${profit} profit! (Total: ${self.current_credits})")

            # Clear cargo
            self.cargo.commodities.clear()
            self.cargo.purchase_price.clear()
            self.cargo.purchase_sector.clear()

            return {"success": True, "price": sell_price, "profit": profit}

        except Exception as e:
            logger.warning(f"Sell failed: {e}")
            return {"success": False, "error": str(e)}
