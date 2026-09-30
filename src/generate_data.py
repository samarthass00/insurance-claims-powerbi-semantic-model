"""Generate a synthetic property & casualty insurance dataset for the ClaimsAnalytics semantic model.

All values are random and fictitious. No real policy, claim, or customer data is used.

Usage:
    python src/generate_data.py --policies 5000 --seed 42 --out data
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("generate_data")

LINES_OF_BUSINESS = [
    ("LOB01", "Commercial Auto", 0.62),
    ("LOB02", "General Liability", 0.55),
    ("LOB03", "Workers Compensation", 0.68),
    ("LOB04", "Commercial Property", 0.48),
]
REGIONS = [
    ("R01", "Northeast"),
    ("R02", "Southeast"),
    ("R03", "Midwest"),
    ("R04", "West"),
]
START = pd.Timestamp("2023-01-01")
END = pd.Timestamp("2025-12-31")


def build_dimensions() -> tuple[pd.DataFrame, pd.DataFrame]:
    lob = pd.DataFrame(LINES_OF_BUSINESS, columns=["lob_key", "line_of_business", "target_loss_ratio"])
    region = pd.DataFrame(REGIONS, columns=["region_key", "region"])
    return lob, region


def build_user_region() -> pd.DataFrame:
    """RLS mapping for the 'Regional Manager' role. example.com addresses are reserved and fictitious."""
    rows = [(f"{name.lower()}.manager@example.com", key) for key, name in REGIONS]
    rows += [("national.director@example.com", key) for key, _ in REGIONS]
    return pd.DataFrame(rows, columns=["user_email", "region_key"])


def build_policies(n: int, rng: np.random.Generator) -> pd.DataFrame:
    days = (END - START).days - 365
    effective = START + pd.to_timedelta(rng.integers(0, days, n), unit="D")
    policies = pd.DataFrame(
        {
            "policy_id": [f"P{idx:06d}" for idx in range(1, n + 1)],
            "lob_key": rng.choice([l[0] for l in LINES_OF_BUSINESS], n, p=[0.3, 0.3, 0.2, 0.2]),
            "region_key": rng.choice([r[0] for r in REGIONS], n),
            "effective_date": effective,
            "written_premium": rng.lognormal(mean=9.2, sigma=0.6, size=n).round(2),
            "is_renewal": rng.random(n) < 0.45,
        }
    )
    policies["expiration_date"] = policies["effective_date"] + pd.DateOffset(years=1) - pd.Timedelta(days=1)
    return policies


def build_earned_premium(policies: pd.DataFrame) -> pd.DataFrame:
    """Spread written premium evenly across the 12 policy months (monthly pro-rata earning)."""
    rows = []
    for p in policies.itertuples(index=False):
        monthly = round(p.written_premium / 12, 2)
        for m in range(12):
            month_start = (p.effective_date + pd.DateOffset(months=m)).to_period("M").to_timestamp()
            rows.append((p.policy_id, month_start, monthly))
    earned = pd.DataFrame(rows, columns=["policy_id", "earned_month", "earned_premium"])
    return earned[earned["earned_month"] <= END]


def build_claims(policies: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    lob_lr = {l[0]: l[2] for l in LINES_OF_BUSINESS}
    has_claim = rng.random(len(policies)) < 0.22
    claimants = policies[has_claim].reset_index(drop=True)
    n = len(claimants)
    loss_date = claimants["effective_date"] + pd.to_timedelta(rng.integers(0, 365, n), unit="D")
    report_lag = pd.to_timedelta(rng.gamma(2.0, 6.0, n).astype(int), unit="D")
    close_lag = pd.to_timedelta(rng.gamma(3.0, 40.0, n).astype(int), unit="D")
    # Severity is scaled so each line trends toward its target loss ratio.
    severity = claimants.apply(lambda r: r.written_premium * lob_lr[r.lob_key] / 0.22, axis=1)
    incurred = (severity * rng.lognormal(0, 0.5, n)).round(2)
    report_date = loss_date + report_lag
    close_date = report_date + close_lag
    is_open = close_date > END
    paid_share = np.where(is_open, rng.uniform(0.1, 0.7, n), 1.0)
    claims = pd.DataFrame(
        {
            "claim_id": [f"C{idx:06d}" for idx in range(1, n + 1)],
            "policy_id": claimants["policy_id"],
            "loss_date": loss_date,
            "report_date": report_date,
            "close_date": close_date.where(~is_open),
            "claim_status": np.where(is_open, "Open", "Closed"),
            "paid_amount": (incurred * paid_share).round(2),
        }
    )
    claims["case_reserve"] = (incurred - claims["paid_amount"]).round(2)
    return claims[claims["report_date"] <= END].reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policies", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("data"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.policies <= 0:
        raise SystemExit("--policies must be positive")
    rng = np.random.default_rng(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)

    lob, region = build_dimensions()
    policies = build_policies(args.policies, rng)
    tables = {
        "dim_line_of_business": lob,
        "dim_region": region,
        "dim_policy": policies,
        "fact_earned_premium": build_earned_premium(policies),
        "fact_claim": build_claims(policies, rng),
        "dim_user_region": build_user_region(),
    }
    for name, df in tables.items():
        for col in df.select_dtypes(include="bool").columns:
            df[col] = df[col].map({True: "true", False: "false"})  # Power Query-friendly logicals
        path = args.out / f"{name}.csv"
        df.to_csv(path, index=False, date_format="%Y-%m-%d")
        log.info("wrote %s (%d rows)", path, len(df))


if __name__ == "__main__":
    main()
