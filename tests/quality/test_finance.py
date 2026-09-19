from datetime import date

from tests.quality.conftest import make_activity, make_budget, make_txn, run


def test_e_b02_value_date_outside_period():
    a = make_activity(budgets=[make_budget(value_date=date(2024, 1, 1))])
    assert len(run("E-B02", a)) == 1


def test_e_b02_value_date_inside_period_ok():
    a = make_activity(budgets=[make_budget(value_date=date(2025, 6, 1))])
    assert run("E-B02", a) == []


def test_e_b03_negative_budget():
    a = make_activity(budgets=[make_budget(value=-100.0)])
    issues = run("E-B03", a)
    assert len(issues) == 1
    assert "-100.00" in issues[0].message


def test_w_b05_overlapping_budgets():
    a = make_activity(
        budgets=[
            make_budget(start=date(2025, 1, 1), end=date(2025, 12, 31), index=0),
            make_budget(start=date(2025, 6, 1), end=date(2026, 5, 31), index=1),
        ]
    )
    assert len(run("W-B05", a)) == 1


def test_w_b05_adjacent_budgets_ok():
    a = make_activity(
        budgets=[
            make_budget(start=date(2025, 1, 1), end=date(2025, 12, 31), index=0),
            make_budget(start=date(2026, 1, 1), end=date(2026, 12, 31), index=1),
        ]
    )
    assert run("W-B05", a) == []


def test_w_b06_short_budget():
    a = make_activity(budgets=[make_budget(start=date(2025, 1, 1), end=date(2025, 1, 5))])
    assert len(run("W-B06", a)) == 1


def test_w_b07_zero_values():
    a = make_activity(budgets=[make_budget(value=0.0)], transactions=[make_txn(value=0.0)])
    issues = run("W-B07", a)
    assert {i.item["kind"] for i in issues} == {"budget", "transaction"}


def test_w_b08_negative_disbursement():
    a = make_activity(transactions=[make_txn(type="3", value=-50.0)])
    issues = run("W-B08", a)
    assert len(issues) == 1
    assert "Local NGO" in issues[0].message


def test_w_b08_negative_commitment_not_flagged_here():
    a = make_activity(transactions=[make_txn(type="2", value=-50.0)])
    assert run("W-B08", a) == []


def test_e_b09_disbursed_exceeds_committed():
    a = make_activity(
        transactions=[
            make_txn(type="2", value=100.0, index=0),
            make_txn(type="3", value=80.0, index=1),
            make_txn(type="4", value=30.0, index=2),
        ]
    )
    issues = run("E-B09", a)
    assert len(issues) == 1
    assert issues[0].evidence["disbursed_and_expended"] == 110.0


def test_e_b09_within_commitment_ok():
    a = make_activity(
        transactions=[make_txn(type="2", value=100.0, index=0), make_txn(type="3", value=100.0, index=1)]
    )
    assert run("E-B09", a) == []


def test_w_b10_disbursed_without_commitment():
    a = make_activity(transactions=[make_txn(type="3", value=100.0)])
    assert len(run("W-B10", a)) == 1


def test_w_b11_closed_without_disbursement():
    a = make_activity(status="4", transactions=[make_txn(type="2", value=100.0)])
    assert len(run("W-B11", a)) == 1


def test_w_b12_closed_not_fully_disbursed():
    a = make_activity(
        status="3",
        transactions=[make_txn(type="2", value=100.0, index=0), make_txn(type="3", value=60.0, index=1)],
    )
    issues = run("W-B12", a)
    assert len(issues) == 1
    assert issues[0].evidence["ratio"] == 0.6


def test_w_b12_fully_disbursed_ok():
    a = make_activity(
        status="3",
        transactions=[make_txn(type="2", value=100.0, index=0), make_txn(type="3", value=99.5, index=1)],
    )
    assert run("W-B12", a) == []


def test_w_b13_transaction_outside_dates():
    a = make_activity(
        dates={"2": date(2024, 1, 15), "4": date(2025, 1, 1)},
        transactions=[
            make_txn(on=date(2023, 12, 1), index=0),
            make_txn(on=date(2025, 6, 1), index=1),
            make_txn(on=date(2024, 6, 1), index=2),
        ],
    )
    issues = run("W-B13", a)
    assert len(issues) == 2


def test_w_b14_receiver_is_reporting_org():
    a = make_activity(transactions=[make_txn(receiver="test org")])
    assert len(run("W-B14", a)) == 1


def test_w_b15_duplicate_transaction():
    a = make_activity(transactions=[make_txn(index=0), make_txn(index=1), make_txn(index=2)])
    issues = run("W-B15", a)
    assert len(issues) == 1  # reported once per duplicated key


def test_w_b16_outgoing_without_receiver():
    a = make_activity(transactions=[make_txn(receiver=None, receiver_type=None)])
    assert len(run("W-B16", a)) == 1


def test_w_b16_incoming_without_receiver_ok():
    a = make_activity(transactions=[make_txn(type="1", receiver=None, receiver_type=None)])
    assert run("W-B16", a) == []


def test_w_b17_receiver_type_other():
    a = make_activity(transactions=[make_txn(receiver_type="90")])
    assert len(run("W-B17", a)) == 1


def test_w_b18_value_date_far():
    a = make_activity(transactions=[make_txn(on=date(2025, 1, 1), value_date=date(2023, 1, 1))])
    issues = run("W-B18", a)
    assert len(issues) == 1
    assert issues[0].evidence["gap_days"] == 731


def test_w_b19_tiny_and_outlier_values():
    a = make_activity(transactions=[make_txn(value=0.5, index=0), make_txn(value=1e9, index=1)])
    issues = run("W-B19", a, transaction_value_p99=1e6)
    assert len(issues) == 2


def test_w_b19_no_p99_only_tiny():
    a = make_activity(transactions=[make_txn(value=0.5, index=0), make_txn(value=1e9, index=1)])
    assert len(run("W-B19", a)) == 1


def test_w_b20_budget_vs_commitment():
    a = make_activity(
        transactions=[make_txn(type="2", value=100.0)],
        budgets=[make_budget(value=300.0)],
    )
    assert len(run("W-B20", a)) == 1


def test_w_b21_year_boundary_dates():
    a = make_activity(
        transactions=[make_txn(on=date(2025, 1, 1), index=0), make_txn(on=date(2025, 12, 31), index=1)]
    )
    assert len(run("W-B21", a)) == 2

