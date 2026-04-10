from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.db.models.strategy_config import StrategyConfigModel
from app.db.session import get_session_factory, init_db
from app.services.strategy_registry import StrategyRegistry

StrategyProfile = dict[str, Any]

PROFILES: dict[str, StrategyProfile] = {
    "active-demo": {
        "description": "High-activity paper-trading profile for dashboard walkthroughs.",
        "notes": [
            "Optimized for visible demo activity, not for trading quality.",
            "Uses short lookbacks and tight exits, so fee drag can dominate quickly.",
            "The experimental ML filter is disabled by default unless you explicitly keep it enabled.",
        ],
        "runtime_recommendations": {
            "DEFAULT_TIMEFRAMES": "1m",
            "MAX_POSITION_NOTIONAL_PCT": 0.20,
            "DEFAULT_LEVERAGE": 2.0,
            "MAX_CONCURRENT_POSITIONS": 3,
        },
        "strategies": {
            "ema_crossover": {
                "enabled": True,
                "parameters": {
                    "fast_window": 2,
                    "slow_window": 4,
                    "stop_loss_pct": 0.008,
                    "take_profit_pct": 0.012,
                },
            },
            "breakout": {
                "enabled": True,
                "parameters": {
                    "lookback": 6,
                    "exit_lookback": 3,
                    "buffer_pct": 0.0,
                    "stop_loss_pct": 0.01,
                    "take_profit_pct": 0.015,
                },
            },
            "rsi_mean_reversion": {
                "enabled": True,
                "parameters": {
                    "rsi_window": 7,
                    "oversold": 45,
                    "overbought": 55,
                    "exit_rsi": 52,
                    "cover_rsi": 48,
                    "trend_window": 10,
                    "stop_loss_pct": 0.008,
                    "take_profit_pct": 0.012,
                },
            },
            "ml_filter": {
                "enabled": False,
                "parameters": {},
            },
        },
    },
    "research-breakout-15m": {
        "description": "Lower-turnover research preset based on the recent paper-trade loss review.",
        "notes": [
            "This profile is a research hypothesis, not evidence of production alpha.",
            "It slows the system down, narrows the universe, and favors wider 15-minute breakouts.",
            "Recent sample analysis suggested the current 1-minute demo profile loses mainly to cost and turnover.",
        ],
        "runtime_recommendations": {
            "DEFAULT_TIMEFRAMES": "15m",
            "SYMBOL_ALLOWLIST": "ETH/USDT,SOL/USDT",
            "MAX_POSITION_NOTIONAL_PCT": 0.08,
            "DEFAULT_LEVERAGE": 1.5,
            "MAX_CONCURRENT_POSITIONS": 2,
        },
        "strategies": {
            "ema_crossover": {
                "enabled": False,
                "parameters": {
                    "fast_window": 20,
                    "slow_window": 50,
                    "stop_loss_pct": 0.02,
                    "take_profit_pct": 0.05,
                },
            },
            "breakout": {
                "enabled": True,
                "parameters": {
                    "lookback": 30,
                    "exit_lookback": 30,
                    "buffer_pct": 0.002,
                    "stop_loss_pct": 0.02,
                    "take_profit_pct": 0.06,
                },
            },
            "rsi_mean_reversion": {
                "enabled": False,
                "parameters": {
                    "rsi_window": 14,
                    "oversold": 30,
                    "overbought": 70,
                    "exit_rsi": 50,
                    "cover_rsi": 50,
                    "trend_window": 20,
                    "stop_loss_pct": 0.015,
                    "take_profit_pct": 0.03,
                },
            },
            "ml_filter": {
                "enabled": False,
                "parameters": {},
            },
        },
    },
}


def apply_profile(profile_name: str, disable_ml_filter: bool) -> dict[str, object]:
    profile = PROFILES[profile_name]
    strategy_entries: dict[str, dict[str, Any]] = profile["strategies"]
    init_db()
    registry = StrategyRegistry()
    with get_session_factory()() as db:
        registry.sync_configs(db)
        changes: list[dict[str, object]] = []
        for strategy_name, strategy_details in strategy_entries.items():
            config = registry.get_db_config(db, strategy_name)
            parameters = dict(strategy_details.get("parameters", {}))
            enabled = bool(strategy_details.get("enabled", True))
            if strategy_name == "ml_filter" and disable_ml_filter:
                enabled = False
            before = dict(config.parameters)
            before_enabled = config.enabled
            config.parameters = dict(parameters)
            config.enabled = enabled
            db.add(config)
            changes.append(
                {
                    "name": strategy_name,
                    "enabled_before": before_enabled,
                    "enabled_after": config.enabled,
                    "before": before,
                    "after": config.parameters,
                }
            )

        db.commit()
        return {
            "profile": profile_name,
            "description": profile["description"],
            "runtime_recommendations": profile["runtime_recommendations"],
            "notes": profile["notes"],
            "changes": changes,
        }


def list_profiles() -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for name, profile in PROFILES.items():
        output.append(
            {
                "name": name,
                "description": profile["description"],
                "runtime_recommendations": profile["runtime_recommendations"],
                "notes": profile["notes"],
            }
        )
    return output


def list_current_configs() -> list[dict[str, object]]:
    init_db()
    with get_session_factory()() as db:
        rows = db.query(StrategyConfigModel).order_by(StrategyConfigModel.name.asc()).all()
        return [
            {
                "name": row.name,
                "enabled": row.enabled,
                "parameters": row.parameters,
                "experimental": row.experimental,
            }
            for row in rows
        ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a paper-trading profile for dashboard demos or lower-turnover research runs."
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES.keys()),
        default="active-demo",
        help="Named profile to apply.",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="Print the available profile names, notes, and runtime recommendations.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Print the current strategy configuration without applying changes.",
    )
    parser.add_argument(
        "--keep-ml-filter-enabled",
        action="store_true",
        help="Keep the experimental ML filter enabled when the selected profile would otherwise only disable it for demo safety.",
    )
    args = parser.parse_args()

    if args.list_profiles:
        print(json.dumps(list_profiles(), indent=2))
        return

    if args.list_only:
        print(json.dumps(list_current_configs(), indent=2))
        return

    try:
        changes = apply_profile(
            profile_name=args.profile,
            disable_ml_filter=not args.keep_ml_filter_enabled,
        )
    except SQLAlchemyError as exc:
        raise SystemExit(
            "Unable to apply the requested profile. Verify DATABASE_URL points to a reachable runtime database."
        ) from exc

    print(json.dumps(changes, indent=2))


if __name__ == "__main__":
    main()
