export type SectionKey =
  | 'overview'
  | 'market'
  | 'execution'
  | 'research'
  | 'news-ai'
  | 'settings'

export interface StrategyDescriptor {
  name: string
  description: string
  experimental: boolean
  enabled: boolean
  parameters: Record<string, unknown>
}

export interface PortfolioSummary {
  currency: string
  starting_balance: number
  cash_balance: number
  realized_pnl: number
  unrealized_pnl: number
  equity: number
  peak_equity: number
  drawdown_pct: number
  margin_used: number
  gross_exposure: number
  net_exposure: number
}

export interface RiskSummary {
  kill_switch: boolean
  live_trading_enabled: boolean
  open_positions: number
  max_concurrent_positions: number
  daily_realized_pnl: number
  daily_loss_limit: number
  drawdown_pct: number
  drawdown_limit_pct: number
  blocked_symbols: string[]
  equity: number
  cash_balance: number
  margin_used: number
  gross_exposure: number
  net_exposure: number
  max_gross_exposure_pct: number
  max_net_exposure_pct: number
  max_side_exposure_pct: number
  long_exposure: number
  short_exposure: number
}

export interface StreamStatusItem {
  stream_name: string
  symbol: string
  status: string
  stream_metadata?: Record<string, unknown>
  error_message?: string | null
  last_message_at?: string | null
}

export interface NewsItem {
  id?: number
  source: string
  title: string
  summary?: string | null
  url?: string
  symbols: string[]
  published_at?: string | null
}

export interface LLMDecision {
  id?: number
  provider?: string
  model?: string
  symbol?: string | null
  position_side?: string | null
  confidence: number
  accepted: boolean
  reason?: string | null
  prompt?: string
  context_payload?: Record<string, unknown>
  structured_output?: Record<string, unknown>
  created_at: string
}

export interface DashboardSummary {
  portfolio: PortfolioSummary
  risk: RiskSummary
  strategies: StrategyDescriptor[]
  stream_status: StreamStatusItem[]
  optimizer: Record<string, unknown> | null
  news: NewsItem[]
  llm_decisions: LLMDecision[]
  recent_events: Array<{
    event_type: string
    message: string
    created_at: string
  }>
}

export interface Position {
  id: number
  strategy_name: string
  symbol: string
  instrument_type: string
  margin_mode: string
  side: string
  mode: string
  status: string
  quantity: number
  leverage: number
  avg_entry_price: number
  current_price: number
  entry_notional: number
  collateral: number
  unrealized_pnl: number
  realized_pnl: number
  stop_loss_price?: number | null
  take_profit_price?: number | null
  liquidation_price?: number | null
  maintenance_margin_rate: number
  funding_cost: number
  exit_reason?: string | null
  opened_at: string
  closed_at?: string | null
  updated_at: string
}

export interface Order {
  id: number
  client_order_id: string
  exchange_order_id?: string | null
  strategy_name?: string | null
  symbol: string
  instrument_type: string
  margin_mode: string
  position_side: string
  source: string
  side: string
  order_type: string
  status: string
  mode: string
  quantity: number
  filled_quantity: number
  remaining_quantity: number
  limit_price?: number | null
  fill_price?: number | null
  fee_paid: number
  slippage_bps: number
  leverage: number
  reduce_only: boolean
  post_only: boolean
  tick_size?: number | null
  lot_size?: number | null
  min_notional?: number | null
  liquidation_price?: number | null
  funding_cost: number
  exchange_name: string
  notes?: string | null
  created_at: string
  updated_at: string
}

export interface Trade {
  id: number
  order_id: number
  position_id?: number | null
  strategy_name?: string | null
  symbol: string
  instrument_type: string
  margin_mode: string
  position_side: string
  source: string
  side: string
  action: string
  mode: string
  leverage: number
  price: number
  quantity: number
  notional: number
  fee_paid: number
  funding_cost: number
  realized_pnl: number
  cash_flow: number
  trade_time: string
  notes?: string | null
}

export interface ConfigResponse {
  settings: Record<string, unknown>
  trading_mode: string
  live_trading_enabled: boolean
}

export interface OrderBookSnapshot {
  exchange: string
  symbol: string
  instrument_type: string
  sequence?: number | null
  depth: number
  bids: number[][]
  asks: number[][]
  mid_price?: number | null
  snapshot_time: string
}

export interface BacktestTrade {
  entry_time: string
  exit_time: string
  instrument_type: string
  position_side: string
  leverage: number
  entry_price: number
  exit_price: number
  quantity: number
  gross_pnl: number
  net_pnl: number
  fees: number
  funding_paid: number
  exit_reason: string
}

export interface BacktestResult {
  strategy_name: string
  symbol: string
  timeframe: string
  instrument_type: string
  margin_mode: string
  execution_model: string
  trades: BacktestTrade[]
  equity_curve: Array<{ timestamp: string; equity: number }>
  total_trades: number
  win_rate: number
  total_return_pct: number
  sharpe_like: number
  max_drawdown_pct: number
  fees_paid: number
  funding_paid: number
  liquidation_count: number
  ending_balance: number
  ending_equity: number
}

export interface ExecutionSnapshot {
  positions: Array<{
    id: number
    symbol: string
    instrument_type: string
    side: string
    quantity: number
    entry_price: number
    current_price: number
    unrealized_pnl: number
    leverage: number
  }>
  orders: Array<{
    id: number
    symbol: string
    instrument_type: string
    status: string
    side: string
    position_side: string
    quantity: number
    filled_quantity: number
    fill_price?: number | null
    created_at: string
  }>
  trades: Array<{
    id: number
    symbol: string
    action: string
    position_side: string
    quantity: number
    price: number
    realized_pnl: number
    trade_time: string
  }>
}

export interface MarketSnapshot {
  symbol: string
  instrument_type: string
  quote?: {
    best_bid: number
    best_ask: number
    last_price?: number | null
    mark_price?: number | null
    funding_rate?: number | null
    spread_bps: number
    snapshot_time: string
  } | null
  orderbook?: {
    bids: number[][]
    asks: number[][]
    mid_price?: number | null
    snapshot_time: string
  } | null
  stream_status: StreamStatusItem[]
}
