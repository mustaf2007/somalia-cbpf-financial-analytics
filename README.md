# Somalia CBPF Contributions Analytics Dashboard

An interactive Streamlit dashboard for exploring Somalia Country-Based Pooled Fund (CBPF) contribution records, with donor, pledge, payment, currency and data-quality analysis.

## Features

- Upload a CBPF contributions CSV through the sidebar
- Clean text fields, currencies, amounts and dates
- Treat source placeholder dates beginning with `0001-01-01` as missing
- Calculate pledge/payment differences and payment ratios
- Explore annual pledge and payment trends
- Rank donors and inspect donor payment concentration
- Review original local-currency composition without combining unlike currencies
- Run basic data-quality checks
- Download filtered cleaned data, KPI summaries and annual summaries

## Run locally

Requirements: Python 3.10 or newer.

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Upload your authorized copy of `som_cbpf_contributions.csv` using the dashboard sidebar. The source dataset is intentionally **not included** in this public repository. Do not commit it unless you have confirmed that redistribution is permitted.

## Data interpretation and limitations

- `PledgeAmt` and `PaidAmt` are treated as standardized source amount fields. The dashboard does **not** assume they are USD. Verify the official source data dictionary or metadata before assigning a currency label.
- `PledgeAmtLocal` and `PaidAmtLocal` are local-currency values. Do not aggregate across currencies without applying a documented and validated conversion method.
- The dataset records contributions. It does not by itself measure allocations, expenditure, project outputs or beneficiary outcomes.
- Future fiscal-year records and records with zero payments are not automatically overdue.
- Payments greater than pledges are flagged for review, not automatically treated as errors.
- The dashboard is descriptive and should not be used as a standalone fraud, credit or humanitarian-impact decision system.

## Repository contents

- `app.py` — Streamlit dashboard and data preparation functions
- `requirements.txt` — Python dependencies
- `.gitignore` — excludes local datasets, virtual environments and temporary files

## Suggested extensions

1. Integrate validated OCHA allocation and expenditure datasets.
2. Add source-backed exchange-rate metadata and conversion rules.
3. Consider forecasting only after assessing data frequency, completeness and historical stability.

## License

MIT. See [LICENSE](LICENSE).
