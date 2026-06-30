from datetime import datetime, timedelta
from pathlib import Path

import pytest

from analytics.hf_losing_cycle_diagnostics_engine import HFLosingCycleDiagnosticsEngine
from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide
from storage.database_manager import DatabaseManager


PROFILE = "mean_reversion_hf_micro_v1"


def _cycle(
    *,
    direction: PaperOrderSide,
    net_profit: float,
    close_reason: str,
    opened_at: datetime,
    closed_at: datetime,
    open_price: float = 1.0,
    close_price: float = 0.9999,
) -> PaperCycle:
    cycle = PaperCycle(
        id=0,
        direction=direction,
        status=PaperCycleStatus.CLOSED,
        open_price=open_price,
        close_price=close_price,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=net_profit,
        net_profit=net_profit,
        opened_at=opened_at,
        closed_at=closed_at,
    )
    setattr(cycle, "close_reason", close_reason)
    return cycle


def _save_losing_cycle(
    database: DatabaseManager,
    *,
    direction: PaperOrderSide = PaperOrderSide.BUY_USDC,
    net_profit: float = -0.01,
    close_reason: str = "max_holding_270s",
    opened_at: datetime | None = None,
    close_price: float = 0.9999,
    with_entry_diagnostics: bool = True,
    flat_price_buffer: bool = False,
) -> int:
    opened_at = opened_at or datetime(2026, 6, 30, 12, 0, 0)
    db_id = database.save_paper_cycle(
        _cycle(
            direction=direction,
            net_profit=net_profit,
            close_reason=close_reason,
            opened_at=opened_at,
            closed_at=opened_at + timedelta(minutes=5),
            close_price=close_price,
        ),
        strategy_profile=PROFILE,
    )
    if with_entry_diagnostics:
        database.save_hf_paper_cycle_entry_diagnostics(
            paper_cycle_id=db_id,
            strategy_profile=PROFILE,
            current_price=1.0,
            short_center=1.0001,
            previous_price=1.00005,
            last_different_price=1.00005,
            hf_entry_mode="short_center",
            price_buffer_unique_values=2,
            flat_samples_count=0,
            flat_price_buffer=flat_price_buffer,
            entry_direction=direction.value,
            entry_reason="mean_reversion_hf_micro_v1: price below short_center",
        )
    return db_id


def test_hf_losing_cycle_diagnostics_filters_losing_cycles(tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened_at = datetime(2026, 6, 30, 12, 0, 0)
    _save_losing_cycle(database, net_profit=-0.01, opened_at=opened_at)
    database.save_paper_cycle(
        _cycle(
            direction=PaperOrderSide.BUY_USDC,
            net_profit=0.02,
            close_reason="target",
            opened_at=opened_at,
            closed_at=opened_at + timedelta(seconds=30),
            close_price=1.0001,
        ),
        strategy_profile=PROFILE,
    )

    report = HFLosingCycleDiagnosticsEngine(database).build_report(profile=PROFILE)

    assert report.total_cycles == 2
    assert report.losing_cycles_count == 1
    assert report.losing_cycles_rate == pytest.approx(0.5)
    assert report.total_loss_net == pytest.approx(-0.01)


def test_hf_losing_cycle_diagnostics_direction_and_timeout_breakdowns(tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _save_losing_cycle(database, direction=PaperOrderSide.BUY_USDC, net_profit=-0.01)
    _save_losing_cycle(
        database,
        direction=PaperOrderSide.SELL_USDC,
        net_profit=-0.02,
        close_reason="target",
        close_price=1.0001,
    )

    report = HFLosingCycleDiagnosticsEngine(database).build_report(profile=PROFILE)

    assert report.buy_losses_count == 1
    assert report.buy_losses_net == pytest.approx(-0.01)
    assert report.sell_losses_count == 1
    assert report.sell_losses_net == pytest.approx(-0.02)
    assert report.timeout_losses_count == 1
    assert report.timeout_losses_net == pytest.approx(-0.01)
    assert report.target_losses_count == 1
    assert report.target_losses_net == pytest.approx(-0.02)


def test_hf_losing_cycle_diagnostics_category_aggregation(tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _save_losing_cycle(database, net_profit=-0.01, flat_price_buffer=True)
    _save_losing_cycle(database, net_profit=-0.02, flat_price_buffer=True)

    report = HFLosingCycleDiagnosticsEngine(database).build_report(profile=PROFILE)

    categories = {item.category: item for item in report.categories}
    assert categories["flat_market_entry"].count == 2
    assert categories["flat_market_entry"].net_loss == pytest.approx(-0.03)
    assert "tune flat filter" in report.recommendations


def test_hf_losing_cycle_diagnostics_since_id_and_limit(tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    first_id = _save_losing_cycle(database, net_profit=-0.01)
    second_id = _save_losing_cycle(database, net_profit=-0.02)
    _save_losing_cycle(database, net_profit=-0.03)

    report = HFLosingCycleDiagnosticsEngine(database).build_report(
        profile=PROFILE,
        since_id=first_id,
        limit=1,
    )

    assert report.total_cycles == 2
    assert report.losing_cycles_count == 1
    assert report.details[0].db_id > second_id


def test_hf_losing_cycle_diagnostics_empty_dataset(tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = HFLosingCycleDiagnosticsEngine(database).build_report(profile=PROFILE)

    assert report.total_cycles == 0
    assert report.losing_cycles_count == 0
    assert report.recommendations == ["no action yet"]


def test_hf_losing_cycle_diagnostics_missing_entry_context_is_na(tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _save_losing_cycle(database, with_entry_diagnostics=False)

    report = HFLosingCycleDiagnosticsEngine(database).build_report(profile=PROFILE)
    detail = report.details[0]

    assert detail.short_center_at_entry == "N/A"
    assert detail.current_price_at_entry == "N/A"
    assert detail.previous_price == "N/A"
    assert detail.last_different_price == "N/A"
    assert detail.hf_entry_mode == "N/A"
