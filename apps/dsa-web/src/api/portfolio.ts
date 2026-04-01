import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  PortfolioAccountItem,
  PortfolioAccountCreateRequest,
  PortfolioAccountListResponse,
  PortfolioCashLedgerCreateRequest,
  PortfolioCashLedgerListResponse,
  PortfolioCorporateActionCreateRequest,
  PortfolioCorporateActionListResponse,
  PortfolioCorporateActionType,
  PortfolioCostMethod,
  PortfolioDeleteResponse,
  PortfolioEventCreatedResponse,
  PortfolioFxRefreshResponse,
  PortfolioImportBrokerListResponse,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioRiskResponse,
  PortfolioSnapshotResponse,
  PortfolioTradeCreateRequest,
  PortfolioTradeListResponse,
  PortfolioWebSocketMessage,
} from '../types/portfolio';

type SnapshotQuery = {
  accountId?: number;
  asOf?: string;
  costMethod?: PortfolioCostMethod;
  useRealtime?: boolean;
  saveToDb?: boolean;
};

type FxRefreshQuery = {
  accountId?: number;
  asOf?: string;
};

type EventQuery = {
  accountId?: number;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
};

type TradeListQuery = EventQuery & {
  symbol?: string;
  side?: 'buy' | 'sell';
};

type CashListQuery = EventQuery & {
  direction?: 'in' | 'out';
};

type CorporateListQuery = EventQuery & {
  symbol?: string;
  actionType?: PortfolioCorporateActionType;
};

function buildSnapshotParams(query: SnapshotQuery): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.asOf) {
    params.as_of = query.asOf;
  }
  if (query.costMethod) {
    params.cost_method = query.costMethod;
  }
  if (query.useRealtime !== undefined) {
    params.use_realtime = query.useRealtime;
  }
  return params;
}

function buildFxRefreshParams(query: FxRefreshQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.asOf) {
    params.as_of = query.asOf;
  }
  return params;
}

function buildEventParams(query: EventQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.dateFrom) {
    params.date_from = query.dateFrom;
  }
  if (query.dateTo) {
    params.date_to = query.dateTo;
  }
  if (query.page != null) {
    params.page = query.page;
  }
  if (query.pageSize != null) {
    params.page_size = query.pageSize;
  }
  return params;
}

export const portfolioApi = {
  async getAccounts(includeInactive = false): Promise<PortfolioAccountListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/accounts', {
      params: { include_inactive: includeInactive },
    });
    return toCamelCase<PortfolioAccountListResponse>(response.data);
  },

  async createAccount(payload: PortfolioAccountCreateRequest): Promise<PortfolioAccountItem> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/accounts', {
      name: payload.name,
      broker: payload.broker,
      market: payload.market,
      base_currency: payload.baseCurrency,
      owner_id: payload.ownerId,
    });
    return toCamelCase<PortfolioAccountItem>(response.data);
  },

  async getSnapshot(query: SnapshotQuery = {}): Promise<PortfolioSnapshotResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/snapshot', {
      params: buildSnapshotParams(query),
    });
    return toCamelCase<PortfolioSnapshotResponse>(response.data);
  },

  async getRisk(query: SnapshotQuery = {}): Promise<PortfolioRiskResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/risk', {
      params: buildSnapshotParams(query),
    });
    return toCamelCase<PortfolioRiskResponse>(response.data);
  },

  async refreshFx(query: FxRefreshQuery = {}): Promise<PortfolioFxRefreshResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/fx/refresh', undefined, {
      params: buildFxRefreshParams(query),
    });
    return toCamelCase<PortfolioFxRefreshResponse>(response.data);
  },

  async createTrade(payload: PortfolioTradeCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/trades', {
      account_id: payload.accountId,
      symbol: payload.symbol,
      trade_date: payload.tradeDate,
      side: payload.side,
      quantity: payload.quantity,
      price: payload.price,
      fee: payload.fee ?? 0,
      tax: payload.tax ?? 0,
      market: payload.market,
      currency: payload.currency,
      trade_uid: payload.tradeUid,
      note: payload.note,
    });
    return toCamelCase<PortfolioEventCreatedResponse>(response.data);
  },

  async deleteTrade(tradeId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/trades/${tradeId}`);
    return toCamelCase<PortfolioDeleteResponse>(response.data);
  },

  async createCashLedger(payload: PortfolioCashLedgerCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/cash-ledger', {
      account_id: payload.accountId,
      event_date: payload.eventDate,
      direction: payload.direction,
      amount: payload.amount,
      currency: payload.currency,
      note: payload.note,
    });
    return toCamelCase<PortfolioEventCreatedResponse>(response.data);
  },

  async deleteCashLedger(entryId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/cash-ledger/${entryId}`);
    return toCamelCase<PortfolioDeleteResponse>(response.data);
  },

  async createCorporateAction(payload: PortfolioCorporateActionCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/corporate-actions', {
      account_id: payload.accountId,
      symbol: payload.symbol,
      effective_date: payload.effectiveDate,
      action_type: payload.actionType,
      market: payload.market,
      currency: payload.currency,
      cash_dividend_per_share: payload.cashDividendPerShare,
      split_ratio: payload.splitRatio,
      bonus_quantity: payload.bonusQuantity,
      note: payload.note,
    });
    return toCamelCase<PortfolioEventCreatedResponse>(response.data);
  },

  async deleteCorporateAction(actionId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/corporate-actions/${actionId}`);
    return toCamelCase<PortfolioDeleteResponse>(response.data);
  },

  async listTrades(query: TradeListQuery = {}): Promise<PortfolioTradeListResponse> {
    const params = buildEventParams(query);
    if (query.symbol) {
      params.symbol = query.symbol;
    }
    if (query.side) {
      params.side = query.side;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/trades', { params });
    return toCamelCase<PortfolioTradeListResponse>(response.data);
  },

  async listCashLedger(query: CashListQuery = {}): Promise<PortfolioCashLedgerListResponse> {
    const params = buildEventParams(query);
    if (query.direction) {
      params.direction = query.direction;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/cash-ledger', { params });
    return toCamelCase<PortfolioCashLedgerListResponse>(response.data);
  },

  async listCorporateActions(query: CorporateListQuery = {}): Promise<PortfolioCorporateActionListResponse> {
    const params = buildEventParams(query);
    if (query.symbol) {
      params.symbol = query.symbol;
    }
    if (query.actionType) {
      params.action_type = query.actionType;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/corporate-actions', { params });
    return toCamelCase<PortfolioCorporateActionListResponse>(response.data);
  },

  async listImportBrokers(): Promise<PortfolioImportBrokerListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/imports/csv/brokers');
    return toCamelCase<PortfolioImportBrokerListResponse>(response.data);
  },

  async parseCsvImport(broker: string, file: File): Promise<PortfolioImportParseResponse> {
    const formData = new FormData();
    formData.append('broker', broker);
    formData.append('file', file);
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/imports/csv/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return toCamelCase<PortfolioImportParseResponse>(response.data);
  },

  async commitCsvImport(
    accountId: number,
    broker: string,
    file: File,
    dryRun = false,
  ): Promise<PortfolioImportCommitResponse> {
    const formData = new FormData();
    formData.append('account_id', String(accountId));
    formData.append('broker', broker);
    formData.append('dry_run', dryRun ? 'true' : 'false');
    formData.append('file', file);
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/imports/csv/commit', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return toCamelCase<PortfolioImportCommitResponse>(response.data);
  },
};

/**
 * WebSocket client for real-time portfolio price updates.
 *
 * Usage:
 * ```typescript
 * const wsClient = new PortfolioWebSocketClient();
 *
 * // Subscribe to price updates
 * wsClient.connect();
 * wsClient.subscribe(['600519', '000001'], (update) => {
 *   console.log('Price update:', update);
 * });
 *
 * // Cleanup on unmount
 * return () => wsClient.disconnect();
 * ```
 */
export class PortfolioWebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 3000; // 3 seconds
  private maxReconnectAttempts = 10;
  private reconnectAttempts = 0;
  private subscribedSymbols: string[] = [];
  private messageHandlers: Set<(message: PortfolioWebSocketMessage) => void> = new Set();
  private isManualDisconnect = false;

  /**
   * Connect to the WebSocket server.
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log('[PortfolioWebSocket] Already connected');
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/v1/portfolio/ws/realtime`;

    console.log('[PortfolioWebSocket] Connecting to:', wsUrl);

    try {
      this.ws = new WebSocket(wsUrl);
      this.setupEventHandlers();
    } catch (error) {
      console.error('[PortfolioWebSocket] Connection error:', error);
      this.scheduleReconnect();
    }
  }

  /**
   * Disconnect from the WebSocket server.
   */
  disconnect(): void {
    this.isManualDisconnect = true;
    this.clearReconnectTimer();

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.messageHandlers.clear();
    this.subscribedSymbols = [];
    this.reconnectAttempts = 0;
  }

  /**
   * Subscribe to price updates for the given symbols.
   *
   * @param symbols - List of stock symbols to track
   * @param onMessage - Callback for incoming messages
   */
  subscribe(symbols: string[], onMessage: (message: PortfolioWebSocketMessage) => void): void {
    if (onMessage) {
      this.messageHandlers.add(onMessage);
    }

    this.subscribedSymbols = symbols;

    if (this.ws?.readyState === WebSocket.OPEN) {
      this.sendSubscribe(symbols);
    } else {
      // Will subscribe after connection is established
      this.connect();
    }
  }

  /**
   * Unsubscribe from price updates.
   *
   * @param symbols - Symbols to unsubscribe (empty array = unsubscribe all)
   */
  unsubscribe(symbols: string[] = []): void {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      return;
    }

    this.sendUnsubscribe(symbols);

    if (symbols.length === 0) {
      this.subscribedSymbols = [];
    } else {
      this.subscribedSymbols = this.subscribedSymbols.filter(s => !symbols.includes(s));
    }
  }

  /**
   * Update the subscribed symbols.
   *
   * @param symbols - New list of symbols to track
   */
  updateSymbols(symbols: string[]): void {
    this.subscribedSymbols = symbols;

    if (this.ws?.readyState === WebSocket.OPEN) {
      this.sendSubscribe(symbols);
    }
  }

  /**
   * Send a ping message to keep the connection alive.
   */
  ping(): void {
    this.sendMessage({ action: 'ping' });
  }

  /**
   * Check if the client is connected.
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('[PortfolioWebSocket] Connected');
      this.reconnectAttempts = 0;
      this.isManualDisconnect = false;

      // Subscribe to symbols after connection
      if (this.subscribedSymbols.length > 0) {
        this.sendSubscribe(this.subscribedSymbols);
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const message: PortfolioWebSocketMessage = JSON.parse(event.data);
        this.notifyHandlers(message);
      } catch (error) {
        console.error('[PortfolioWebSocket] Failed to parse message:', error);
      }
    };

    this.ws.onclose = (event) => {
      console.log('[PortfolioWebSocket] Disconnected:', event.code, event.reason);

      if (!this.isManualDisconnect) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error('[PortfolioWebSocket] Error:', error);
    };
  }

  private sendSubscribe(symbols: string[]): void {
    this.sendMessage({
      action: 'subscribe',
      symbols,
    });
  }

  private sendUnsubscribe(symbols: string[]): void {
    this.sendMessage({
      action: 'unsubscribe',
      symbols,
    });
  }

  private sendMessage(message: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  private notifyHandlers(message: PortfolioWebSocketMessage): void {
    this.messageHandlers.forEach(handler => {
      try {
        handler(message);
      } catch (error) {
        console.error('[PortfolioWebSocket] Handler error:', error);
      }
    });
  }

  private scheduleReconnect(): void {
    if (this.isManualDisconnect) {
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[PortfolioWebSocket] Max reconnect attempts reached');
      return;
    }

    this.clearReconnectTimer();

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++;
      console.log(
        `[PortfolioWebSocket] Reconnecting... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`
      );
      this.connect();
    }, this.reconnectDelay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
