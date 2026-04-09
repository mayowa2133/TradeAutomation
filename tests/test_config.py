from app.core.enums import TradingMode


def test_config_safety_defaults(settings):
    assert settings.trading_mode == TradingMode.PAPER
    assert settings.enable_live_trading is False
    assert settings.live_trading_enabled is False
    assert settings.kill_switch is False
