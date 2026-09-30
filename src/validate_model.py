"""Static checks for the TMDL semantic model plus reference KPIs for reconciliation.

1. Every 'Table'[Column] reference in a measure or RLS filter points to a declared column.
2. Every [Measure] reference points to a declared measure.
3. Every relationship endpoint exists, and every sourceColumn exists in its CSV header.
4. Reference KPIs (loss ratio by line of business) are computed independently in pandas and
   written to docs/reference_kpis.csv so report totals can be reconciled after refresh.

Exit code is non-zero when any check fails, so the script can gate CI.
"""
from __future__ import annotations

import csv
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEF = ROOT / "ClaimsAnalytics.SemanticModel" / "definition"
DATA = ROOT / "data"
log = logging.getLogger("validate_model")

NAME = r"(?:'[^']+'|[A-Za-z_][\w]*)"
TABLE_RE = re.compile(rf"^table ({NAME})", re.M)
COLUMN_RE = re.compile(rf"^\tcolumn ({NAME})", re.M)
MEASURE_RE = re.compile(rf"^\tmeasure ({NAME}) = (.+)$", re.M)
SOURCE_RE = re.compile(r"^\t\tsourceColumn: (\w+)$", re.M)
CSV_RE = re.compile(r'DataFolder & "\\\\?(\w+)\.csv"')
COLREF_RE = re.compile(r"('[^']+'|\b[A-Za-z_]\w*)\[([^\]]+)\]")
MEASREF_RE = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
REL_RE = re.compile(rf"(fromColumn|toColumn): ({NAME})\.({NAME})")
PERM_RE = re.compile(r"^\ttablePermission .+? = (.+)$", re.M)


def unquote(name: str) -> str:
    return name[1:-1] if name.startswith("'") else name


@dataclass
class Model:
    columns: dict[str, set[str]] = field(default_factory=dict)
    measures: dict[str, str] = field(default_factory=dict)
    expressions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def load_model() -> Model:
    model = Model()
    for path in sorted((DEF / "tables").glob("*.tmdl")):
        text = path.read_text(encoding="utf-8")
        table = unquote(TABLE_RE.search(text).group(1))
        model.columns[table] = {unquote(c) for c in COLUMN_RE.findall(text)}
        for name, expr in MEASURE_RE.findall(text):
            model.measures[unquote(name)] = expr
        csv_match = CSV_RE.search(text)
        if csv_match:
            header = next(csv.reader((DATA / f"{csv_match.group(1)}.csv").open(encoding="utf-8")))
            for src in SOURCE_RE.findall(text):
                if src not in header:
                    model.errors.append(f"{table}: sourceColumn '{src}' not in {csv_match.group(1)}.csv")
    model.expressions = list(model.measures.values())
    for path in (DEF / "roles").glob("*.tmdl"):
        model.expressions += PERM_RE.findall(path.read_text(encoding="utf-8"))
    return model


def check_references(model: Model) -> None:
    for expr in model.expressions:
        for table, column in COLREF_RE.findall(expr):
            t = unquote(table)
            if t not in model.columns:
                model.errors.append(f"unknown table {t!r} in: {expr}")
            elif column not in model.columns[t]:
                model.errors.append(f"unknown column {t}[{column}] in: {expr}")
        stripped = COLREF_RE.sub("", expr)
        for ref in MEASREF_RE.findall(stripped):
            if ref not in model.measures:
                model.errors.append(f"unknown measure [{ref}] in: {expr}")
    for side, table, column in REL_RE.findall((DEF / "relationships.tmdl").read_text(encoding="utf-8")):
        t, c = unquote(table), unquote(column)
        if c not in model.columns.get(t, set()):
            model.errors.append(f"relationship {side} {t}.{c} does not exist")


def reference_kpis() -> pd.DataFrame:
    policy = pd.read_csv(DATA / "dim_policy.csv")
    lob = pd.read_csv(DATA / "dim_line_of_business.csv")
    earned = pd.read_csv(DATA / "fact_earned_premium.csv").merge(policy[["policy_id", "lob_key"]], on="policy_id")
    claims = pd.read_csv(DATA / "fact_claim.csv").merge(policy[["policy_id", "lob_key"]], on="policy_id")
    claims["incurred"] = claims["paid_amount"] + claims["case_reserve"]
    kpi = (
        earned.groupby("lob_key")["earned_premium"].sum().to_frame("earned_premium")
        .join(claims.groupby("lob_key").agg(incurred_loss=("incurred", "sum"), claim_count=("claim_id", "count")))
        .join(lob.set_index("lob_key")[["line_of_business", "target_loss_ratio"]])
        .reset_index()
    )
    kpi["loss_ratio"] = (kpi["incurred_loss"] / kpi["earned_premium"]).round(4)
    total = kpi[["earned_premium", "incurred_loss", "claim_count"]].sum()
    kpi.loc[len(kpi)] = {"lob_key": "ALL", "line_of_business": "Total", **total.to_dict(),
                         "target_loss_ratio": None, "loss_ratio": round(total.incurred_loss / total.earned_premium, 4)}
    return kpi[["lob_key", "line_of_business", "earned_premium", "incurred_loss", "claim_count", "loss_ratio", "target_loss_ratio"]]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not (DATA / "dim_policy.csv").exists():
        log.error("data/ is empty - run: python src/generate_data.py")
        return 2
    model = load_model()
    check_references(model)
    log.info("tables=%d measures=%d expressions checked=%d", len(model.columns), len(model.measures), len(model.expressions))
    for err in model.errors:
        log.error(err)
    kpi = reference_kpis()
    (ROOT / "docs").mkdir(exist_ok=True)
    kpi.round(2).to_csv(ROOT / "docs" / "reference_kpis.csv", index=False)
    log.info("reference KPIs written to docs/reference_kpis.csv\n%s", kpi.round(3).to_string(index=False))
    return 1 if model.errors else 0


if __name__ == "__main__":
    sys.exit(main())
