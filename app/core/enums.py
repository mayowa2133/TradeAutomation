from enum import Enum


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class InstrumentType(str, Enum):
    SPOT = "spot"
    PERPETUAL = "perpetual"


class MarginMode(str, Enum):
    CASH = "cash"
    ISOLATED = "isolated"
    CROSS = "cross"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class TradeAction(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"
    FUNDING = "funding"


class StrategyRunStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class DecisionSource(str, Enum):
    STRATEGY = "strategy"
    OPTIMIZER = "optimizer"
    LLM = "llm"
    RISK = "risk"
    MANUAL = "manual"
    SYSTEM = "system"


class StreamHealth(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
