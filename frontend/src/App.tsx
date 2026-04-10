import { startTransition, useDeferredValue, useEffect, useState, type ReactNode } from 'react'

import {
  cancelOrder,
  closePosition,
  getConfig,
  getDashboardSummary,
  getDepth,
  getOrders,
  getPositions,
  getTrades,
  requestLlmDecision,
  runBacktest,
  runOptimizer,
  submitManualOrder,
  toggleStrategy,
} from './api'
import './App.css'
import { useLiveChannel } from './hooks/useLiveChannel'
import type {
  BacktestResult,
  ConfigResponse,
  DashboardSummary,
  ExecutionSnapshot,
  MarketSnapshot,
  Order,
  OrderBookSnapshot,
  Position,
  SectionKey,
  Trade,
} from './types'

const sections: Array<{
  key: SectionKey
  label: string
  code: string
  description: string
}> = [
  { key: 'overview', label: 'Overview', code: 'OVR', description: 'Equity, exposure, risk posture, and runtime health.' },
  { key: 'market', label: 'Market Monitor', code: 'MKT', description: 'Watchlists, depth, tape, and stream reliability.' },
  { key: 'execution', label: 'Execution Desk', code: 'EXE', description: 'Positions, orders, fills, and manual controls.' },
  { key: 'research', label: 'Research Lab', code: 'RSH', description: 'Backtests, optimizer runs, and scenario checks.' },
  { key: 'news-ai', label: 'News + AI', code: 'AI', description: 'News ingestion, structured reviews, and audit history.' },
  { key: 'settings', label: 'Settings', code: 'CFG', description: 'Safety defaults, live gates, and runtime configuration.' },
]

const fallbackSymbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toNumber(value: unknown) {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function parseAllowlist(raw: unknown) {
  if (Array.isArray(raw)) {
    return raw.map(String).filter(Boolean)
  }
  if (typeof raw === 'string') {
    return raw
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
  }
  return []
}

function formatCurrency(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return 'n/a'
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value)
}

function formatPrice(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return 'n/a'
  }
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}

function formatCompact(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return 'n/a'
  }
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value)
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return 'n/a'
  }
  return `${(value * 100).toFixed(2)}%`
}

function formatSignedCurrency(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return 'n/a'
  }
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${formatCurrency(value)}`
}

function formatTime(value: string | null | undefined) {
  if (!value) {
    return 'idle'
  }
  return new Date(value).toLocaleTimeString()
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) {
    return 'n/a'
  }
  return new Date(value).toLocaleString()
}

function statusTone(value: string | null | undefined) {
  const normalized = (value ?? '').toLowerCase()

  if (
    normalized.includes('healthy') ||
    normalized.includes('open') ||
    normalized.includes('ok') ||
    normalized.includes('connected') ||
    normalized.includes('active') ||
    normalized.includes('filled') ||
    normalized.includes('accepted') ||
    normalized.includes('paper') ||
    normalized.includes('stable') ||
    normalized.includes('operational') ||
    normalized.includes('normal')
  ) {
    return 'tone-positive'
  }

  if (
    normalized.includes('warning') ||
    normalized.includes('degraded') ||
    normalized.includes('connecting') ||
    normalized.includes('closed') ||
    normalized.includes('retrieving') ||
    normalized.includes('new') ||
    normalized.includes('partial') ||
    normalized.includes('standby')
  ) {
    return 'tone-warning'
  }

  if (
    normalized.includes('blocked') ||
    normalized.includes('error') ||
    normalized.includes('fail') ||
    normalized.includes('live') ||
    normalized.includes('kill') ||
    normalized.includes('canceled') ||
    normalized.includes('rejected') ||
    normalized.includes('misconfigured')
  ) {
    return 'tone-critical'
  }

  return 'tone-neutral'
}

function CommandBadge({
  children,
  tone = 'tone-neutral',
}: {
  children: ReactNode
  tone?: string
}) {
  return <span className={`command-badge ${tone}`}>{children}</span>
}

function MonolithCard({
  label,
  value,
  detail,
  tone,
}: {
  label: string
  value: string
  detail?: string
  tone?: 'positive' | 'warning' | 'critical'
}) {
  return (
    <article className="monolith-card">
      <div className="monolith-label">{label}</div>
      <div className={`monolith-value ${tone ? `is-${tone}` : ''}`}>{value}</div>
      {detail ? <div className="monolith-detail">{detail}</div> : null}
    </article>
  )
}

function Panel({
  title,
  eyebrow,
  actions,
  children,
  className,
}: {
  title: string
  eyebrow?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`panel-shell ${className ?? ''}`}>
      <header className="panel-header">
        <div>
          {eyebrow ? <div className="panel-eyebrow">{eyebrow}</div> : null}
          <h2>{title}</h2>
        </div>
        {actions ? <div className="panel-actions">{actions}</div> : null}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  )
}

function SectionIntro({
  title,
  description,
  actions,
}: {
  title: string
  description: string
  actions?: ReactNode
}) {
  return (
    <div className="section-intro">
      <div>
        <div className="section-kicker">Sovereign Console</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions ? <div className="section-actions">{actions}</div> : null}
    </div>
  )
}

function ProgressMeter({
  label,
  value,
  detail,
  tone,
}: {
  label: string
  value: number
  detail: string
  tone: 'positive' | 'warning' | 'critical'
}) {
  const safeValue = Number.isFinite(value) ? value : 0
  return (
    <div className="meter-row">
      <div className="meter-meta">
        <span>{label}</span>
        <strong>{detail}</strong>
      </div>
      <div className="meter-track">
        <div
          className={`meter-fill is-${tone}`}
          style={{ width: `${Math.max(0, Math.min(100, safeValue))}%` }}
        />
      </div>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return <div className="empty-state">{message}</div>
}

function App() {
  const [activeSection, setActiveSection] = useState<SectionKey>('overview')
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT')
  const deferredSymbol = useDeferredValue(selectedSymbol)
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [config, setConfig] = useState<ConfigResponse | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [trades, setTrades] = useState<Trade[]>([])
  const [depth, setDepth] = useState<OrderBookSnapshot | null>(null)
  const [backtest, setBacktest] = useState<BacktestResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [manualOrder, setManualOrder] = useState({
    symbol: 'BTC/USDT',
    instrumentType: 'perpetual',
    positionSide: 'long',
    orderType: 'market',
    quantity: '0.01',
    referencePrice: '100000',
    limitPrice: '100000',
    leverage: '2',
  })
  const [backtestForm, setBacktestForm] = useState({
    strategyName: 'ema_crossover',
    symbol: 'BTC/USDT',
    instrumentType: 'perpetual',
    timeframe: '5m',
    leverage: '2',
    limit: '300',
  })

  const systemChannel = useLiveChannel<DashboardSummary>('/ws/system')
  const executionChannel = useLiveChannel<ExecutionSnapshot>('/ws/execution')
  const marketChannel = useLiveChannel<MarketSnapshot>(
    `/ws/market?symbol=${encodeURIComponent(deferredSymbol)}&instrument_type=perpetual`,
  )

  async function hydrateDashboard(symbol: string) {
    setError(null)
    const [dashboard, runtimeConfig, openPositions, recentOrders, recentTrades, depthSnapshot] =
      await Promise.all([
        getDashboardSummary(),
        getConfig(),
        getPositions(),
        getOrders(),
        getTrades(),
        getDepth(symbol).catch(() => null),
      ])

    startTransition(() => {
      setSummary(dashboard)
      setConfig(runtimeConfig)
      setPositions(openPositions)
      setOrders(recentOrders)
      setTrades(recentTrades)
      setDepth(depthSnapshot)
    })
  }

  useEffect(() => {
    void hydrateDashboard(deferredSymbol).catch((requestError: Error) => {
      setError(requestError.message)
    })
  }, [deferredSymbol])

  useEffect(() => {
    if (systemChannel.data) {
      startTransition(() => setSummary(systemChannel.data))
    }
  }, [systemChannel.data])

  useEffect(() => {
    if (!executionChannel.data) {
      return
    }

    void Promise.all([getPositions(), getOrders(), getTrades()])
      .then(([openPositions, recentOrders, recentTrades]) => {
        startTransition(() => {
          setPositions(openPositions)
          setOrders(recentOrders)
          setTrades(recentTrades)
        })
      })
      .catch(() => undefined)
  }, [executionChannel.data])

  useEffect(() => {
    const marketData = marketChannel.data
    const orderbook = marketData?.orderbook
    if (!marketData || !orderbook) {
      return
    }

    startTransition(() =>
      setDepth({
        exchange: 'bybit',
        symbol: marketData.symbol ?? deferredSymbol,
        instrument_type: marketData.instrument_type ?? 'perpetual',
        depth: orderbook.bids.length,
        bids: orderbook.bids,
        asks: orderbook.asks,
        mid_price: orderbook.mid_price ?? null,
        snapshot_time: orderbook.snapshot_time,
      }),
    )
  }, [deferredSymbol, marketChannel.data])

  async function refreshAll(message?: string) {
    setBusy(true)
    setNotice(null)
    setError(null)
    try {
      await hydrateDashboard(deferredSymbol)
      if (message) {
        setNotice(message)
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Request failed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleToggleStrategy(name: string, enabled: boolean) {
    setBusy(true)
    setError(null)
    try {
      await toggleStrategy(name, enabled)
      await refreshAll(`Strategy ${name} ${enabled ? 'enabled' : 'disabled'}.`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to toggle strategy.')
      setBusy(false)
    }
  }

  async function handleRunBacktest() {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const result = await runBacktest({
        strategy_name: backtestForm.strategyName,
        symbol: backtestForm.symbol,
        timeframe: backtestForm.timeframe,
        instrument_type: backtestForm.instrumentType,
        margin_mode: backtestForm.instrumentType === 'perpetual' ? 'isolated' : 'cash',
        leverage: Number(backtestForm.leverage),
        limit: Number(backtestForm.limit),
        execution_model: 'candle',
      })
      setBacktest(result)
      setNotice(`Backtest completed for ${result.strategy_name} on ${result.symbol}.`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to run backtest.')
    } finally {
      setBusy(false)
    }
  }

  async function handleOptimizerRun() {
    setBusy(true)
    setError(null)
    try {
      await runOptimizer(selectedSymbols)
      await refreshAll('Optimizer run completed.')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to run optimizer.')
      setBusy(false)
    }
  }

  async function handleLlmReview() {
    setBusy(true)
    setError(null)
    try {
      await requestLlmDecision(deferredSymbol)
      await refreshAll(`LLM review requested for ${deferredSymbol}.`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to request LLM review.')
      setBusy(false)
    }
  }

  async function handleManualOrder() {
    setBusy(true)
    setError(null)
    try {
      await submitManualOrder({
        symbol: manualOrder.symbol,
        instrument_type: manualOrder.instrumentType,
        position_side: manualOrder.positionSide,
        quantity: Number(manualOrder.quantity),
        reference_price: Number(manualOrder.referencePrice),
        order_type: manualOrder.orderType,
        limit_price: manualOrder.orderType === 'limit' ? Number(manualOrder.limitPrice) : undefined,
        leverage: Number(manualOrder.leverage),
      })
      await refreshAll(
        `${manualOrder.orderType} ${manualOrder.positionSide} order submitted for ${manualOrder.symbol}.`,
      )
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to submit manual order.')
      setBusy(false)
    }
  }

  async function handleClosePosition(positionId: number) {
    setBusy(true)
    setError(null)
    try {
      await closePosition(positionId)
      await refreshAll(`Close submitted for position ${positionId}.`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to close position.')
      setBusy(false)
    }
  }

  async function handleCancelOrder(orderId: number) {
    setBusy(true)
    setError(null)
    try {
      await cancelOrder(orderId)
      await refreshAll(`Cancel requested for order ${orderId}.`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to cancel order.')
      setBusy(false)
    }
  }

  const settingsMap = config?.settings ?? {}
  const symbolUniverse = parseAllowlist(settingsMap.symbol_allowlist)
  const selectedSymbols = symbolUniverse.length ? symbolUniverse : fallbackSymbols
  const portfolio = summary?.portfolio ?? null
  const risk = summary?.risk ?? null
  const strategyItems = summary?.strategies ?? []
  const streamStatus = summary?.stream_status ?? []
  const newsItems = summary?.news ?? []
  const decisions = summary?.llm_decisions ?? []
  const recentEvents = summary?.recent_events ?? []
  const quote = marketChannel.data?.quote ?? null
  const sectionMeta = sections.find((section) => section.key === activeSection) ?? sections[0]
  const riskStatus =
    risk?.kill_switch
      ? 'BREAKER ACTIVE'
      : risk && risk.daily_realized_pnl <= risk.daily_loss_limit
        ? 'LOSS LIMIT BREACH'
        : 'NORMAL OPERATIONAL'
  const marginLoadPct =
    portfolio && portfolio.equity > 0 ? (portfolio.margin_used / Math.max(portfolio.equity, 1)) * 100 : 0
  const drawdownLoadPct =
    risk && risk.drawdown_limit_pct > 0 ? (risk.drawdown_pct / risk.drawdown_limit_pct) * 100 : 0
  const dailyLossUsagePct =
    risk && Math.abs(risk.daily_loss_limit) > 0
      ? (Math.abs(Math.min(risk.daily_realized_pnl, 0)) / Math.abs(risk.daily_loss_limit)) * 100
      : 0
  const riskLoadMultiple =
    portfolio && portfolio.equity > 0 ? portfolio.gross_exposure / Math.max(portfolio.equity, 1) : 0
  const wsStates = [systemChannel.state, marketChannel.state, executionChannel.state]
  const allChannelsHealthy = wsStates.every((state) => state === 'open')
  const topStatusItems = [
    { label: 'REDIS', value: systemChannel.state === 'open' ? 'OK' : systemChannel.state, tone: statusTone(systemChannel.state) },
    { label: 'DB', value: config ? 'OK' : 'SYNCING', tone: config ? 'tone-positive' : 'tone-warning' },
    { label: 'WS', value: allChannelsHealthy ? 'CONNECTED' : 'RECOVERING', tone: allChannelsHealthy ? 'tone-positive' : 'tone-warning' },
  ]

  const tickerItems = [
    `${deferredSymbol} ${quote?.last_price ? formatPrice(quote.last_price) : 'PENDING'}`,
    `SPREAD ${quote ? `${quote.spread_bps.toFixed(2)} BPS` : 'n/a'}`,
    `RISK LOAD ${riskLoadMultiple.toFixed(2)}x`,
    `${config?.trading_mode === 'live' ? 'LIVE' : 'PAPER'} MODE`,
    `DRAWDOWN ${formatPercent(portfolio?.drawdown_pct)}`,
    `${allChannelsHealthy ? 'SYSTEM NOMINAL' : 'STREAM RECOVERY'}`,
  ]

  const allowlist = selectedSymbols
  const watchlistRows = allowlist.map((symbol) => {
    const position = positions.find((item) => item.symbol === symbol)
    const hasLiveQuote = symbol === deferredSymbol && quote
    return {
      symbol,
      lastPrice: hasLiveQuote ? quote.last_price ?? quote.mark_price ?? quote.best_bid : position?.current_price ?? null,
      markPrice: hasLiveQuote ? quote.mark_price ?? quote.best_ask : position?.current_price ?? null,
      spread: hasLiveQuote ? `${quote.spread_bps.toFixed(2)} bps` : 'n/a',
      funding: hasLiveQuote ? formatPercent(quote.funding_rate ?? null) : 'n/a',
      status: hasLiveQuote ? marketChannel.state : position ? 'tracked' : 'standby',
    }
  })

  const maxDepthSize = Math.max(
    1,
    ...(depth?.bids ?? []).map(([, size]) => size),
    ...(depth?.asks ?? []).map(([, size]) => size),
  )

  const optimizerPayload = isRecord(summary?.optimizer) ? summary?.optimizer : null
  const optimizerWeights =
    optimizerPayload && isRecord(optimizerPayload.weights) ? optimizerPayload.weights : {}
  const optimizerTargets =
    optimizerPayload && isRecord(optimizerPayload.target_notional) ? optimizerPayload.target_notional : {}
  const optimizerRows = Object.entries(optimizerWeights).map(([symbol, weight]) => ({
    symbol,
    weight: toNumber(weight),
    targetNotional: toNumber(optimizerTargets[symbol]),
  }))

  const latestDecision = decisions[0] ?? null
  const liveLlmLocked = settingsMap.llm_autonomy_live !== true
  const paperLlmEnabled =
    settingsMap.llm_features_enabled === true && settingsMap.llm_autonomy_paper === true
  const estimatedReference =
    manualOrder.orderType === 'limit' ? Number(manualOrder.limitPrice) : Number(manualOrder.referencePrice)
  const estimatedNotional = Number(manualOrder.quantity) * (Number.isFinite(estimatedReference) ? estimatedReference : 0)
  const estimatedMargin =
    manualOrder.instrumentType === 'perpetual'
      ? estimatedNotional / Math.max(Number(manualOrder.leverage) || 1, 1)
      : estimatedNotional

  function setManualInstrumentType(value: string) {
    setManualOrder((current) => ({
      ...current,
      instrumentType: value,
      positionSide: value === 'spot' ? 'long' : current.positionSide,
      leverage: value === 'spot' ? '1' : current.leverage,
    }))
  }

  function setBacktestInstrumentType(value: string) {
    setBacktestForm((current) => ({
      ...current,
      instrumentType: value,
      leverage: value === 'spot' ? '1' : current.leverage,
    }))
  }

  return (
    <div className="console-shell">
      <aside className="console-sidebar">
        <div className="sidebar-brand">
          <h2 className="sidebar-wordmark">MISSION CONTROL</h2>
          <div className="sidebar-subtitle">Sovereign Console</div>
          <p className="sidebar-copy">
            Trade Automation Control for systematic crypto execution, research, and runtime safety.
          </p>
        </div>

        <nav className="console-nav" aria-label="Primary">
          {sections.map((section) => (
            <button
              key={section.key}
              className={`nav-button ${activeSection === section.key ? 'is-active' : ''}`}
              onClick={() => startTransition(() => setActiveSection(section.key))}
              type="button"
            >
              <span className="nav-code">{section.code}</span>
              <span className="nav-copy">
                <strong>{section.label}</strong>
                <small>{section.description}</small>
              </span>
            </button>
          ))}
        </nav>

        <div className="sidebar-safety">
          <div className="sidebar-safety-title">Safety Defaults</div>
          <p>Paper default. Live execution stays fail-closed. LLM autonomy is blocked in live mode.</p>
          <div className="sidebar-badge-row">
            <CommandBadge tone={config?.live_trading_enabled ? 'tone-critical' : 'tone-positive'}>
              {config?.live_trading_enabled ? 'live enabled' : 'paper default'}
            </CommandBadge>
            <CommandBadge tone={risk?.kill_switch ? 'tone-critical' : 'tone-positive'}>
              {risk?.kill_switch ? 'kill switch active' : 'entries allowed'}
            </CommandBadge>
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-footer-line">README.md</div>
          <div className="sidebar-footer-line">architecture.md</div>
          <div className="sidebar-footer-line">HANDOFF.md</div>
        </div>
      </aside>

      <div className="console-stage">
        <header className="command-bar">
          <div className="command-bar-left">
            <div className="command-title">OPERATIONS COMMAND</div>
            <div className="command-status-row">
              {topStatusItems.map((item) => (
                <span key={item.label} className={`command-status ${item.tone}`}>
                  <span className="status-dot" />
                  {item.label}: {item.value}
                </span>
              ))}
            </div>
          </div>

          <div className="command-bar-right">
            <button
              className={`mode-button ${config?.trading_mode === 'live' ? 'is-live' : 'is-paper'}`}
              onClick={() => startTransition(() => setActiveSection('settings'))}
              type="button"
            >
              {config?.trading_mode === 'live' ? 'LIVE MODE' : 'PAPER MODE'}
            </button>
            <button
              className={`kill-button ${risk?.kill_switch ? 'is-active' : ''}`}
              onClick={() => startTransition(() => setActiveSection('settings'))}
              type="button"
            >
              {risk?.kill_switch ? 'KILL SWITCH ACTIVE' : 'KILL SWITCH'}
            </button>
            <button
              className="ghost-button compact"
              disabled={busy}
              onClick={() => void refreshAll('Dashboard refreshed.')}
              type="button"
            >
              {busy ? 'WORKING...' : 'REFRESH'}
            </button>
          </div>
        </header>

        <div className="ticker-strip">
          {tickerItems.map((item) => (
            <span key={item} className="ticker-item">
              {item}
            </span>
          ))}
        </div>

        <main className="viewport">
          <SectionIntro
            title={sectionMeta.label.toUpperCase()}
            description={sectionMeta.description}
            actions={
              <>
                <label className="symbol-control">
                  <span>Venue Focus</span>
                  <select value={selectedSymbol} onChange={(event) => setSelectedSymbol(event.target.value)}>
                    {selectedSymbols.map((symbol) => (
                      <option key={symbol} value={symbol}>
                        {symbol}
                      </option>
                    ))}
                  </select>
                </label>
                <CommandBadge tone={allChannelsHealthy ? 'tone-positive' : 'tone-warning'}>
                  {allChannelsHealthy ? 'streams healthy' : 'stream recovery'}
                </CommandBadge>
              </>
            }
          />

          {error ? <div className="alert-banner tone-critical">{error}</div> : null}
          {notice ? <div className="alert-banner tone-positive">{notice}</div> : null}

          <section className="hero-grid">
            <MonolithCard
              label="Total Equity"
              value={formatCurrency(portfolio?.equity)}
              detail={`Peak ${formatCurrency(portfolio?.peak_equity)}`}
            />
            <MonolithCard
              label="Cash Balance"
              value={formatCurrency(portfolio?.cash_balance)}
              detail="Settled funds"
            />
            <MonolithCard
              label="Realized PnL"
              value={formatSignedCurrency(portfolio?.realized_pnl)}
              detail={`Daily ${formatSignedCurrency(risk?.daily_realized_pnl)}`}
              tone={portfolio && portfolio.realized_pnl >= 0 ? 'positive' : 'critical'}
            />
            <MonolithCard
              label="Unrealized PnL"
              value={formatSignedCurrency(portfolio?.unrealized_pnl)}
              detail={`${positions.length} open positions`}
              tone={portfolio && portfolio.unrealized_pnl >= 0 ? 'positive' : 'warning'}
            />
            <MonolithCard
              label="Gross Exposure"
              value={formatCompact(portfolio?.gross_exposure)}
              detail={`Net ${formatSignedCurrency(portfolio?.net_exposure)}`}
            />
            <MonolithCard
              label="Max Drawdown"
              value={formatPercent(portfolio?.drawdown_pct)}
              detail={`Margin ${formatCurrency(portfolio?.margin_used)}`}
              tone={portfolio && portfolio.drawdown_pct > 0.05 ? 'critical' : 'warning'}
            />
          </section>

          {activeSection === 'overview' ? (
            <section className="overview-layout">
              <div className="stack-column">
                <Panel
                  title="Risk Posture"
                  eyebrow="Deterministic guardrails"
                  actions={<CommandBadge tone={statusTone(riskStatus)}>{riskStatus}</CommandBadge>}
                >
                  <div className="risk-overview">
                    <div className="risk-status-block">
                      <div className="risk-status-label">Current status</div>
                      <div className={`risk-status-value ${statusTone(riskStatus)}`}>{riskStatus}</div>
                      <div className="risk-status-grid">
                        <div>
                          <span>Open positions</span>
                          <strong>{`${risk?.open_positions ?? 0}/${risk?.max_concurrent_positions ?? 0}`}</strong>
                        </div>
                        <div>
                          <span>Long exposure</span>
                          <strong>{formatCurrency(risk?.long_exposure)}</strong>
                        </div>
                        <div>
                          <span>Short exposure</span>
                          <strong>{formatCurrency(risk?.short_exposure)}</strong>
                        </div>
                        <div>
                          <span>Daily loss cap</span>
                          <strong>{formatCurrency(risk?.daily_loss_limit)}</strong>
                        </div>
                      </div>
                    </div>

                    <div className="meter-stack">
                      <ProgressMeter
                        label="Margin load"
                        value={marginLoadPct}
                        detail={`${marginLoadPct.toFixed(1)}% of equity`}
                        tone={marginLoadPct > 70 ? 'critical' : marginLoadPct > 40 ? 'warning' : 'positive'}
                      />
                      <ProgressMeter
                        label="Drawdown usage"
                        value={drawdownLoadPct}
                        detail={`${drawdownLoadPct.toFixed(1)}% of drawdown cap`}
                        tone={drawdownLoadPct > 80 ? 'critical' : drawdownLoadPct > 50 ? 'warning' : 'positive'}
                      />
                      <ProgressMeter
                        label="Daily loss usage"
                        value={dailyLossUsagePct}
                        detail={`${dailyLossUsagePct.toFixed(1)}% of daily loss guard`}
                        tone={dailyLossUsagePct > 80 ? 'critical' : dailyLossUsagePct > 50 ? 'warning' : 'positive'}
                      />
                    </div>

                    <div className="chip-row">
                      {risk?.blocked_symbols.length ? (
                        risk.blocked_symbols.map((symbol) => (
                          <CommandBadge key={symbol} tone="tone-warning">
                            cooldown {symbol}
                          </CommandBadge>
                        ))
                      ) : (
                        <CommandBadge tone="tone-positive">no symbol cooldowns</CommandBadge>
                      )}
                      <CommandBadge tone={risk?.kill_switch ? 'tone-critical' : 'tone-positive'}>
                        {risk?.kill_switch ? 'kill switch armed' : 'global breaker clear'}
                      </CommandBadge>
                    </div>
                  </div>
                </Panel>

                <Panel
                  title="Active Strategies"
                  eyebrow="Runtime toggles"
                  actions={<CommandBadge tone="tone-neutral">{`${strategyItems.length} registered`}</CommandBadge>}
                >
                  {strategyItems.length ? (
                    <div className="strategy-grid">
                      {strategyItems.map((strategy) => (
                        <div key={strategy.name} className="strategy-card">
                          <div className="strategy-copy">
                            <strong>{strategy.name}</strong>
                            <p>{strategy.description}</p>
                          </div>
                          <div className="strategy-actions">
                            {strategy.experimental ? (
                              <CommandBadge tone="tone-warning">experimental</CommandBadge>
                            ) : null}
                            <button
                              className={`toggle-button ${strategy.enabled ? 'is-enabled' : 'is-disabled'}`}
                              disabled={busy}
                              onClick={() => void handleToggleStrategy(strategy.name, !strategy.enabled)}
                              type="button"
                            >
                              {strategy.enabled ? 'ENABLED' : 'DISABLED'}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState message="No strategies registered in the dashboard payload." />
                  )}
                </Panel>
              </div>

              <div className="stack-column">
                <Panel title="Stream Health" eyebrow="Realtime plumbing">
                  <div className="stream-card-list">
                    {[
                      { stream_name: 'system_ws', symbol: 'all', status: systemChannel.state, last_message_at: null },
                      { stream_name: 'market_ws', symbol: deferredSymbol, status: marketChannel.state, last_message_at: quote?.snapshot_time ?? null },
                      { stream_name: 'execution_ws', symbol: 'all', status: executionChannel.state, last_message_at: null },
                      ...streamStatus,
                    ].map((stream) => (
                      <div key={`${stream.stream_name}-${stream.symbol}-${stream.status}`} className="stream-card">
                        <div>
                          <strong>{stream.stream_name}</strong>
                          <p>{stream.symbol}</p>
                        </div>
                        <div className="stream-card-meta">
                          <CommandBadge tone={statusTone(stream.status)}>{stream.status}</CommandBadge>
                          <small>{formatTime(stream.last_message_at)}</small>
                        </div>
                      </div>
                    ))}
                  </div>
                </Panel>

                <Panel title="Event Log" eyebrow="Audit trail">
                  {recentEvents.length ? (
                    <div className="event-console">
                      {recentEvents.map((event) => (
                        <div key={`${event.event_type}-${event.created_at}`} className="event-line">
                          <span className={`event-type ${statusTone(event.event_type)}`}>[{event.event_type}]</span>
                          <div className="event-message">{event.message}</div>
                          <time>{formatTime(event.created_at)}</time>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState message="No recent events have been recorded yet." />
                  )}
                </Panel>
              </div>
            </section>
          ) : null}

          {activeSection === 'market' ? (
            <section className="market-layout">
              <div className="stack-column">
                <Panel title="Symbol Watchlist" eyebrow="Selected venue universe">
                  <div className="table-shell">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Symbol</th>
                          <th>Last</th>
                          <th>Mark</th>
                          <th>Spread</th>
                          <th>Funding</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {watchlistRows.map((row) => (
                          <tr key={row.symbol} className={row.symbol === deferredSymbol ? 'is-focused' : ''}>
                            <td>{row.symbol}</td>
                            <td>{formatPrice(row.lastPrice)}</td>
                            <td>{formatPrice(row.markPrice)}</td>
                            <td>{row.spread}</td>
                            <td>{row.funding}</td>
                            <td>
                              <CommandBadge tone={statusTone(row.status)}>{row.status}</CommandBadge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>

                <div className="split-grid">
                  <Panel
                    title={`L2 Depth: ${deferredSymbol}`}
                    eyebrow="Depth-aware simulation"
                    actions={
                      <CommandBadge tone={depth?.mid_price ? 'tone-positive' : 'tone-warning'}>
                        {depth?.mid_price ? `mid ${formatPrice(depth.mid_price)}` : 'awaiting depth'}
                      </CommandBadge>
                    }
                  >
                    <div className="depth-shell">
                      <div className="depth-side">
                        <div className="depth-side-header">Bids</div>
                        <div className="depth-list">
                          {(depth?.bids ?? []).slice(0, 10).map(([price, size]) => (
                            <div key={`bid-${price}-${size}`} className="depth-row bid">
                              <div className="depth-bar" style={{ width: `${(size / maxDepthSize) * 100}%` }} />
                              <span>{formatPrice(price)}</span>
                              <span>{size.toFixed(4)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="depth-side">
                        <div className="depth-side-header">Asks</div>
                        <div className="depth-list">
                          {(depth?.asks ?? []).slice(0, 10).map(([price, size]) => (
                            <div key={`ask-${price}-${size}`} className="depth-row ask">
                              <div className="depth-bar" style={{ width: `${(size / maxDepthSize) * 100}%` }} />
                              <span>{formatPrice(price)}</span>
                              <span>{size.toFixed(4)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </Panel>

                  <Panel title="Recent Trades" eyebrow="Execution tape">
                    {trades.length ? (
                      <div className="event-console">
                        {trades.slice(0, 10).map((trade) => (
                          <div key={trade.id} className="event-line">
                            <span className={`event-type ${trade.realized_pnl >= 0 ? 'tone-positive' : 'tone-critical'}`}>
                              [{trade.action}]
                            </span>
                            <div className="event-message">
                              {trade.symbol} {trade.position_side} {trade.quantity.toFixed(4)} @ {formatPrice(trade.price)}
                            </div>
                            <time>{formatTime(trade.trade_time)}</time>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyState message="No trades available in the execution tape." />
                    )}
                  </Panel>
                </div>
              </div>

              <div className="stack-column">
                <Panel title="Stream Health" eyebrow="Transport state">
                  <div className="mini-stat-grid">
                    <div className="mini-stat">
                      <span>Best bid</span>
                      <strong>{formatPrice(quote?.best_bid)}</strong>
                    </div>
                    <div className="mini-stat">
                      <span>Best ask</span>
                      <strong>{formatPrice(quote?.best_ask)}</strong>
                    </div>
                    <div className="mini-stat">
                      <span>Spread</span>
                      <strong>{quote ? `${quote.spread_bps.toFixed(2)} bps` : 'n/a'}</strong>
                    </div>
                    <div className="mini-stat">
                      <span>Funding</span>
                      <strong>{formatPercent(quote?.funding_rate ?? null)}</strong>
                    </div>
                  </div>
                  <div className="stream-card-list">
                    {streamStatus.length ? (
                      streamStatus.map((stream) => (
                        <div key={`${stream.stream_name}-${stream.symbol}`} className="stream-card">
                          <div>
                            <strong>{stream.stream_name}</strong>
                            <p>{stream.symbol}</p>
                          </div>
                          <div className="stream-card-meta">
                            <CommandBadge tone={statusTone(stream.status)}>{stream.status}</CommandBadge>
                            <small>{formatTime(stream.last_message_at)}</small>
                          </div>
                        </div>
                      ))
                    ) : (
                      <EmptyState message="No persisted stream health records yet." />
                    )}
                  </div>
                </Panel>

                <Panel title="System Log" eyebrow="Recent diagnostics">
                  {recentEvents.length ? (
                    <div className="event-console">
                      {recentEvents.slice(0, 8).map((event) => (
                        <div key={`${event.event_type}-${event.created_at}-market`} className="event-line">
                          <span className={`event-type ${statusTone(event.event_type)}`}>[{event.event_type}]</span>
                          <div className="event-message">{event.message}</div>
                          <time>{formatTime(event.created_at)}</time>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState message="No diagnostics recorded yet." />
                  )}
                </Panel>
              </div>
            </section>
          ) : null}

          {activeSection === 'execution' ? (
            <section className="execution-layout">
              <div className="stack-column">
                <Panel
                  title="Open Positions"
                  eyebrow="Live state"
                  actions={<CommandBadge tone="tone-neutral">{`count ${positions.length}`}</CommandBadge>}
                >
                  {positions.length ? (
                    <div className="table-shell">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Asset</th>
                            <th>Side</th>
                            <th>Lev</th>
                            <th>Entry</th>
                            <th>Mark</th>
                            <th>UPnL</th>
                            <th>Liq</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {positions.map((position) => (
                            <tr key={position.id}>
                              <td>{position.symbol}</td>
                              <td>
                                <CommandBadge tone={position.side === 'long' ? 'tone-positive' : 'tone-critical'}>
                                  {position.side}
                                </CommandBadge>
                              </td>
                              <td>{`${position.leverage.toFixed(1)}x`}</td>
                              <td>{formatPrice(position.avg_entry_price)}</td>
                              <td>{formatPrice(position.current_price)}</td>
                              <td className={position.unrealized_pnl >= 0 ? 'text-positive' : 'text-critical'}>
                                {formatSignedCurrency(position.unrealized_pnl)}
                              </td>
                              <td>{formatPrice(position.liquidation_price)}</td>
                              <td className="table-action-cell">
                                <button
                                  className="ghost-button compact"
                                  disabled={busy}
                                  onClick={() => void handleClosePosition(position.id)}
                                  type="button"
                                >
                                  CLOSE
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <EmptyState message="No open positions in the current workspace." />
                  )}
                </Panel>

                <div className="split-grid">
                  <Panel title="Recent Orders" eyebrow="Order registry">
                    {orders.length ? (
                      <div className="table-shell compact-shell">
                        <table className="data-table compact-table">
                          <thead>
                            <tr>
                              <th>Symbol</th>
                              <th>Type</th>
                              <th>Status</th>
                              <th>Qty</th>
                              <th />
                            </tr>
                          </thead>
                          <tbody>
                            {orders.slice(0, 8).map((order) => (
                              <tr key={order.id}>
                                <td>{order.symbol}</td>
                                <td>{order.order_type}</td>
                                <td>
                                  <CommandBadge tone={statusTone(order.status)}>{order.status}</CommandBadge>
                                </td>
                                <td>{order.quantity.toFixed(4)}</td>
                                <td className="table-action-cell">
                                  {['new', 'partially_filled'].includes(order.status) ? (
                                    <button
                                      className="ghost-button compact"
                                      disabled={busy}
                                      onClick={() => void handleCancelOrder(order.id)}
                                      type="button"
                                    >
                                      CANCEL
                                    </button>
                                  ) : null}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <EmptyState message="No orders have been submitted yet." />
                    )}
                  </Panel>

                  <Panel title="Execution Fills" eyebrow="Trade ledger">
                    {trades.length ? (
                      <div className="table-shell compact-shell">
                        <table className="data-table compact-table">
                          <thead>
                            <tr>
                              <th>Symbol</th>
                              <th>Action</th>
                              <th>Side</th>
                              <th>PnL</th>
                            </tr>
                          </thead>
                          <tbody>
                            {trades.slice(0, 8).map((trade) => (
                              <tr key={trade.id}>
                                <td>{trade.symbol}</td>
                                <td>{trade.action}</td>
                                <td>{trade.position_side}</td>
                                <td className={trade.realized_pnl >= 0 ? 'text-positive' : 'text-critical'}>
                                  {formatSignedCurrency(trade.realized_pnl)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <EmptyState message="No fills have been recorded yet." />
                    )}
                  </Panel>
                </div>
              </div>

              <div className="stack-column">
                <Panel title="Manual Order Entry" eyebrow="Operator controls">
                  <form
                    className="form-stack"
                    onSubmit={(event) => {
                      event.preventDefault()
                      void handleManualOrder()
                    }}
                  >
                    <div className="segmented-control">
                      {[
                        { label: 'BUY / LONG', value: 'long' },
                        { label: 'SELL / SHORT', value: 'short' },
                      ].map((option) => (
                        <button
                          key={option.value}
                          className={`segment-button ${manualOrder.positionSide === option.value ? 'is-active' : ''}`}
                          disabled={manualOrder.instrumentType === 'spot' && option.value === 'short'}
                          onClick={() =>
                            setManualOrder((current) => ({
                              ...current,
                              positionSide: option.value,
                            }))
                          }
                          type="button"
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>

                    <label>
                      <span>Asset Pair</span>
                      <select
                        value={manualOrder.symbol}
                        onChange={(event) =>
                          setManualOrder((current) => ({ ...current, symbol: event.target.value }))
                        }
                      >
                        {selectedSymbols.map((symbol) => (
                          <option key={symbol} value={symbol}>
                            {symbol}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="form-grid two-up">
                      <label>
                        <span>Instrument</span>
                        <select
                          value={manualOrder.instrumentType}
                          onChange={(event) => setManualInstrumentType(event.target.value)}
                        >
                          <option value="perpetual">perpetual</option>
                          <option value="spot">spot</option>
                        </select>
                      </label>

                      <label>
                        <span>Order Type</span>
                        <select
                          value={manualOrder.orderType}
                          onChange={(event) =>
                            setManualOrder((current) => ({
                              ...current,
                              orderType: event.target.value,
                              limitPrice:
                                event.target.value === 'limit' && !current.limitPrice
                                  ? current.referencePrice
                                  : current.limitPrice,
                            }))
                          }
                        >
                          <option value="market">market</option>
                          <option value="limit">limit</option>
                        </select>
                      </label>
                    </div>

                    <div className="form-grid two-up">
                      <label>
                        <span>Reference Price (USD)</span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={manualOrder.referencePrice}
                          onChange={(event) =>
                            setManualOrder((current) => ({
                              ...current,
                              referencePrice: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <label>
                        <span>Limit Price (USD)</span>
                        <input
                          type="number"
                          disabled={manualOrder.orderType !== 'limit'}
                          min="0"
                          step="0.01"
                          value={manualOrder.limitPrice}
                          onChange={(event) =>
                            setManualOrder((current) => ({
                              ...current,
                              limitPrice: event.target.value,
                            }))
                          }
                        />
                      </label>
                    </div>

                    <div className="form-grid two-up">
                      <label>
                        <span>Size (Units)</span>
                        <input
                          type="number"
                          min="0"
                          step="0.0001"
                          value={manualOrder.quantity}
                          onChange={(event) =>
                            setManualOrder((current) => ({
                              ...current,
                              quantity: event.target.value,
                            }))
                          }
                        />
                      </label>

                      <label>
                        <span>Leverage</span>
                        <input
                          type="number"
                          disabled={manualOrder.instrumentType === 'spot'}
                          min="1"
                          step="0.1"
                          value={manualOrder.leverage}
                          onChange={(event) =>
                            setManualOrder((current) => ({
                              ...current,
                              leverage: event.target.value,
                            }))
                          }
                        />
                      </label>
                    </div>

                    <div className="mini-stat-grid">
                      <div className="mini-stat">
                        <span>Est. notional</span>
                        <strong>{formatCurrency(estimatedNotional)}</strong>
                      </div>
                      <div className="mini-stat">
                        <span>Est. margin</span>
                        <strong>{formatCurrency(estimatedMargin)}</strong>
                      </div>
                    </div>

                    <button className="primary-button" disabled={busy} type="submit">
                      PLACE EXECUTION ORDER
                    </button>
                  </form>
                </Panel>

                <Panel title="Safety Actions" eyebrow="Non-destructive console controls">
                  <div className="action-stack">
                    <button
                      className="danger-button"
                      onClick={() => startTransition(() => setActiveSection('settings'))}
                      type="button"
                    >
                      REVIEW KILL SWITCH STATE
                    </button>
                    <button
                      className="ghost-button"
                      disabled={busy}
                      onClick={() => void refreshAll('Execution state refreshed.')}
                      type="button"
                    >
                      REFRESH EXECUTION STATE
                    </button>
                    <p className="panel-note">
                      Frontend controls do not bypass backend safety rules. Live execution remains fail-closed
                      unless explicitly enabled in config.
                    </p>
                  </div>
                </Panel>
              </div>
            </section>
          ) : null}

          {activeSection === 'research' ? (
            <section className="research-layout">
              <div className="stack-column">
                <Panel title="Backtest Config" eyebrow="Scenario lab">
                  <form
                    className="form-stack"
                    onSubmit={(event) => {
                      event.preventDefault()
                      void handleRunBacktest()
                    }}
                  >
                    <label>
                      <span>Strategy Engine</span>
                      <select
                        value={backtestForm.strategyName}
                        onChange={(event) =>
                          setBacktestForm((current) => ({ ...current, strategyName: event.target.value }))
                        }
                      >
                        {(strategyItems.length ? strategyItems : [{ name: 'ema_crossover' }]).map((strategy) => (
                          <option key={strategy.name} value={strategy.name}>
                            {strategy.name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="form-grid two-up">
                      <label>
                        <span>Symbol</span>
                        <select
                          value={backtestForm.symbol}
                          onChange={(event) =>
                            setBacktestForm((current) => ({ ...current, symbol: event.target.value }))
                          }
                        >
                          {selectedSymbols.map((symbol) => (
                            <option key={symbol} value={symbol}>
                              {symbol}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label>
                        <span>Timeframe</span>
                        <select
                          value={backtestForm.timeframe}
                          onChange={(event) =>
                            setBacktestForm((current) => ({ ...current, timeframe: event.target.value }))
                          }
                        >
                          <option value="1m">1m</option>
                          <option value="5m">5m</option>
                          <option value="15m">15m</option>
                        </select>
                      </label>
                    </div>

                    <div className="form-grid two-up">
                      <label>
                        <span>Instrument</span>
                        <select
                          value={backtestForm.instrumentType}
                          onChange={(event) => setBacktestInstrumentType(event.target.value)}
                        >
                          <option value="perpetual">perpetual</option>
                          <option value="spot">spot</option>
                        </select>
                      </label>

                      <label>
                        <span>Leverage</span>
                        <input
                          type="number"
                          min="1"
                          disabled={backtestForm.instrumentType === 'spot'}
                          step="0.1"
                          value={backtestForm.leverage}
                          onChange={(event) =>
                            setBacktestForm((current) => ({ ...current, leverage: event.target.value }))
                          }
                        />
                      </label>
                    </div>

                    <label>
                      <span>Bars</span>
                      <input
                        type="number"
                        min="100"
                        step="50"
                        value={backtestForm.limit}
                        onChange={(event) =>
                          setBacktestForm((current) => ({ ...current, limit: event.target.value }))
                        }
                      />
                    </label>

                    <button className="primary-button" disabled={busy} type="submit">
                      EXECUTE SIMULATION
                    </button>
                  </form>
                </Panel>

                <Panel title="Execution Notes" eyebrow="Research constraints">
                  <div className="event-console">
                    <div className="event-line">
                      <span className="event-type tone-positive">[INFO]</span>
                      <div className="event-message">Backtests run through the same strategy registry used by paper execution.</div>
                      <time>static</time>
                    </div>
                    <div className="event-line">
                      <span className="event-type tone-warning">[NOTE]</span>
                      <div className="event-message">Current frontend triggers the candle execution model for repeatable local runs.</div>
                      <time>static</time>
                    </div>
                    <div className="event-line">
                      <span className="event-type tone-critical">[RISK]</span>
                      <div className="event-message">No profitability claim is made. Results must be validated with fees, slippage, and live venue behavior.</div>
                      <time>static</time>
                    </div>
                  </div>
                </Panel>
              </div>

              <div className="stack-column">
                <div className="summary-strip">
                  <MonolithCard
                    label="Return"
                    value={backtest ? formatPercent(backtest.total_return_pct) : 'n/a'}
                    tone={backtest && backtest.total_return_pct >= 0 ? 'positive' : 'critical'}
                  />
                  <MonolithCard label="Win Rate" value={backtest ? formatPercent(backtest.win_rate) : 'n/a'} />
                  <MonolithCard label="Sharpe-Like" value={backtest ? backtest.sharpe_like.toFixed(2) : 'n/a'} />
                  <MonolithCard label="Liquidations" value={backtest ? String(backtest.liquidation_count) : 'n/a'} />
                </div>

                <Panel
                  title="Optimizer Output"
                  eyebrow="Advisory targets"
                  actions={
                    <button className="ghost-button compact" disabled={busy} onClick={() => void handleOptimizerRun()} type="button">
                      RUN OPTIMIZER
                    </button>
                  }
                >
                  {optimizerRows.length ? (
                    <div className="table-shell">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Symbol</th>
                            <th>Weight</th>
                            <th>Target Notional</th>
                          </tr>
                        </thead>
                        <tbody>
                          {optimizerRows.map((row) => (
                            <tr key={row.symbol}>
                              <td>{row.symbol}</td>
                              <td>{`${(row.weight * 100).toFixed(1)}%`}</td>
                              <td>{formatCurrency(row.targetNotional)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <pre className="code-block">{JSON.stringify(summary?.optimizer ?? { status: 'not_run' }, null, 2)}</pre>
                  )}
                </Panel>

                <Panel title="Latest Backtest" eyebrow="Result snapshot">
                  {backtest ? (
                    <div className="backtest-layout">
                      <div className="mini-stat-grid">
                        <div className="mini-stat">
                          <span>Ending equity</span>
                          <strong>{formatCurrency(backtest.ending_equity)}</strong>
                        </div>
                        <div className="mini-stat">
                          <span>Fees paid</span>
                          <strong>{formatCurrency(backtest.fees_paid)}</strong>
                        </div>
                        <div className="mini-stat">
                          <span>Funding paid</span>
                          <strong>{formatCurrency(backtest.funding_paid)}</strong>
                        </div>
                        <div className="mini-stat">
                          <span>Execution model</span>
                          <strong>{backtest.execution_model}</strong>
                        </div>
                      </div>

                      <div className="equity-strip">
                        {backtest.equity_curve.slice(-18).map((point, index, points) => {
                          const values = points.map((item) => item.equity)
                          const min = Math.min(...values)
                          const max = Math.max(...values)
                          const height =
                            max === min ? 100 : ((point.equity - min) / Math.max(max - min, 1)) * 100
                          return (
                            <div key={`${point.timestamp}-${index}`} className="equity-bar-shell">
                              <div className="equity-bar" style={{ height: `${Math.max(8, height)}%` }} />
                            </div>
                          )
                        })}
                      </div>

                      <div className="table-shell compact-shell">
                        <table className="data-table compact-table">
                          <thead>
                            <tr>
                              <th>Entry</th>
                              <th>Exit</th>
                              <th>Side</th>
                              <th>Net PnL</th>
                            </tr>
                          </thead>
                          <tbody>
                            {backtest.trades.slice(0, 6).map((trade) => (
                              <tr key={`${trade.entry_time}-${trade.exit_time}-${trade.position_side}`}>
                                <td>{formatTime(trade.entry_time)}</td>
                                <td>{formatTime(trade.exit_time)}</td>
                                <td>{trade.position_side}</td>
                                <td className={trade.net_pnl >= 0 ? 'text-positive' : 'text-critical'}>
                                  {formatSignedCurrency(trade.net_pnl)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : (
                    <EmptyState message="Run a backtest to populate research results." />
                  )}
                </Panel>
              </div>
            </section>
          ) : null}

          {activeSection === 'news-ai' ? (
            <section className="news-layout">
              <div className="advisory-banner">
                OPERATIONAL ADVISORY: LLM output is informational only. Live trading ignores LLM-triggered intents.
              </div>

              <div className="news-layout-grid">
                <Panel title="Structured News Feed" eyebrow="RSS-first ingest">
                  {newsItems.length ? (
                    <div className="news-feed">
                      {newsItems.map((item) => (
                        <article key={`${item.source}-${item.title}`} className="news-card">
                          <div className="news-meta">
                            <span>{item.source}</span>
                            <span>{formatTime(item.published_at)}</span>
                          </div>
                          <h3>{item.title}</h3>
                          <p>{item.summary ?? 'No summary returned for this headline.'}</p>
                          <div className="chip-row">
                            {(item.symbols.length ? item.symbols : ['unmapped']).map((symbol) => (
                              <CommandBadge key={`${item.title}-${symbol}`} tone="tone-neutral">
                                {symbol}
                              </CommandBadge>
                            ))}
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <EmptyState message="No news items are available in the dashboard payload." />
                  )}
                </Panel>

                <Panel
                  title="LLM Market Summary"
                  eyebrow="Structured outputs only"
                  actions={
                    <button className="primary-button compact-button" disabled={busy} onClick={() => void handleLlmReview()} type="button">
                      REQUEST REVIEW
                    </button>
                  }
                >
                  {latestDecision ? (
                    <div className="llm-summary">
                      <div className="summary-card">
                        <div className="summary-title-row">
                          <strong>{latestDecision.symbol ?? deferredSymbol}</strong>
                          <CommandBadge tone={latestDecision.accepted ? 'tone-positive' : 'tone-warning'}>
                            {latestDecision.accepted ? 'accepted' : 'rejected'}
                          </CommandBadge>
                        </div>
                        <p>{latestDecision.reason ?? 'No rationale returned.'}</p>
                      </div>
                      <div className="mini-stat-grid">
                        <div className="mini-stat">
                          <span>Confidence</span>
                          <strong>{`${(latestDecision.confidence * 100).toFixed(0)}%`}</strong>
                        </div>
                        <div className="mini-stat">
                          <span>Provider</span>
                          <strong>{latestDecision.provider ?? 'n/a'}</strong>
                        </div>
                        <div className="mini-stat">
                          <span>Paper autonomy</span>
                          <strong>{paperLlmEnabled ? 'enabled' : 'off'}</strong>
                        </div>
                        <div className="mini-stat">
                          <span>Live autonomy</span>
                          <strong>{liveLlmLocked ? 'locked off' : 'invalid'}</strong>
                        </div>
                      </div>
                      <pre className="code-block">
                        {JSON.stringify(latestDecision.structured_output ?? latestDecision.context_payload ?? {}, null, 2)}
                      </pre>
                    </div>
                  ) : (
                    <EmptyState message="No LLM decisions have been recorded yet." />
                  )}
                </Panel>

                <Panel title="Audit Decision Log" eyebrow="Review history">
                  {decisions.length ? (
                    <div className="event-console">
                      {decisions.map((decision) => (
                        <div key={`${decision.symbol}-${decision.created_at}-${decision.confidence}`} className="event-line">
                          <span className={`event-type ${decision.accepted ? 'tone-positive' : 'tone-warning'}`}>
                            [{decision.accepted ? 'ACCEPT' : 'REJECT'}]
                          </span>
                          <div className="event-message">
                            {decision.symbol ?? 'market summary'} :: {decision.reason ?? 'No rationale returned.'}
                          </div>
                          <time>{formatTime(decision.created_at)}</time>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState message="No decision audit history is available yet." />
                  )}
                </Panel>
              </div>
            </section>
          ) : null}

          {activeSection === 'settings' ? (
            <section className="settings-layout">
              <div className="stack-column">
                <Panel title="Global Toggles" eyebrow="Runtime safety console">
                  <div className="mini-stat-grid">
                    <div className="mini-stat">
                      <span>Operational mode</span>
                      <strong>{config?.trading_mode ?? 'paper'}</strong>
                    </div>
                    <div className="mini-stat">
                      <span>Live enabled</span>
                      <strong>{config?.live_trading_enabled ? 'true' : 'false'}</strong>
                    </div>
                    <div className="mini-stat">
                      <span>Kill switch</span>
                      <strong>{risk?.kill_switch ? 'armed' : 'clear'}</strong>
                    </div>
                    <div className="mini-stat">
                      <span>LLM live gate</span>
                      <strong>{liveLlmLocked ? 'locked off' : 'invalid'}</strong>
                    </div>
                  </div>

                  <div className="action-stack">
                    <button className="danger-button" onClick={() => void refreshAll('Safety console refreshed.')} type="button">
                      REFRESH SAFETY STATE
                    </button>
                    <p className="panel-note">
                      This dashboard reflects safety state. Any live enablement still requires explicit environment
                      flags and valid credentials on the backend.
                    </p>
                  </div>
                </Panel>

                <Panel title="Worker and Stream Registry" eyebrow="Background services">
                  {streamStatus.length ? (
                    <div className="stream-card-list worker-grid">
                      {streamStatus.map((stream) => (
                        <div key={`${stream.stream_name}-${stream.symbol}-settings`} className="worker-card">
                          <div className="worker-header">
                            <strong>{stream.stream_name}</strong>
                            <CommandBadge tone={statusTone(stream.status)}>{stream.status}</CommandBadge>
                          </div>
                          <div className="worker-copy">{stream.symbol}</div>
                          <div className="worker-copy">{formatTimestamp(stream.last_message_at)}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState message="No worker stream registry items are available yet." />
                  )}
                </Panel>
              </div>

              <div className="stack-column">
                <Panel title="Risk Engine Configuration" eyebrow="Fail-closed thresholds">
                  <div className="meter-stack">
                    <ProgressMeter
                      label="Gross exposure cap"
                      value={Math.min(riskLoadMultiple / Math.max(risk?.max_gross_exposure_pct ?? 1, 0.0001), 1) * 100}
                      detail={`${risk?.max_gross_exposure_pct?.toFixed(2) ?? 'n/a'}x equity limit`}
                      tone="warning"
                    />
                    <ProgressMeter
                      label="Net exposure cap"
                      value={
                        Math.min(
                          Math.abs(portfolio?.net_exposure ?? 0) /
                            Math.max((risk?.equity ?? 1) * (risk?.max_net_exposure_pct ?? 1), 1),
                          1,
                        ) * 100
                      }
                      detail={`${risk?.max_net_exposure_pct?.toFixed(2) ?? 'n/a'}x equity limit`}
                      tone="warning"
                    />
                    <ProgressMeter
                      label="Side concentration cap"
                      value={
                        Math.min(
                          Math.max(risk?.long_exposure ?? 0, risk?.short_exposure ?? 0) /
                            Math.max((risk?.equity ?? 1) * (risk?.max_side_exposure_pct ?? 1), 1),
                          1,
                        ) * 100
                      }
                      detail={`${risk?.max_side_exposure_pct?.toFixed(2) ?? 'n/a'}x per side`}
                      tone="warning"
                    />
                  </div>

                  <div className="table-shell compact-shell">
                    <table className="data-table compact-table">
                      <tbody>
                        <tr>
                          <td>Max concurrent positions</td>
                          <td>{risk?.max_concurrent_positions ?? 'n/a'}</td>
                        </tr>
                        <tr>
                          <td>Daily realized PnL</td>
                          <td>{formatSignedCurrency(risk?.daily_realized_pnl)}</td>
                        </tr>
                        <tr>
                          <td>Daily loss limit</td>
                          <td>{formatCurrency(risk?.daily_loss_limit)}</td>
                        </tr>
                        <tr>
                          <td>Drawdown limit</td>
                          <td>{formatPercent(risk?.drawdown_limit_pct)}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </Panel>

                <Panel title="Symbol Allowlist + Runtime Config" eyebrow="Operator reference">
                  <div className="chip-row">
                    {allowlist.map((symbol) => (
                      <CommandBadge key={`allow-${symbol}`} tone="tone-neutral">
                        {symbol}
                      </CommandBadge>
                    ))}
                  </div>
                  <pre className="code-block">{JSON.stringify(settingsMap, null, 2)}</pre>
                </Panel>
              </div>
            </section>
          ) : null}
        </main>

        <footer className="footer-ticker">
          <span>{deferredSymbol}</span>
          <span>{quote?.last_price ? formatPrice(quote.last_price) : 'awaiting quote'}</span>
          <span>{allChannelsHealthy ? 'sync nominal' : 'reconnect in progress'}</span>
          <span>{formatTime(quote?.snapshot_time ?? depth?.snapshot_time ?? null)}</span>
        </footer>
      </div>
    </div>
  )
}

export default App
