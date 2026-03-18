# -*- coding: utf-8 -*-
"""Portfolio endpoints (P0 core account + snapshot workflow)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.portfolio import (
    PortfolioAccountCreateRequest,
    PortfolioAccountItem,
    PortfolioAccountListResponse,
    PortfolioAccountUpdateRequest,
    PortfolioCashLedgerListResponse,
    PortfolioCashLedgerCreateRequest,
    PortfolioCorporateActionListResponse,
    PortfolioCorporateActionCreateRequest,
    PortfolioEventCreatedResponse,
    PortfolioFxRefreshResponse,
    PortfolioImportBrokerListResponse,
    PortfolioImportCommitResponse,
    PortfolioImportParseResponse,
    PortfolioImportTradeItem,
    PortfolioRiskResponse,
    PortfolioSnapshotResponse,
    PortfolioTradeListResponse,
    PortfolioTradeCreateRequest,
)
from src.services.portfolio_import_service import PortfolioImportService
from src.services.portfolio_risk_service import PortfolioRiskService
from src.services.portfolio_service import PortfolioConflictError, PortfolioService
from src.services.realtime_price_service import RealtimePriceService

logger = logging.getLogger(__name__)

router = APIRouter()

# WebSocket connection manager
class ConnectionManager:
    """Manage active WebSocket connections for real-time price updates."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific WebSocket connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending message to WebSocket: {e}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all active connections."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)

        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


# Global connection manager instance
connection_manager = ConnectionManager()


async def _safe_send_json(websocket: WebSocket, message: dict) -> bool:
    """
    Safely send a JSON message to a WebSocket, checking connection state first.

    Returns True if the message was sent successfully, False otherwise.
    """
    if websocket.client_state.name != "connected":
        return False

    try:
        await websocket.send_json(message)
        return True
    except Exception as e:
        logger.debug(f"Failed to send WebSocket message: {e}")
        return False


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"error": "validation_error", "message": str(exc)},
    )


def _internal_error(message: str, exc: Exception) -> HTTPException:
    logger.error(f"{message}: {exc}", exc_info=True)
    return HTTPException(
        status_code=500,
        detail={"error": "internal_error", "message": f"{message}: {str(exc)}"},
    )


def _serialize_import_record(item: dict) -> PortfolioImportTradeItem:
    payload = dict(item)
    trade_date = payload.get("trade_date")
    if isinstance(trade_date, date):
        payload["trade_date"] = trade_date.isoformat()
    else:
        payload["trade_date"] = str(trade_date)
    return PortfolioImportTradeItem(**payload)


@router.post(
    "/accounts",
    response_model=PortfolioAccountItem,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Create portfolio account",
)
def create_account(request: PortfolioAccountCreateRequest) -> PortfolioAccountItem:
    service = PortfolioService()
    try:
        row = service.create_account(
            name=request.name,
            broker=request.broker,
            market=request.market,
            base_currency=request.base_currency,
            owner_id=request.owner_id,
        )
        return PortfolioAccountItem(**row)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create account failed", exc)


@router.get(
    "/accounts",
    response_model=PortfolioAccountListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="List portfolio accounts",
)
def list_accounts(
    include_inactive: bool = Query(False, description="Whether to include inactive accounts"),
) -> PortfolioAccountListResponse:
    service = PortfolioService()
    try:
        rows = service.list_accounts(include_inactive=include_inactive)
        return PortfolioAccountListResponse(accounts=[PortfolioAccountItem(**item) for item in rows])
    except Exception as exc:
        raise _internal_error("List accounts failed", exc)


@router.put(
    "/accounts/{account_id}",
    response_model=PortfolioAccountItem,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Update portfolio account",
)
def update_account(account_id: int, request: PortfolioAccountUpdateRequest) -> PortfolioAccountItem:
    service = PortfolioService()
    try:
        updated = service.update_account(
            account_id,
            name=request.name,
            broker=request.broker,
            market=request.market,
            base_currency=request.base_currency,
            owner_id=request.owner_id,
            is_active=request.is_active,
        )
        if updated is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"Account not found: {account_id}"},
            )
        return PortfolioAccountItem(**updated)
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Update account failed", exc)


@router.delete(
    "/accounts/{account_id}",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Deactivate portfolio account",
)
def delete_account(account_id: int):
    service = PortfolioService()
    try:
        ok = service.deactivate_account(account_id)
        if not ok:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"Account not found: {account_id}"},
            )
        return {"deleted": 1}
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error("Deactivate account failed", exc)


@router.post(
    "/trades",
    response_model=PortfolioEventCreatedResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Record trade event",
)
def create_trade(request: PortfolioTradeCreateRequest) -> PortfolioEventCreatedResponse:
    service = PortfolioService()
    try:
        data = service.record_trade(
            account_id=request.account_id,
            symbol=request.symbol,
            trade_date=request.trade_date,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            fee=request.fee,
            tax=request.tax,
            market=request.market,
            currency=request.currency,
            trade_uid=request.trade_uid,
            note=request.note,
        )
        return PortfolioEventCreatedResponse(**data)
    except PortfolioConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "conflict", "message": str(exc)},
        )
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create trade failed", exc)


@router.get(
    "/trades",
    response_model=PortfolioTradeListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List trade events",
)
def list_trades(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    date_from: Optional[date] = Query(None, description="Trade date from"),
    date_to: Optional[date] = Query(None, description="Trade date to"),
    symbol: Optional[str] = Query(None, description="Optional stock symbol filter"),
    side: Optional[str] = Query(None, description="Optional side filter: buy/sell"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PortfolioTradeListResponse:
    service = PortfolioService()
    try:
        data = service.list_trade_events(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbol=symbol,
            side=side,
            page=page,
            page_size=page_size,
        )
        return PortfolioTradeListResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("List trade events failed", exc)


@router.post(
    "/cash-ledger",
    response_model=PortfolioEventCreatedResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Record cash event",
)
def create_cash_ledger(request: PortfolioCashLedgerCreateRequest) -> PortfolioEventCreatedResponse:
    service = PortfolioService()
    try:
        data = service.record_cash_ledger(
            account_id=request.account_id,
            event_date=request.event_date,
            direction=request.direction,
            amount=request.amount,
            currency=request.currency,
            note=request.note,
        )
        return PortfolioEventCreatedResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create cash ledger event failed", exc)


@router.get(
    "/cash-ledger",
    response_model=PortfolioCashLedgerListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List cash ledger events",
)
def list_cash_ledger(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    date_from: Optional[date] = Query(None, description="Cash event date from"),
    date_to: Optional[date] = Query(None, description="Cash event date to"),
    direction: Optional[str] = Query(None, description="Optional direction filter: in/out"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PortfolioCashLedgerListResponse:
    service = PortfolioService()
    try:
        data = service.list_cash_ledger_events(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            direction=direction,
            page=page,
            page_size=page_size,
        )
        return PortfolioCashLedgerListResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("List cash ledger events failed", exc)


@router.post(
    "/corporate-actions",
    response_model=PortfolioEventCreatedResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Record corporate action event",
)
def create_corporate_action(request: PortfolioCorporateActionCreateRequest) -> PortfolioEventCreatedResponse:
    service = PortfolioService()
    try:
        data = service.record_corporate_action(
            account_id=request.account_id,
            symbol=request.symbol,
            effective_date=request.effective_date,
            action_type=request.action_type,
            market=request.market,
            currency=request.currency,
            cash_dividend_per_share=request.cash_dividend_per_share,
            split_ratio=request.split_ratio,
            note=request.note,
        )
        return PortfolioEventCreatedResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create corporate action event failed", exc)


@router.get(
    "/corporate-actions",
    response_model=PortfolioCorporateActionListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List corporate action events",
)
def list_corporate_actions(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    date_from: Optional[date] = Query(None, description="Corporate action effective date from"),
    date_to: Optional[date] = Query(None, description="Corporate action effective date to"),
    symbol: Optional[str] = Query(None, description="Optional stock symbol filter"),
    action_type: Optional[str] = Query(None, description="Optional action type filter"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PortfolioCorporateActionListResponse:
    service = PortfolioService()
    try:
        data = service.list_corporate_action_events(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbol=symbol,
            action_type=action_type,
            page=page,
            page_size=page_size,
        )
        return PortfolioCorporateActionListResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("List corporate action events failed", exc)


@router.get(
    "/snapshot",
    response_model=PortfolioSnapshotResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get portfolio snapshot",
)
def get_snapshot(
    account_id: Optional[int] = Query(None, description="Optional account id, default returns all accounts"),
    as_of: Optional[date] = Query(None, description="Snapshot date, default today"),
    cost_method: str = Query("fifo", description="Cost method: fifo or avg"),
    use_realtime: bool = Query(False, description="Use realtime quotes for prices (slower)"),
    save_to_db: bool = Query(False, description="Save snapshot to database (default false for web view)"),
) -> PortfolioSnapshotResponse:
    service = PortfolioService()
    try:
        data = service.get_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            use_realtime=use_realtime,
            save_to_db=save_to_db,
        )
        return PortfolioSnapshotResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Get snapshot failed", exc)


@router.post(
    "/imports/csv/parse",
    response_model=PortfolioImportParseResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Parse broker CSV into normalized trade records",
)
def parse_csv_import(
    broker: str = Form(..., description="Broker id: huatai/citic/cmb"),
    file: UploadFile = File(...),
) -> PortfolioImportParseResponse:
    importer = PortfolioImportService()
    try:
        content = file.file.read()
        parsed = importer.parse_trade_csv(broker=broker, content=content)
        return PortfolioImportParseResponse(
            broker=parsed["broker"],
            record_count=parsed["record_count"],
            skipped_count=parsed["skipped_count"],
            error_count=parsed["error_count"],
            records=[_serialize_import_record(item) for item in parsed.get("records", [])],
            errors=list(parsed.get("errors", [])),
        )
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Parse CSV import failed", exc)


@router.get(
    "/imports/csv/brokers",
    response_model=PortfolioImportBrokerListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="List supported broker CSV parsers",
)
def list_csv_brokers() -> PortfolioImportBrokerListResponse:
    importer = PortfolioImportService()
    try:
        return PortfolioImportBrokerListResponse(brokers=importer.list_supported_brokers())
    except Exception as exc:
        raise _internal_error("List CSV brokers failed", exc)


@router.post(
    "/imports/csv/commit",
    response_model=PortfolioImportCommitResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Parse and commit broker CSV with dedup",
)
def commit_csv_import(
    account_id: int = Form(...),
    broker: str = Form(..., description="Broker id: huatai/citic/cmb"),
    dry_run: bool = Form(False),
    file: UploadFile = File(...),
) -> PortfolioImportCommitResponse:
    importer = PortfolioImportService()
    try:
        content = file.file.read()
        parsed = importer.parse_trade_csv(broker=broker, content=content)
        result = importer.commit_trade_records(
            account_id=account_id,
            broker=parsed["broker"],
            records=list(parsed.get("records", [])),
            dry_run=dry_run,
        )
        return PortfolioImportCommitResponse(**result)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Commit CSV import failed", exc)


@router.post(
    "/fx/refresh",
    response_model=PortfolioFxRefreshResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Refresh FX cache online with stale fallback",
)
def refresh_fx_rates(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="Rate date, default today"),
) -> PortfolioFxRefreshResponse:
    service = PortfolioService()
    try:
        data = service.refresh_fx_rates(account_id=account_id, as_of=as_of)
        return PortfolioFxRefreshResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Refresh FX rates failed", exc)


@router.get(
    "/risk",
    response_model=PortfolioRiskResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get portfolio risk report",
)
def get_risk_report(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="Risk report date, default today"),
    cost_method: str = Query("fifo", description="Cost method: fifo or avg"),
) -> PortfolioRiskResponse:
    service = PortfolioRiskService()
    try:
        data = service.get_risk_report(account_id=account_id, as_of=as_of, cost_method=cost_method)
        return PortfolioRiskResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Get risk report failed", exc)


@router.websocket("/ws/realtime")
async def websocket_realtime_prices(websocket: WebSocket):
    """
    WebSocket endpoint for real-time portfolio price updates.

    Protocol:
    1. Client connects
    2. Client sends JSON message with symbols to track:
       {"action": "subscribe", "symbols": ["600519", "000001", "HK00700"]}
    3. Server streams price updates every 5 seconds:
       {"type": "price_update", "symbol": "600519", "success": true, "data": {...}}

    Example:
        const ws = new WebSocket('ws://localhost:8000/api/v1/portfolio/ws/realtime');
        ws.onopen = () => {
            ws.send(JSON.stringify({action: 'subscribe', symbols: ['600519', '000001']}));
        };
        ws.onmessage = (event) => {
            const update = JSON.parse(event.data);
            console.log('Price update:', update);
        };
    """
    await connection_manager.connect(websocket)
    price_service = RealtimePriceService()
    subscribed_symbols: List[str] = []
    streaming_task = None

    try:
        # Send welcome message
        await _safe_send_json(websocket, {
            "type": "connected",
            "message": "Connected to real-time price feed",
            "timestamp": asyncio.get_event_loop().time(),
        })

        # Handle client messages
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)

                action = message.get("action")

                if action == "subscribe":
                    # Subscribe to symbols
                    new_symbols = message.get("symbols", [])
                    if not isinstance(new_symbols, list):
                        await _safe_send_json(websocket, {
                            "type": "error",
                            "message": "symbols must be a list",
                        })
                        continue

                    # Update subscribed symbols
                    subscribed_symbols = new_symbols

                    # Send initial prices immediately
                    if subscribed_symbols:
                        price_map = await price_service.fetch_realtime_prices(subscribed_symbols)
                        for symbol, price_data in price_map.items():
                            if not await _safe_send_json(
                                websocket,
                                price_service.format_price_update(symbol, price_data)
                            ):
                                break

                    # Start streaming if not already running
                    if streaming_task is None or streaming_task.done():
                        streaming_task = asyncio.create_task(
                            _stream_prices(websocket, price_service, subscribed_symbols)
                        )

                    await _safe_send_json(websocket, {
                        "type": "subscribed",
                        "symbols": subscribed_symbols,
                        "count": len(subscribed_symbols),
                    })

                elif action == "unsubscribe":
                    # Unsubscribe from specific symbols or all
                    symbols_to_remove = message.get("symbols", [])

                    if not symbols_to_remove:
                        # Unsubscribe from all
                        subscribed_symbols = []
                        if streaming_task and not streaming_task.done():
                            streaming_task.cancel()
                            try:
                                await streaming_task
                            except asyncio.CancelledError:
                                pass
                    else:
                        # Unsubscribe from specific symbols
                        subscribed_symbols = [
                            s for s in subscribed_symbols if s not in symbols_to_remove
                        ]

                    await _safe_send_json(websocket, {
                        "type": "unsubscribed",
                        "symbols": subscribed_symbols,
                        "count": len(subscribed_symbols),
                    })

                elif action == "ping":
                    # Respond to ping with pong
                    await _safe_send_json(websocket, {
                        "type": "pong",
                        "timestamp": asyncio.get_event_loop().time(),
                    })

                else:
                    await _safe_send_json(websocket, {
                        "type": "error",
                        "message": f"Unknown action: {action}",
                    })

            except json.JSONDecodeError:
                # 检查连接状态后再发送错误响应
                if websocket.client_state.name == "connected":
                    await _safe_send_json(websocket, {
                        "type": "error",
                        "message": "Invalid JSON message",
                    })
            except Exception as e:
                # 检查是否是断开异常，避免在断开后尝试发送
                if "disconnect" in str(e).lower() or websocket.client_state.name != "connected":
                    logger.info(f"WebSocket disconnected, skipping error response: {e}")
                    raise  # 重新抛出让外层处理
                logger.error(f"Error handling WebSocket message: {e}")
                if websocket.client_state.name == "connected":
                    await _safe_send_json(websocket, {
                        "type": "error",
                        "message": str(e),
                    })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Clean up
        if streaming_task and not streaming_task.done():
            streaming_task.cancel()
            try:
                await streaming_task
            except asyncio.CancelledError:
                pass

        connection_manager.disconnect(websocket)


async def _stream_prices(
    websocket: WebSocket,
    price_service: RealtimePriceService,
    symbols: List[str],
    interval_seconds: int = 5,
):
    """
    Internal function to stream price updates at regular intervals.

    This function runs as a background task and sends price updates
    to the WebSocket client every `interval_seconds` seconds.
    """
    try:
        while True:
            # Check if connection is still open before each iteration
            if websocket.client_state.name != "connected":
                logger.info("WebSocket connection closed, stopping stream")
                break

            if not symbols:
                await asyncio.sleep(interval_seconds)
                continue

            try:
                # Fetch prices for all subscribed symbols
                price_map = await price_service.fetch_realtime_prices(symbols)

                # Send updates for each symbol
                for symbol, price_data in price_map.items():
                    if not await _safe_send_json(
                        websocket,
                        price_service.format_price_update(symbol, price_data)
                    ):
                        # Connection closed, stop streaming
                        return

            except Exception as e:
                logger.error(f"Error streaming prices: {e}")
                # Try to send error message
                sent = await _safe_send_json(websocket, {
                    "type": "error",
                    "message": f"Error fetching prices: {str(e)}",
                })
                if not sent:
                    # Connection closed, stop streaming
                    return
                # Break the loop on error to avoid continuous errors
                break

            # Wait before next update
            await asyncio.sleep(interval_seconds)

    except asyncio.CancelledError:
        logger.info("Price streaming cancelled")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in price streaming: {e}")
