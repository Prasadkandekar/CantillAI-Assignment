import csv

import pytest

from engine import BatchFormatError, load_batch, read_batch
from tests.helpers import BATCH_PATH, ROOT, master_data


def count_rows(rel):
    with open(ROOT / rel, encoding="utf-8-sig") as fh:
        return sum(1 for _ in csv.DictReader(fh))


def test_sample_batch(raw_lines):
    assert len(raw_lines) == 186
    assert raw_lines[0].values["pr_no"] == "PR-26-00001"


def test_master_counts():
    m = master_data()
    assert len(m.items) == count_rows("master_data/item_master.csv")
    assert len(m.suppliers) == count_rows("master_data/supplier_master.csv")
    assert sum(len(v) for v in m.po_by_item.values()) == count_rows("master_data/po_history.csv")
    assert set(m.plants) == {"PUN1", "CHK1"}
    assert len(m.contracts) == count_rows("contracts/contract_register.csv") + 2
    assert m.suppliers["S020"].categories == ("Electrical Spares", "Capital Equipment")


def test_missing_columns_rejected():
    with pytest.raises(BatchFormatError, match="Missing required columns: plant, quantity"):
        load_batch(b"pr_no,pr_line,created_at,item_code,description,uom,need_by_date,urgency\n")


def test_extra_columns_warn_and_cp1252_decodes():
    header = BATCH_PATH.read_text(encoding="utf-8").splitlines()[0]
    data = (header + ",note\nPR-X,1,2026-11-02 10:00,,,PUN1,ITM-1001,caf\xe9,1,NOS,,2026-11-20,Normal,x\n").encode("cp1252")
    lines, warnings = read_batch(data)
    assert len(lines) == 1 and lines[0].values["description"] == "caf\xe9"
    assert warnings == ["Ignored extra columns: note"]
