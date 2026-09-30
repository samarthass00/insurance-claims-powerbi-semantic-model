import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import validate_model as vm  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def data():
    subprocess.run([sys.executable, "src/generate_data.py", "--policies", "800", "--out", "data"], cwd=ROOT, check=True)


def test_model_has_no_broken_references():
    model = vm.load_model()
    vm.check_references(model)
    assert model.errors == []
    assert {"Claim", "Policy", "Earned Premium", "Date"} <= set(model.columns)
    assert "Loss Ratio" in model.measures


def test_validator_detects_unknown_column_and_measure():
    model = vm.load_model()
    model.expressions = ["SUM ( Claim[Does Not Exist] )", "[Missing Measure] * 2"]
    vm.check_references(model)
    assert any("Does Not Exist" in e for e in model.errors)
    assert any("Missing Measure" in e for e in model.errors)


def test_every_relationship_is_many_to_one_on_a_unique_key():
    policy = pd.read_csv(ROOT / "data" / "dim_policy.csv")
    claims = pd.read_csv(ROOT / "data" / "fact_claim.csv")
    assert policy["policy_id"].is_unique
    assert claims["policy_id"].isin(policy["policy_id"]).all(), "orphan claims would be dropped by the relationship"


def test_reference_loss_ratio_matches_components():
    kpi = vm.reference_kpis().set_index("lob_key")
    total = kpi.loc["ALL"]
    assert total["loss_ratio"] == pytest.approx(total["incurred_loss"] / total["earned_premium"], abs=1e-4)
    assert kpi.drop("ALL")["claim_count"].sum() == total["claim_count"]


def test_rls_mapping_uses_only_fictitious_addresses():
    users = pd.read_csv(ROOT / "data" / "dim_user_region.csv")
    assert users["user_email"].str.endswith("@example.com").all()
