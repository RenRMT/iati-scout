from datetime import UTC, date, datetime

from tests.quality.conftest import make_activity, make_txn, run


def test_e_a01_actual_end_before_start():
    a = make_activity(dates={"2": date(2024, 5, 1), "4": date(2024, 1, 1)})
    issues = run("E-A01", a)
    assert len(issues) == 1
    assert "2024-01-01" in issues[0].message and "2024-05-01" in issues[0].message
    assert issues[0].evidence == {"actual_start": date(2024, 5, 1), "actual_end": date(2024, 1, 1)}


def test_e_a01_ok_when_ordered():
    a = make_activity(dates={"2": date(2024, 1, 1), "4": date(2024, 5, 1)})
    assert run("E-A01", a) == []


def test_e_a02_planned_end_before_start():
    a = make_activity(dates={"1": date(2024, 5, 1), "3": date(2024, 1, 1)})
    assert len(run("E-A02", a)) == 1


def test_e_a03_actual_dates_in_future():
    a = make_activity(dates={"2": date(2030, 1, 1), "4": date(2031, 1, 1)})
    issues = run("E-A03", a)
    assert len(issues) == 2
    assert {next(iter(i.evidence)) for i in issues} == {"actual_start", "actual_end"}


def test_e_a04_pipeline_with_actual_start_and_transactions():
    a = make_activity(status="1", dates={"2": date(2024, 1, 1)}, transactions=[make_txn()])
    issues = run("E-A04", a)
    assert len(issues) == 2


def test_e_a04_pipeline_clean():
    a = make_activity(status="1", dates={"1": date(2027, 1, 1)})
    assert run("E-A04", a) == []


def test_e_a05_implementation_with_actual_end():
    a = make_activity(status="2", dates={"2": date(2024, 1, 1), "4": date(2025, 1, 1)})
    assert len(run("E-A05", a)) == 1


def test_e_a06_closed_without_actual_end():
    a = make_activity(status="3", dates={"2": date(2024, 1, 1), "3": date(2025, 1, 1)})
    issues = run("E-A06", a)
    assert len(issues) == 1
    assert issues[0].evidence["planned_end"] == date(2025, 1, 1)


def test_e_a06_closed_with_actual_end_ok():
    a = make_activity(status="4", dates={"2": date(2024, 1, 1), "4": date(2025, 1, 1)})
    assert run("E-A06", a) == []


def test_w_a07_implementation_past_planned_end():
    a = make_activity(status="2", dates={"2": date(2024, 1, 1), "3": date(2025, 1, 1)})
    issues = run("W-A07", a)
    assert len(issues) == 1
    assert issues[0].evidence["days_overdue"] > 0


def test_w_a08_implementation_stale():
    a = make_activity(status="2", last_updated=datetime(2024, 1, 1, tzinfo=UTC))
    assert len(run("W-A08", a)) == 1


def test_w_a08_recent_update_ok():
    a = make_activity(status="2", last_updated=datetime(2026, 8, 1, tzinfo=UTC))
    assert run("W-A08", a) == []


def test_w_a09_transaction_after_last_updated():
    a = make_activity(
        last_updated=datetime(2025, 1, 1, tzinfo=UTC),
        transactions=[make_txn(on=date(2025, 6, 1))],
    )
    issues = run("W-A09", a)
    assert len(issues) == 1
    assert issues[0].item["kind"] == "transaction"


def test_e_a10_last_updated_in_future():
    a = make_activity(last_updated=datetime(2030, 1, 1, tzinfo=UTC))
    assert len(run("E-A10", a)) == 1


def test_e_a10_last_updated_today_ok():
    a = make_activity(last_updated=datetime(2026, 9, 11, tzinfo=UTC))
    assert run("E-A10", a) == []


def test_e_a11_no_start_date():
    a = make_activity(dates={"3": date(2027, 12, 31)})
    issues = run("E-A11", a)
    assert len(issues) == 1


def test_e_a11_planned_start_only_ok():
    a = make_activity(dates={"1": date(2024, 1, 1)})
    assert run("E-A11", a) == []
