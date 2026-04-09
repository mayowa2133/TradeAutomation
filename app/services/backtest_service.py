from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import OrderSide, StrategyRunStatus
from app.db.models.strategy_run import StrategyRun
from app.schemas.backtest import BacktestResponse, BacktestTrade, EquityPoint
from app.services.strategy_registry import StrategyRegistry
from app.utils.fees import apply_slippage, calculate_fee
from app.utils.metrics import compute_max_drawdown, compute_sharpe_like, compute_win_rate


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

    def run_backtest(
        self,
        *,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        market_data: pd.DataFrame,
        persist_run: bool = True,
        fee_bps: float | None = None,
        slippage_bps: float | None = None,
    ) -> BacktestResponse:
        fee_bps = fee_bps if fee_bps is not None else self.settings.default_fee_bps
        slippage_bps = slippage_bps if slippage_bps is not None else self.settings.default_slippage_bps
        strategy = self.registry.create_strategy(strategy_name, db=self.db)
        signals = strategy.generate_signals(market_data)
        balance = float(self.settings.paper_starting_balance)
        equity_curve: list[EquityPoint] = []
        pnl_samples: list[float] = []
        trade_records: list[BacktestTrade] = []
        fees_paid = 0.0
        run_model: StrategyRun | None = None

        if persist_run and self.db is not None:
            run_model = StrategyRun(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                mode=self.settings.trading_mode,
                status=StrategyRunStatus.STARTED,
                parameters=strategy.params,
            )
            self.db.add(run_model)
            self.db.commit()
            self.db.refresh(run_model)

        position: dict[str, object] | None = None
        try:
            for timestamp, row in signals.iterrows():
                close_price = float(row["close"])

                if position is not None:
                    exit_price: float | None = None
                    exit_reason = ""
                    stop_price = float(position["stop_loss_price"])
                    take_profit_price = float(position["take_profit_price"])
                    if float(row["low"]) <= stop_price:
                        exit_price = stop_price
                        exit_reason = "stop_loss"
                    elif float(row["high"]) >= take_profit_price:
                        exit_price = take_profit_price
                        exit_reason = "take_profit"
                    elif strategy.should_exit(row, has_position=True):
                        exit_price = close_price
                        exit_reason = "strategy_exit"

                    if exit_price is not None:
                        filled_exit = apply_slippage(
                            exit_price, side=OrderSide.SELL, slippage_bps=slippage_bps
                        )
                        qty = float(position["quantity"])
                        exit_notional = filled_exit * qty
                        exit_fee = calculate_fee(exit_notional, fee_bps)
                        gross_pnl = (filled_exit - float(position["entry_price"])) * qty
                        net_pnl = gross_pnl - float(position["entry_fee"]) - exit_fee
                        balance += exit_notional - exit_fee
                        fees_paid += exit_fee
                        pnl_samples.append(net_pnl)
                        trade_records.append(
                            BacktestTrade(
                                entry_time=position["entry_time"],
                                exit_time=timestamp.to_pydatetime(),
                                entry_price=float(position["entry_price"]),
                                exit_price=filled_exit,
                                quantity=qty,
                                gross_pnl=gross_pnl,
                                net_pnl=net_pnl,
                                fees=float(position["entry_fee"]) + exit_fee,
                                exit_reason=exit_reason,
                            )
                        )
                        position = None

                if position is None and strategy.should_enter(row, has_position=False):
                    quantity = strategy.position_size(
                        cash_balance=balance,
                        price=close_price,
                        risk_fraction=self.settings.max_risk_per_trade,
                        max_notional_fraction=self.settings.max_position_notional_pct,
                    )
                    if quantity > 0:
                        filled_entry = apply_slippage(
                            close_price, side=OrderSide.BUY, slippage_bps=slippage_bps
                        )
                        entry_notional = filled_entry * quantity
                        entry_fee = calculate_fee(entry_notional, fee_bps)
                        total_cost = entry_notional + entry_fee
                        if total_cost <= balance:
                            balance -= total_cost
                            fees_paid += entry_fee
                            position = {
                                "entry_time": timestamp.to_pydatetime(),
                                "entry_price": filled_entry,
                                "quantity": quantity,
                                "entry_fee": entry_fee,
                                "stop_loss_price": filled_entry * (1 - strategy.stop_loss_pct()),
                                "take_profit_price": filled_entry * (1 + strategy.take_profit_pct()),
                            }

                equity = balance
                if position is not None:
                    equity += float(position["quantity"]) * close_price
                equity_curve.append(EquityPoint(timestamp=timestamp.to_pydatetime(), equity=equity))

            if position is not None:
                last_timestamp = signals.index[-1].to_pydatetime()
                last_close = float(signals.iloc[-1]["close"])
                filled_exit = apply_slippage(last_close, side=OrderSide.SELL, slippage_bps=slippage_bps)
                qty = float(position["quantity"])
                exit_notional = filled_exit * qty
                exit_fee = calculate_fee(exit_notional, fee_bps)
                gross_pnl = (filled_exit - float(position["entry_price"])) * qty
                net_pnl = gross_pnl - float(position["entry_fee"]) - exit_fee
                balance += exit_notional - exit_fee
                fees_paid += exit_fee
                pnl_samples.append(net_pnl)
                trade_records.append(
                    BacktestTrade(
                        entry_time=position["entry_time"],
                        exit_time=last_timestamp,
                        entry_price=float(position["entry_price"]),
                        exit_price=filled_exit,
                        quantity=qty,
                        gross_pnl=gross_pnl,
                        net_pnl=net_pnl,
                        fees=float(position["entry_fee"]) + exit_fee,
                        exit_reason="end_of_test",
                    )
                )
                equity_curve[-1] = EquityPoint(timestamp=last_timestamp, equity=balance)

            equity_values = [point.equity for point in equity_curve]
            returns = pd.Series(equity_values, dtype=float).pct_change().fillna(0.0).tolist()
            response = BacktestResponse(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                trades=trade_records,
                equity_curve=equity_curve,
                total_trades=len(trade_records),
                win_rate=compute_win_rate([trade.net_pnl for trade in trade_records]),
                total_return_pct=(balance / self.settings.paper_starting_balance) - 1,
                sharpe_like=compute_sharpe_like(returns),
                max_drawdown_pct=compute_max_drawdown(equity_values),
                fees_paid=fees_paid,
                ending_balance=balance,
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
