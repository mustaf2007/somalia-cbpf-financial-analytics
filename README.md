# Somalia CBPF Contributions Analytics Dashboard

An interactive Streamlit dashboard for exploring Somalia Country-Based Pooled Fund (CBPF) contribution records, with donor, pledge, payment, currency and data-quality analysis.

## Features

- Automatically retrieve the latest published Somalia CBPF contributions CSV from the OCHA Humanitarian Data Exchange (HDX)
- Optionally upload another CBPF contributions CSV through the sidebar
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

The dashboard downloads the CSV directly from the official [OCHA HDX Somalia CBPF dataset](https://data.humdata.org/dataset/520c52a6-6caf-4cba-aecb-a57c063bffc9) when it starts. The download is cached for six hours per app session to reduce repeated requests. You may still upload another CSV through the sidebar. The source data file is not copied into this GitHub repository; the app retrieves it from HDX.

## Data source and attribution

The app retrieves `som_cbpf_contributions.csv` from OCHA's Humanitarian Data Exchange (HDX), dataset **Somalia - CBPF Allocations and Contributions**. Please review the dataset's current metadata and licensing terms on HDX. Attribute OCHA/HDX when reusing the data and check the dataset page for any specific conditions.

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
