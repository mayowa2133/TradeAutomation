from enum import Enum


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    NEW = "new"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


class PositionSide(str, Enum):
    LONG = "long"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class TradeAction(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"


class StrategyRunStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
