import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const dashboardPayload = {
  portfolio: {
    currency: 'USDT',
    starting_balance: 100000,
    cash_balance: 98000,
    realized_pnl: 250,
    unrealized_pnl: 125,
    equity: 98375,
    peak_equity: 100000,
    drawdown_pct: 0.016,
    margin_used: 5000,
    gross_exposure: 10000,
    net_exposure: 4000,
  },
  risk: {
    kill_switch: false,
    live_trading_enabled: false,
    open_positions: 1,
    max_concurrent_positions: 3,
    daily_realized_pnl: 250,
    daily_loss_limit: -3000,
    drawdown_pct: 0.016,
    drawdown_limit_pct: 0.1,
    blocked_symbols: [],
    equity: 98375,
    cash_balance: 98000,
    margin_used: 5000,
    gross_exposure: 10000,
    net_exposure: 4000,
    max_gross_exposure_pct: 2,
    max_net_exposure_pct: 1,
    max_side_exposure_pct: 1.5,
    long_exposure: 10000,
    short_exposure: 0,
  },
  strategies: [],
  worker_status: {
    status: 'healthy',
    last_success_at: new Date().toISOString(),
    last_error_at: null,
    last_event_type: 'worker_job_success',
    last_event_message: 'evaluate_signals completed successfully.',
    stale_after_seconds: 360,
    recent_errors: [],
  },
  position_attribution: [],
  stream_status: [],
  optimizer: null,
  news: [],
  llm_decisions: [],
  recent_events: [],
}

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
    setTimeout(() => this.onopen?.(), 0)
  }

  close() {
    this.onclose?.()
  }
}

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        const payload =
          url.includes('/dashboard/summary')
            ? dashboardPayload
            : url.includes('/config')
              ? { settings: { stitch_project_id: '1872692140714476366' }, trading_mode: 'paper', live_trading_enabled: false }
              : url.includes('/positions')
                ? []
                : url.includes('/orders')
                  ? []
                  : url.includes('/trades')
                    ? []
                    : { exchange: 'bybit', symbol: 'BTC/USDT', instrument_type: 'perpetual', depth: 1, bids: [[100000, 2]], asks: [[100010, 1.5]], mid_price: 100005, snapshot_time: new Date().toISOString() }

        return {
          ok: true,
          status: 200,
          json: async () => payload,
        } as Response
      }),
    )
  })

  it('renders the dashboard shell and safety banner', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: /mission control/i })).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getAllByText(/paper default/i).length).toBeGreaterThan(0)
    })

    expect(screen.getByText(/live execution stays fail-closed/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /overview/i })).toBeInTheDocument()
  })
})
