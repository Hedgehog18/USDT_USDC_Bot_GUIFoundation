from storage.database_manager import DatabaseManager


def test_database_saves_and_loads_long_paper_run(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    run_id = database.save_long_paper_run(
        iterations=500,
        interval_seconds=5,
        final_value=101.5,
        net_profit=1.5,
        win_rate=0.6,
        profit_factor=1.8,
        validation_status="PROMISING",
        insights_rating="GOOD",
        summary_report_path="reports/paper_summary_report.csv",
    )

    rows = database.load_recent_long_paper_runs(limit=20)

    assert run_id == 1
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == run_id
    assert row[2] == 500
    assert row[3] == 5
    assert row[4] == 101.5
    assert row[5] == 1.5
    assert row[6] == 0.6
    assert row[7] == 1.8
    assert row[8] == "PROMISING"
    assert row[9] == "GOOD"
    assert row[10] == "reports/paper_summary_report.csv"
