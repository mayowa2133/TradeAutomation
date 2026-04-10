import type {
  BacktestResult,
  ConfigResponse,
  DashboardSummary,
  LLMDecision,
  Order,
  OrderBookSnapshot,
  Position,
  Trade,
} from './types'

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => ({ detail: response.statusText }))) as {
      detail?: string
    }
    throw new Error(body.detail ?? `Request failed: ${response.status}`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function getDashboardSummary() {
  return requestJson<DashboardSummary>('/api/v1/dashboard/summary')
}

export function getConfig() {
  return requestJson<ConfigResponse>('/api/v1/config')
}

export function getPositions() {
  return requestJson<Position[]>('/api/v1/positions')
}

export function getOrders() {
  return requestJson<Order[]>('/api/v1/orders')
}

export function getTrades() {
  return requestJson<Trade[]>('/api/v1/trades')
}

export function getDepth(symbol: string) {
  const query = new URLSearchParams({
    symbol,
    instrument_type: 'perpetual',
  })
  return requestJson<OrderBookSnapshot>(`/api/v1/market/depth?${query.toString()}`)
}

export function runBacktest(payload: Record<string, unknown>) {
  return requestJson<BacktestResult>('/api/v1/backtests/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function submitManualOrder(payload: Record<string, unknown>) {
  return requestJson<Order>('/api/v1/orders/manual', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function toggleStrategy(name: string, enabled: boolean) {
  return requestJson<{ name: string; enabled: boolean; updated_at: string }>(
    `/api/v1/strategies/${name}/toggle`,
    {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    },
  )
}

export function closePosition(positionId: number) {
  return requestJson<{ message: string }>(`/api/v1/positions/${positionId}/close`, {
    method: 'POST',
  })
}

export function cancelOrder(orderId: number) {
  return requestJson<{ order_id: number; status: string; message: string }>(
    `/api/v1/orders/${orderId}/cancel`,
    {
      method: 'POST',
    },
  )
}

export function runOptimizer(symbols: string[]) {
  return requestJson<Record<string, unknown>>('/api/v1/optimizer/run', {
    method: 'POST',
    body: JSON.stringify({ symbols, timeframe: '5m' }),
  })
}

export function requestLlmDecision(symbol: string) {
  return requestJson<LLMDecision>('/api/v1/llm/decisions', {
    method: 'POST',
    body: JSON.stringify({ symbol, timeframe: '5m' }),
  })
}
