from analytics.fee_model_report_engine import FeeModelReportEngine


def test_fee_model_report_summarizes_configured_fee_models(test_config):
    report = FeeModelReportEngine(test_config).build_report(trade_size=10.0)

    assert report.configured_maker_fee == 0.001
    assert report.configured_taker_fee == 0.001
    assert report.effective_maker_fee == 0.0
    assert report.effective_taker_fee == 0.0
    assert "USDCUSDT" in report.effective_fee_source
    assert "maker fee" in report.backtest_model
    assert "taker fee" in report.paper_model
    assert "effective maker fee" in report.risk_profitability_model
    assert report.fee_model_consistency == "MISMATCH"
    assert len(report.scenarios) == 3
    assert report.scenarios[0].name == "maker/maker"
    assert report.scenarios[0].total_fee == 0.0
    assert "0.1% + 0.1%" in report.observed_fee_rate_interpretation


def test_fee_model_report_flags_mismatch_when_maker_and_taker_differ(test_config):
    config = test_config.__class__(**{
        **test_config.__dict__,
        "taker_fee_percent": 0.002,
    })

    report = FeeModelReportEngine(config).build_report(trade_size=10.0)

    assert report.fee_model_consistency == "MISMATCH"
