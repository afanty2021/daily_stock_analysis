# -*- coding: utf-8 -*-
"""
Real-time price service for WebSocket streaming.

This module provides async methods to fetch real-time stock prices
and push updates to connected WebSocket clients.

Features:
- Async concurrent price fetching using asyncio.gather
- Unified quote format for WebSocket transmission
- Per-symbol error handling
- Streaming support with configurable intervals
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from data_provider.base import DataFetcherManager, canonical_stock_code

logger = logging.getLogger(__name__)


class RealtimePriceService:
    """
    Service for fetching and broadcasting real-time stock prices.

    Features:
    - Async concurrent price fetching
    - Unified quote format
    - Error handling per symbol
    """

    def __init__(self, fetcher_manager: Optional[DataFetcherManager] = None):
        """
        Initialize the realtime price service.

        Args:
            fetcher_manager: Optional DataFetcherManager instance
        """
        self.fetcher_manager = fetcher_manager or DataFetcherManager()

    async def fetch_realtime_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch real-time price for a single symbol (async wrapper).

        Args:
            symbol: Stock symbol (e.g., '600519', 'HK00700', 'AAPL')

        Returns:
            Dict with price data or None if fetch failed
        """
        loop = asyncio.get_event_loop()

        def _fetch():
            try:
                quote = self.fetcher_manager.get_realtime_quote(symbol)
                if quote is None:
                    return None

                return {
                    "symbol": canonical_stock_code(symbol),
                    "name": getattr(quote, "name", None),
                    "price": float(getattr(quote, "price", 0) or 0),
                    "change": float(getattr(quote, "change_amount", 0) or 0),
                    "change_pct": float(getattr(quote, "change_pct", 0) or 0),
                    "open": float(getattr(quote, "open_price", 0) or 0),
                    "high": float(getattr(quote, "high", 0) or 0),
                    "low": float(getattr(quote, "low", 0) or 0),
                    "prev_close": float(getattr(quote, "pre_close", 0) or 0),
                    "volume": int(getattr(quote, "volume", 0) or 0),
                    "amount": float(getattr(quote, "amount", 0) or 0),
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.warning(f"Failed to fetch realtime price for {symbol}: {e}")
                return None

        return await loop.run_in_executor(None, _fetch)

    async def fetch_realtime_prices(
        self, symbols: List[str]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Fetch real-time prices for multiple symbols concurrently.

        Args:
            symbols: List of stock symbols

        Returns:
            Dict mapping symbol to price data (None if failed)
        """
        if not symbols:
            return {}

        # Normalize symbols
        normalized_symbols = [canonical_stock_code(s) for s in symbols if s]

        # Create tasks for concurrent fetching
        tasks = [self.fetch_realtime_price(symbol) for symbol in normalized_symbols]

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dictionary
        price_map = {}
        for symbol, result in zip(normalized_symbols, results):
            if isinstance(result, Exception):
                logger.warning(f"Exception fetching {symbol}: {result}")
                price_map[symbol] = None
            else:
                price_map[symbol] = result

        return price_map

    def format_price_update(self, symbol: str, price_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format price data for WebSocket transmission.

        Args:
            symbol: Stock symbol
            price_data: Raw price data

        Returns:
            Formatted update message
        """
        if price_data is None:
            return {
                "type": "price_update",
                "symbol": symbol,
                "success": False,
                "error": "Failed to fetch price",
            }

        return {
            "type": "price_update",
            "symbol": symbol,
            "success": True,
            "data": {
                "symbol": price_data.get("symbol"),
                "name": price_data.get("name"),
                "price": price_data.get("price"),
                "change": price_data.get("change"),
                "change_pct": price_data.get("change_pct"),
                "open": price_data.get("open"),
                "high": price_data.get("high"),
                "low": price_data.get("low"),
                "prev_close": price_data.get("prev_close"),
                "volume": price_data.get("volume"),
                "amount": price_data.get("amount"),
                "timestamp": price_data.get("timestamp"),
            },
        }

    async def stream_prices(
        self,
        symbols: List[str],
        callback,
        interval_seconds: int = 5,
        max_iterations: Optional[int] = None,
    ):
        """
        Stream price updates at regular intervals.

        Args:
            symbols: List of stock symbols to track
            callback: Async callback function to receive updates
                     Signature: async callback(update: Dict[str, Any])
            interval_seconds: Interval between price updates
            max_iterations: Maximum number of iterations (None for infinite)
        """
        iteration = 0

        while max_iterations is None or iteration < max_iterations:
            try:
                # Fetch prices
                price_map = await self.fetch_realtime_prices(symbols)

                # Send updates for each symbol
                for symbol, price_data in price_map.items():
                    update = self.format_price_update(symbol, price_data)
                    try:
                        await callback(update)
                    except Exception as e:
                        logger.error(f"Error in callback for {symbol}: {e}")

                iteration += 1

                # Wait before next update
                if max_iterations is None or iteration < max_iterations:
                    await asyncio.sleep(interval_seconds)

            except asyncio.CancelledError:
                logger.info("Price streaming cancelled")
                break
            except Exception as e:
                logger.error(f"Error in price streaming: {e}")
                await asyncio.sleep(interval_seconds)
