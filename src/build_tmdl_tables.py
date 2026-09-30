"""Render the import tables of the TMDL model from one column specification.

Keeping column names, source columns and data types in one place means the CSV schema,
the Power Query type step and the model metadata cannot drift apart. Run after editing SPEC:

    python src/build_tmdl_tables.py
"""
from __future__ import annotations

from pathlib import Path

TABLES_DIR = Path(__file__).resolve().parents[1] / "ClaimsAnalytics.SemanticModel" / "definition" / "tables"

M_TYPES = {"string": "type text", "int64": "Int64.Type", "double": "type number",
           "decimal": "Currency.Type", "dateTime": "type date", "boolean": "type logical"}

# table name -> (csv file, hidden?, [(column name, source column, dataType, formatString or None, hidden?)])
SPEC = {
    "Line of Business": ("dim_line_of_business", False, [
        ("LOB Key", "lob_key", "string", None, True),
        ("Line of Business", "line_of_business", "string", None, False),
        ("Target Loss Ratio", "target_loss_ratio", "double", "0.0%", False),
    ]),
    "Region": ("dim_region", False, [
        ("Region Key", "region_key", "string", None, True),
        ("Region", "region", "string", None, False),
    ]),
    "Policy": ("dim_policy", False, [
        ("Policy ID", "policy_id", "string", None, False),
        ("LOB Key", "lob_key", "string", None, True),
        ("Region Key", "region_key", "string", None, True),
        ("Effective Date", "effective_date", "dateTime", "yyyy-mm-dd", False),
        ("Expiration Date", "expiration_date", "dateTime", "yyyy-mm-dd", False),
        ("Written Premium", "written_premium", "decimal", "\\$#,0.00", True),
        ("Is Renewal", "is_renewal", "boolean", None, False),
    ]),
    "Earned Premium": ("fact_earned_premium", False, [
        ("Policy ID", "policy_id", "string", None, True),
        ("Earned Month", "earned_month", "dateTime", "yyyy-mm-dd", True),
        ("Earned Premium", "earned_premium", "decimal", "\\$#,0.00", True),
    ]),
    "Claim": ("fact_claim", False, [
        ("Claim ID", "claim_id", "string", None, False),
        ("Policy ID", "policy_id", "string", None, True),
        ("Loss Date", "loss_date", "dateTime", "yyyy-mm-dd", False),
        ("Report Date", "report_date", "dateTime", "yyyy-mm-dd", False),
        ("Close Date", "close_date", "dateTime", "yyyy-mm-dd", False),
        ("Claim Status", "claim_status", "string", None, False),
        ("Paid Amount", "paid_amount", "decimal", "\\$#,0.00", True),
        ("Case Reserve", "case_reserve", "decimal", "\\$#,0.00", True),
    ]),
    "User Region": ("dim_user_region", True, [
        ("User Email", "user_email", "string", None, False),
        ("Region Key", "region_key", "string", None, False),
    ]),
}

# Measures live on the table whose grain they aggregate.
MEASURES = {
    "Earned Premium": [
        ("Earned Premium Amount", "SUM ( 'Earned Premium'[Earned Premium] )", "\\$#,0", "Premium earned in the period (monthly pro-rata)."),
        ("Earned Premium PY", "CALCULATE ( [Earned Premium Amount], SAMEPERIODLASTYEAR ( 'Date'[Date] ) )", "\\$#,0", "Earned premium for the same period last year."),
        ("Earned Premium YoY %", "DIVIDE ( [Earned Premium Amount] - [Earned Premium PY], [Earned Premium PY] )", "0.0%", "Year-over-year change in earned premium."),
    ],
    "Policy": [
        ("Policy Count", "COUNTROWS ( Policy )", "#,0", "Number of policies in filter context."),
        ("Written Premium", "CALCULATE ( SUM ( Policy[Written Premium] ), USERELATIONSHIP ( Policy[Effective Date], 'Date'[Date] ) )", "\\$#,0", "Premium written on policies effective in the period."),
        ("Renewal Share %", "DIVIDE ( CALCULATE ( [Policy Count], Policy[Is Renewal] = TRUE () ), [Policy Count] )", "0.0%", "Share of policies that are renewals."),
    ],
    "Claim": [
        ("Claim Count", "COUNTROWS ( Claim )", "#,0", "Claims by loss date."),
        ("Claims Reported", "CALCULATE ( [Claim Count], USERELATIONSHIP ( Claim[Report Date], 'Date'[Date] ) )", "#,0", "Claims by report date (inactive relationship)."),
        ("Open Claims", "CALCULATE ( [Claim Count], Claim[Claim Status] = \"Open\" )", "#,0", "Claims not yet closed."),
        ("Paid Loss", "SUM ( Claim[Paid Amount] )", "\\$#,0", "Loss payments to date."),
        ("Case Reserve Amount", "SUM ( Claim[Case Reserve] )", "\\$#,0", "Outstanding case reserves."),
        ("Incurred Loss", "[Paid Loss] + [Case Reserve Amount]", "\\$#,0", "Paid loss plus case reserves."),
        ("Loss Ratio", "DIVIDE ( [Incurred Loss], [Earned Premium Amount] )", "0.0%", "Incurred loss / earned premium (calendar-period view, synthetic data)."),
        ("Loss Ratio vs Target", "[Loss Ratio] - MAX ( 'Line of Business'[Target Loss Ratio] )", "+0.0%;-0.0%", "Gap to target; meaningful when one line of business is in context."),
        ("Average Severity", "DIVIDE ( [Incurred Loss], [Claim Count] )", "\\$#,0", "Incurred loss per claim."),
        ("Claim Frequency per 100 Policies", "DIVIDE ( [Claim Count], [Policy Count] ) * 100", "0.00", "Claims per 100 policies in context."),
        ("Avg Report Lag Days", "AVERAGEX ( Claim, DATEDIFF ( Claim[Loss Date], Claim[Report Date], DAY ) )", "0.0", "Days from loss to first report."),
        ("Avg Days to Close", "AVERAGEX ( FILTER ( Claim, NOT ISBLANK ( Claim[Close Date] ) ), DATEDIFF ( Claim[Report Date], Claim[Close Date], DAY ) )", "0.0", "Cycle time for closed claims."),
    ],
}


def q(name: str) -> str:
    return f"'{name}'" if " " in name else name


def render(table: str) -> str:
    csv, hidden, cols = SPEC[table]
    out = [f"table {q(table)}"]
    if hidden:
        out.append("\tisHidden")
    out.append("")
    for name, expr, fmt, desc in MEASURES.get(table, []):
        out += [f"\t/// {desc}", f"\tmeasure {q(name)} = {expr}", f"\t\tformatString: {fmt}", ""]
    for name, src, dtype, fmt, col_hidden in cols:
        out.append(f"\tcolumn {q(name)}")
        out.append(f"\t\tdataType: {dtype}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        if col_hidden:
            out.append("\t\tisHidden")
        out.append("\t\tsummarizeBy: none")
        out.append(f"\t\tsourceColumn: {src}")
        out.append("")
    types = ", ".join(f'{{"{src}", {M_TYPES[dtype]}}}' for _, src, dtype, _, _ in cols)
    out += [
        f"\tpartition {q(table)} = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\t\tlet",
        f'\t\t\t\t    Source = Csv.Document(File.Contents(DataFolder & "\\{csv}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "\t\t\t\t    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f'\t\t\t\t    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")',
        "\t\t\t\tin",
        "\t\t\t\t    Typed",
        "",
    ]
    return "\n".join(out)


def main() -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    for table in SPEC:
        (TABLES_DIR / f"{table}.tmdl").write_text(render(table), encoding="utf-8")
        print(f"wrote {table}.tmdl")


if __name__ == "__main__":
    main()
