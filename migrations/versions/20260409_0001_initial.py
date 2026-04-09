"""Initial trading schema."""

from alembic import op
import sqlalchemy as sa


revision = "20260409_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    order_side = sa.Enum("BUY", "SELL", name="orderside")
    order_type = sa.Enum("MARKET", "LIMIT", name="ordertype")
    order_status = sa.Enum("NEW", "FILLED", "CANCELED", "REJECTED", name="orderstatus")
    trading_mode = sa.Enum("PAPER", "LIVE", name="tradingmode")
    position_side = sa.Enum("LONG", name="positionside")
    position_status = sa.Enum("OPEN", "CLOSED", name="positionstatus")
    trade_action = sa.Enum("ENTRY", "EXIT", name="tradeaction")
    strategy_run_status = sa.Enum("STARTED", "COMPLETED", "FAILED", name="strategyrunstatus")

    bind = op.get_bind()
    for enum_type in (
        order_side,
        order_type,
        order_status,
        trading_mode,
        position_side,
        position_status,
        trade_action,
        strategy_run_status,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "event_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_event_logs_id", "event_logs", ["id"])
    op.create_index("ix_event_logs_level", "event_logs", ["level"])
    op.create_index("ix_event_logs_event_type", "event_logs", ["event_type"])
    op.create_index("ix_event_logs_created_at", "event_logs", ["created_at"])

    op.create_table(
        "market_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.UniqueConstraint("exchange", "symbol", "timeframe", "timestamp", name="uq_marketdata_bar"),
    )
    for idx in ["id", "exchange", "symbol", "timeframe", "timestamp"]:
        op.create_index(f"ix_market_data_{idx}", "market_data", [idx])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("exchange_order_id", sa.String(length=128), nullable=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", order_side, nullable=False),
        sa.Column("order_type", order_type, nullable=False),
        sa.Column("status", order_status, nullable=False),
        sa.Column("mode", trading_mode, nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("limit_price", sa.Float(), nullable=True),
        sa.Column("fill_price", sa.Float(), nullable=True),
        sa.Column("fee_paid", sa.Float(), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("exchange_name", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_order_id"),
    )
    for idx in ["id", "strategy_name", "symbol", "side", "status"]:
        op.create_index(f"ix_orders_{idx}", "orders", [idx])

    op.create_table(
        "portfolio_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mode", trading_mode, nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("starting_balance", sa.Float(), nullable=False),
        sa.Column("cash_balance", sa.Float(), nullable=False),
        sa.Column("last_equity", sa.Float(), nullable=False),
        sa.Column("peak_equity", sa.Float(), nullable=False),
        sa.Column("realized_pnl", sa.Float(), nullable=False),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mode"),
    )
    op.create_index("ix_portfolio_state_id", "portfolio_state", ["id"])
    op.create_index("ix_portfolio_state_mode", "portfolio_state", ["mode"])

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", position_side, nullable=False),
        sa.Column("mode", trading_mode, nullable=False),
        sa.Column("status", position_status, nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("avg_entry_price", sa.Float(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=False),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False),
        sa.Column("realized_pnl", sa.Float(), nullable=False),
        sa.Column("stop_loss_price", sa.Float(), nullable=True),
        sa.Column("take_profit_price", sa.Float(), nullable=True),
        sa.Column("exit_reason", sa.String(length=64), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for idx in ["id", "strategy_name", "symbol", "mode", "status"]:
        op.create_index(f"ix_positions_{idx}", "positions", [idx])

    op.create_table(
        "strategy_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("experimental", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_strategy_configs_id", "strategy_configs", ["id"])
    op.create_index("ix_strategy_configs_name", "strategy_configs", ["name"])

    op.create_table(
        "strategy_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("mode", trading_mode, nullable=False),
        sa.Column("status", strategy_run_status, nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=255), nullable=True),
    )
    for idx in ["id", "strategy_name", "symbol", "timeframe"]:
        op.create_index(f"ix_strategy_runs_{idx}", "strategy_runs", [idx])

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("positions.id"), nullable=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", order_side, nullable=False),
        sa.Column("action", trade_action, nullable=False),
        sa.Column("mode", trading_mode, nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("notional", sa.Float(), nullable=False),
        sa.Column("fee_paid", sa.Float(), nullable=False),
        sa.Column("realized_pnl", sa.Float(), nullable=False),
        sa.Column("trade_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(length=255), nullable=True),
    )
    for idx in ["id", "order_id", "position_id", "strategy_name", "symbol", "mode", "trade_time"]:
        op.create_index(f"ix_trades_{idx}", "trades", [idx])


def downgrade() -> None:
    for table in [
        "trades",
        "strategy_runs",
        "strategy_configs",
        "positions",
        "portfolio_state",
        "orders",
        "market_data",
        "event_logs",
    ]:
        op.drop_table(table)

    bind = op.get_bind()
    for enum_name in [
        "strategyrunstatus",
        "tradeaction",
        "positionstatus",
        "positionside",
        "tradingmode",
        "orderstatus",
        "ordertype",
        "orderside",
    ]:
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
