import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_generator_is_deterministic(tmp_path):
    for run in ("a", "b"):
        subprocess.run([sys.executable, "src/generate_data.py", "--policies", "300", "--seed", "7",
                        "--out", str(tmp_path / run)], cwd=ROOT, check=True)
    a = pd.read_csv(tmp_path / "a" / "fact_claim.csv")
    b = pd.read_csv(tmp_path / "b" / "fact_claim.csv")
    pd.testing.assert_frame_equal(a, b)


def test_claim_amounts_are_consistent(tmp_path):
    subprocess.run([sys.executable, "src/generate_data.py", "--policies", "500", "--out", str(tmp_path)], cwd=ROOT, check=True)
    claims = pd.read_csv(tmp_path / "fact_claim.csv", parse_dates=["loss_date", "report_date", "close_date"])
    assert (claims["paid_amount"] >= 0).all() and (claims["case_reserve"] >= -0.01).all()
    assert (claims["report_date"] >= claims["loss_date"]).all()
    closed = claims[claims["claim_status"] == "Closed"]
    assert closed["close_date"].notna().all()
    assert (closed["case_reserve"].abs() < 0.01).all()


def test_rejects_non_positive_policy_count(tmp_path):
    result = subprocess.run([sys.executable, "src/generate_data.py", "--policies", "0", "--out", str(tmp_path)],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
