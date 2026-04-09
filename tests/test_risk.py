from app.services.risk_service import RiskService


def test_kill_switch_blocks_entries(db_session, settings):
    settings.kill_switch = True
    service = RiskService(db=db_session, settings=settings)
    decision = service.evaluate_entry(
        symbol="BTC/USDT",
        quantity=1.0,
        price=100.0,
        stop_loss_pct=0.01,
    )
    assert decision.allowed is False
    assert "Kill switch" in decision.reason
    settings.kill_switch = False


def test_symbol_allowlist_blocks_unknown_pair(db_session, settings):
    service = RiskService(db=db_session, settings=settings)
    decision = service.evaluate_entry(
        symbol="DOGE/USDT",
        quantity=1.0,
        price=100.0,
        stop_loss_pct=0.01,
    )
    assert decision.allowed is False
    assert "allowlist" in decision.reason
