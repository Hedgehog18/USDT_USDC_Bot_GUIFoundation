import json
from pathlib import Path

from config.config_manager import ConfigManager


def test_config_manager_loads_config(tmp_path: Path):
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        json.dumps(
            {
                "symbol": "USDCUSDT",
                "mode": "DEMO",
                "market_data_source": "MOCK",
                "binance_base_url": "https://api.binance.com",
                "target_profit": 0.0002,
                "trade_size_percent": 0.10,
                "max_active_cycles": 1,
                "work_window_minutes": 15,
                "short_window_minutes": 60,
                "long_window_minutes": 1440,
                "min_market_activity_score": 40.0,
                "min_cycle_prediction_score": 60.0,
                "buy_zone_max": 20.0,
                "sell_zone_min": 80.0,
                "min_usdt_reserve_percent": 0.20,
                "min_usdc_reserve_percent": 0.20,
                "database_path": "database/test.sqlite",
                "use_real_market_data": False,
                "price_tick_size": 0.00001,
                "quantity_step_size": 0.0001,
                "min_notional": 5.0,
                "maker_fee_percent": 0.001,
                "taker_fee_percent": 0.001,
                "market_data_cache_ttl_seconds": 5,
                "runner_interval_seconds": 1,
                "max_runner_iterations": 2,
            }
        ),
        encoding="utf-8",
    )

    manager = ConfigManager(config_path)

    assert manager.config.symbol == "USDCUSDT"
    assert manager.config.target_profit == 0.0002
    assert manager.config.use_real_market_data is False
    assert manager.config.strategy_profile == "strict_current"
