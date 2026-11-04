from datetime import date
from decimal import Decimal

from treasurer.post import LocalCsvSink
from treasurer.reimburse import Reimbursement, totals_by_payer, validate


def test_validate_blocks_bad_paybacks():
    assert validate("Member A", "10", Decimal("31.07")) == (Decimal("10.00"), None)
    assert validate("Member A", "$31.07", Decimal("31.07"))[0] == Decimal("31.07")
    assert "overpay" in validate("Member A", "31.08", Decimal("31.07"))[1]
    assert validate("Member A", "0", Decimal("5"))[1]
    assert validate("Member A", "ten", Decimal("5"))[1]
    assert validate("(no payer)", "1", Decimal("5"))[1]


def test_csv_sink_keeps_reimbursements_per_event(tmp_path):
    sink = LocalCsvSink(tmp_path / "tx.csv")
    sink.record_reimbursement(Reimbursement("E1", "Member A", date(2026, 11, 20), Decimal("10.00"), "Zelle"))
    sink.record_reimbursement(Reimbursement("E1", "Member A", date(2026, 11, 21), Decimal("5.50"), "Cash"))
    sink.record_reimbursement(Reimbursement("E2", "Member A", date(2026, 11, 21), Decimal("1.00"), "Cash"))
    assert totals_by_payer(sink.reimbursements(), "E1") == {"Member A": Decimal("15.50")}
