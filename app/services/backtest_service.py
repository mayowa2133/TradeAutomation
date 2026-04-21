from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import DecisionSource, InstrumentType, MarginMode, OrderSide, PositionSide, StrategyRunStatus
from app.db.models.strategy_run import StrategyRun
from app.schemas.backtest import BacktestResponse, BacktestTrade, EquityPoint
from app.services.strategy_registry import StrategyRegistry
from app.utils.fees import apply_slippage, calculate_fee
from app.utils.metrics import compute_max_drawdown, compute_sharpe_like, compute_win_rate
from app.utils.orderbook import simulate_market_fill


def _direction(side: PositionSide) -> float:
    return -1.0 if side == PositionSide.SHORT else 1.0


def _entry_side(side: PositionSide) -> OrderSide:
    return OrderSide.SELL if side == PositionSide.SHORT else OrderSide.BUY


def _exit_side(side: PositionSide) -> OrderSide:
    return OrderSide.BUY if side == PositionSide.SHORT else OrderSide.SELL


class BacktestService:
    def __init__(
        self,
        settings: Settings,
        registry: StrategyRegistry | None = None,
        db: Session | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry or StrategyRegistry()
        self.db = db

    def _simulate_fill(
        self,
        *,
        price: float,
        quantity: float,
        side: OrderSide,
        slippage_bps: float,
        execution_model: str,
        depth_snapshot: dict[str, list[list[float]]] | None,
        allow_candle_fallback: bool,
    ) -> float:
        if execution_model == "depth":
            if depth_snapshot is not None:
                fill = simulate_market_fill(side, quantity, depth_snapshot.get("bids", []), depth_snapshot.get("asks", []))
                if fill.average_price is not None:
                    return float(fill.average_price)
            if not allow_candle_fallback:
                raise ValueError("Depth execution requested but no depth snapshot was supplied.")
        return apply_slippage(price, side=side, slippage_bps=slippage_bps)

    def _equity_with_position(self, balance: float, position: dict[str, float] | None, mark_price: float) -> float:
        if position is None:
            return balance
        direction = _direction(PositionSide(position["side"]))
        if position["instrument_type"] == InstrumentType.SPOT.value and position["side"] == PositionSide.LONG.value:
            return balance + (position["quantity"] * mark_price)
        unrealized = direction * (mark_price - position["entry_price"]) * position["quantity"]
        return balance + position["collateral"] + unrealized

    def run_backtest(
        self,
        *,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        market_data: pd.DataFrame,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        margin_mode: MarginMode = MarginMode.CASH,
        leverage: float = 1.0,
        execution_model: str = "candle",
        allow_candle_fallback: bool = True,
        depth_snapshots: dict[str, dict[str, list[list[float]]]] | None = None,
        persist_run: bool = True,
        fee_bps: float | None = None,
        slippage_bps: float | None = None,
    ) -> BacktestResponse:
        fee_bps = fee_bps if fee_bps is not None else self.settings.default_fee_bps
        slippage_bps = slippage_bps if slippage_bps is not None else self.settings.default_slippage_bps
        strategy = self.registry.create_strategy(strategy_name, db=self.db, symbol=symbol)
        signals = strategy.generate_signals(market_data)
        balance = float(self.settings.paper_starting_balance)
        equity_curve: list[EquityPoint] = []
        trade_records: list[BacktestTrade] = []
        fees_paid = 0.0
        funding_paid = 0.0
        liquidation_count = 0
        run_model: StrategyRun | None = None

        if persist_run and self.db is not None:
            run_model = StrategyRun(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                mode=self.settings.trading_mode,
                status=StrategyRunStatus.STARTED,
                decision_source=DecisionSource.STRATEGY,
                execution_model=execution_model,
                parameters={
                    **strategy.params,
                    "instrument_type": instrument_type.value,
                    "margin_mode": margin_mode.value,
                    "leverage": leverage,
                },
            )
            self.db.add(run_model)
            self.db.commit()
            self.db.refresh(run_model)

        position: dict[str, float | str | datetime] | None = None
        try:
            for timestamp, row in signals.iterrows():
                close_price = float(row["close"])
                high_price = float(row["high"])
                low_price = float(row["low"])
                timestamp_key = timestamp.isoformat()

                if position is not None and instrument_type == InstrumentType.PERPETUAL:
                    funding_rate = float(row.get("funding_rate", 0.0) or 0.0)
                    if funding_rate:
                        signed_funding = funding_rate * position["entry_notional"] * _direction(PositionSide(position["side"]))
                        balance -= signed_funding
                        position["funding_cost"] += signed_funding
                        funding_paid += signed_funding

                if position is not None:
                    side = PositionSide(position["side"])
                    direction = _direction(side)
                    exit_price: float | None = None
                    exit_reason = ""
                    liquidation_price = float(position.get("liquidation_price") or 0.0)
                    stop_price = float(position["stop_loss_price"])
                    take_profit_price = float(position["take_profit_price"])

                    if liquidation_price:
                        if side == PositionSide.LONG and low_price <= liquidation_price:
                            exit_price = liquidation_price
                            exit_reason = "liquidation"
                            liquidation_count += 1
                        elif side == PositionSide.SHORT and high_price >= liquidation_price:
                            exit_price = liquidation_price
                            exit_reason = "liquidation"
                            liquidation_count += 1

                    if exit_price is None:
                        if side == PositionSide.LONG and low_price <= stop_price:
                            exit_price = stop_price
                            exit_reason = "stop_loss"
                        elif side == PositionSide.SHORT and high_price >= stop_price:
                            exit_price = stop_price
                            exit_reason = "stop_loss"
                        elif side == PositionSide.LONG and high_price >= take_profit_price:
                            exit_price = take_profit_price
                            exit_reason = "take_profit"
                        elif side == PositionSide.SHORT and low_price <= take_profit_price:
                            exit_price = take_profit_price
                            exit_reason = "take_profit"
                        elif strategy.should_exit(row, has_position=True, position_side=side):
                            exit_price = close_price
                            exit_reason = "strategy_exit"

                    if exit_price is not None:
                        filled_exit = self._simulate_fill(
                            price=exit_price,
                            quantity=float(position["quantity"]),
                            side=_exit_side(side),
                            slippage_bps=slippage_bps,
                            execution_model=execution_model,
                            depth_snapshot=(depth_snapshots or {}).get(timestamp_key),
                            allow_candle_fallback=allow_candle_fallback,
                        )
                        qty = float(position["quantity"])
                        exit_notional = filled_exit * qty
                        exit_fee = calculate_fee(exit_notional, fee_bps)
                        gross_pnl = direction * (filled_exit - float(position["entry_price"])) * qty
                        total_funding = float(position["funding_cost"])
                        net_pnl = gross_pnl - float(position["entry_fee"]) - exit_fee - total_funding
                        if instrument_type == InstrumentType.SPOT and side == PositionSide.LONG:
                            balance += exit_notional - exit_fee
                        else:
                            balance += float(position["collateral"]) + gross_pnl - exit_fee
                        fees_paid += exit_fee
                        trade_records.append(
                            BacktestTrade(
                                entry_time=position["entry_time"],
                                exit_time=timestamp.to_pydatetime(),
                                instrument_type=instrument_type,
                                position_side=side,
                                leverage=float(position["leverage"]),
                                entry_price=float(position["entry_price"]),
                                exit_price=filled_exit,
                                quantity=qty,
                                gross_pnl=gross_pnl,
                                net_pnl=net_pnl,
                                fees=float(position["entry_fee"]) + exit_fee,
                                funding_paid=total_funding,
                                exit_reason=exit_reason,
                            )
                        )
                        position = None

                if position is None and strategy.should_enter(row, has_position=False):
                    side = strategy.desired_position_side(row)
                    if instrument_type == InstrumentType.SPOT and side == PositionSide.SHORT:
                        equity_curve.append(
                            EquityPoint(timestamp=timestamp.to_pydatetime(), equity=balance)
                        )
                        continue
                    quantity = strategy.position_size(
                        cash_balance=balance,
                        price=close_price,
                        risk_fraction=self.settings.max_risk_per_trade,
                        max_notional_fraction=self.settings.max_position_notional_pct,
                        leverage=leverage,
                    )
                    if quantity > 0:
                        filled_entry = self._simulate_fill(
                            price=close_price,
                            quantity=quantity,
                            side=_entry_side(side),
                            slippage_bps=slippage_bps,
                            execution_model=execution_model,
                            depth_snapshot=(depth_snapshots or {}).get(timestamp_key),
                            allow_candle_fallback=allow_candle_fallback,
                        )
                        entry_notional = filled_entry * quantity
                        entry_fee = calculate_fee(entry_notional, fee_bps)
                        collateral = (
                            entry_notional / max(leverage, 1.0)
                            if instrument_type == InstrumentType.PERPETUAL
                            else 0.0
                        )
                        upfront_cost = (
                            entry_notional + entry_fee
                            if instrument_type == InstrumentType.SPOT and side == PositionSide.LONG
                            else collateral + entry_fee
                        )
                        if upfront_cost <= balance:
                            balance -= upfront_cost
                            fees_paid += entry_fee
                            position = {
                                "entry_time": timestamp.to_pydatetime(),
                                "entry_price": filled_entry,
                                "quantity": quantity,
                                "entry_fee": entry_fee,
                                "entry_notional": entry_notional,
                                "collateral": collateral,
                                "leverage": leverage,
                                "instrument_type": instrument_type.value,
                                "side": side.value,
                                "funding_cost": 0.0,
                                "stop_loss_price": (
                                    filled_entry * (1 + strategy.stop_loss_pct())
                                    if side == PositionSide.SHORT
                                    else filled_entry * (1 - strategy.stop_loss_pct())
                                ),
                                "take_profit_price": (
                                    filled_entry * (1 - strategy.take_profit_pct())
                                    if side == PositionSide.SHORT
                                    else filled_entry * (1 + strategy.take_profit_pct())
                                ),
                                "liquidation_price": (
                                    filled_entry * (1 + (1 / max(leverage, 1.0)) - self.settings.default_maintenance_margin_pct)
                                    if instrument_type == InstrumentType.PERPETUAL and side == PositionSide.SHORT
                                    else (
                                        filled_entry * (1 - (1 / max(leverage, 1.0)) + self.settings.default_maintenance_margin_pct)
                                        if instrument_type == InstrumentType.PERPETUAL
                                        else 0.0
                                    )
                                ),
                            }

                equity_curve.append(
                    EquityPoint(
                        timestamp=timestamp.to_pydatetime(),
                        equity=self._equity_with_position(balance, position, close_price),
                    )
                )

            if position is not None:
                last_timestamp = signals.index[-1].to_pydatetime()
                last_close = float(signals.iloc[-1]["close"])
                side = PositionSide(position["side"])
                filled_exit = self._simulate_fill(
                    price=last_close,
                    quantity=float(position["quantity"]),
                    side=_exit_side(side),
                    slippage_bps=slippage_bps,
                    execution_model=execution_model,
                    depth_snapshot=(depth_snapshots or {}).get(signals.index[-1].isoformat()),
                    allow_candle_fallback=allow_candle_fallback,
                )
                qty = float(position["quantity"])
                exit_notional = filled_exit * qty
                exit_fee = calculate_fee(exit_notional, fee_bps)
                gross_pnl = _direction(side) * (filled_exit - float(position["entry_price"])) * qty
                total_funding = float(position["funding_cost"])
                net_pnl = gross_pnl - float(position["entry_fee"]) - exit_fee - total_funding
                if instrument_type == InstrumentType.SPOT and side == PositionSide.LONG:
                    balance += exit_notional - exit_fee
                else:
                    balance += float(position["collateral"]) + gross_pnl - exit_fee
                fees_paid += exit_fee
                trade_records.append(
                    BacktestTrade(
                        entry_time=position["entry_time"],
                        exit_time=last_timestamp,
                        instrument_type=instrument_type,
                        position_side=side,
                        leverage=float(position["leverage"]),
                        entry_price=float(position["entry_price"]),
                        exit_price=filled_exit,
                        quantity=qty,
                        gross_pnl=gross_pnl,
                        net_pnl=net_pnl,
                        fees=float(position["entry_fee"]) + exit_fee,
                        funding_paid=total_funding,
                        exit_reason="end_of_test",
                    )
                )
                ending_equity = balance
                equity_curve[-1] = EquityPoint(timestamp=last_timestamp, equity=ending_equity)
            else:
                ending_equity = balance

            equity_values = [point.equity for point in equity_curve]
            returns = pd.Series(equity_values, dtype=float).pct_change().fillna(0.0).tolist()
            response = BacktestResponse(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                instrument_type=instrument_type,
                margin_mode=margin_mode,
                execution_model=execution_model,
                trades=trade_records,
                equity_curve=equity_curve,
                total_trades=len(trade_records),
                win_rate=compute_win_rate([trade.net_pnl for trade in trade_records]),
                total_return_pct=(ending_equity / self.settings.paper_starting_balance) - 1,
                sharpe_like=compute_sharpe_like(returns),
                max_drawdown_pct=compute_max_drawdown(equity_values),
                fees_paid=fees_paid,
                funding_paid=funding_paid,
                liquidation_count=liquidation_count,
                ending_balance=balance,
                ending_equity=ending_equity,
            )

            if run_model is not None:
                run_model.status = StrategyRunStatus.COMPLETED
                run_model.metrics = response.model_dump(mode="json")
                run_model.completed_at = datetime.now(timezone.utc)
                self.db.add(run_model)
                self.db.commit()

            return response
        except Exception as exc:
            if run_model is not None:
                run_model.status = StrategyRunStatus.FAILED
                run_model.error_message = str(exc)
                run_model.completed_at = datetime.now(timezone.utc)
                self.db.add(run_model)
                self.db.commit()
            raise
