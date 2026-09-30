# Measure catalog

Generated from `src/build_tmdl_tables.py`.

| Measure | Table | DAX | Purpose |
|---|---|---|---|
| Earned Premium Amount | Earned Premium | `SUM ( 'Earned Premium'[Earned Premium] )` | Premium earned in the period (monthly pro-rata). |
| Earned Premium PY | Earned Premium | `CALCULATE ( [Earned Premium Amount], SAMEPERIODLASTYEAR ( 'Date'[Date] ) )` | Earned premium for the same period last year. |
| Earned Premium YoY % | Earned Premium | `DIVIDE ( [Earned Premium Amount] - [Earned Premium PY], [Earned Premium PY] )` | Year-over-year change in earned premium. |
| Policy Count | Policy | `COUNTROWS ( Policy )` | Number of policies in filter context. |
| Written Premium | Policy | `CALCULATE ( SUM ( Policy[Written Premium] ), USERELATIONSHIP ( Policy[Effective Date], 'Date'[Date] ) )` | Premium written on policies effective in the period. |
| Renewal Share % | Policy | `DIVIDE ( CALCULATE ( [Policy Count], Policy[Is Renewal] = TRUE () ), [Policy Count] )` | Share of policies that are renewals. |
| Claim Count | Claim | `COUNTROWS ( Claim )` | Claims by loss date. |
| Claims Reported | Claim | `CALCULATE ( [Claim Count], USERELATIONSHIP ( Claim[Report Date], 'Date'[Date] ) )` | Claims by report date (inactive relationship). |
| Open Claims | Claim | `CALCULATE ( [Claim Count], Claim[Claim Status] = "Open" )` | Claims not yet closed. |
| Paid Loss | Claim | `SUM ( Claim[Paid Amount] )` | Loss payments to date. |
| Case Reserve Amount | Claim | `SUM ( Claim[Case Reserve] )` | Outstanding case reserves. |
| Incurred Loss | Claim | `[Paid Loss] + [Case Reserve Amount]` | Paid loss plus case reserves. |
| Loss Ratio | Claim | `DIVIDE ( [Incurred Loss], [Earned Premium Amount] )` | Incurred loss / earned premium (calendar-period view, synthetic data). |
| Loss Ratio vs Target | Claim | `[Loss Ratio] - MAX ( 'Line of Business'[Target Loss Ratio] )` | Gap to target; meaningful when one line of business is in context. |
| Average Severity | Claim | `DIVIDE ( [Incurred Loss], [Claim Count] )` | Incurred loss per claim. |
| Claim Frequency per 100 Policies | Claim | `DIVIDE ( [Claim Count], [Policy Count] ) * 100` | Claims per 100 policies in context. |
| Avg Report Lag Days | Claim | `AVERAGEX ( Claim, DATEDIFF ( Claim[Loss Date], Claim[Report Date], DAY ) )` | Days from loss to first report. |
| Avg Days to Close | Claim | `AVERAGEX ( FILTER ( Claim, NOT ISBLANK ( Claim[Close Date] ) ), DATEDIFF ( Claim[Report Date], Claim[Close Date], DAY ) )` | Cycle time for closed claims. |
