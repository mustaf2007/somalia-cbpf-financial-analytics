"""
Somalia CBPF Contributions — Financial Analytics Dashboard
Run:
    pip install -r requirements.txt
    streamlit run app.py

Upload som_cbpf_contributions.csv in the sidebar. The dataset is intentionally
not bundled with this public repository.
Important: PledgeAmt and PaidAmt are source-standardized fields. Confirm their
reporting currency from source metadata before labeling them USD.
"""
from pathlib import Path
from io import BytesIO
import requests
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Somalia CBPF Financial Intelligence", page_icon="📊", layout="wide")

REQUIRED = ["FiscalYear", "DonorName", "PledgeAmt", "PaidAmt"]
DATE_COLS = ["PledgeDate", "PipeLineDate", "PaidDate", "ExpectedDate"]
AMOUNT_COLS = ["PledgeAmt", "PaidAmt", "PledgeAmtLocal", "PaidAmtLocal",
               "PledgeAmtCurrencyExchangeRate", "PaidAmtCurrencyExchangeRate"]


def clean_data(raw: pd.DataFrame) -> pd.DataFrame:
    """Clean a source CBPF contributions dataframe and add derived measures."""
    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Required columns missing: {missing}")

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

    for col in ["PledgeAmtLocalCurrency", "PaidAmtLocalCurrency"]:
        if col in df:
            df[col] = (df[col].astype("string").str.strip().str.upper()
                       .replace({"": pd.NA, "NAN": pd.NA}))

    for col in AMOUNT_COLS:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["FiscalYear"] = pd.to_numeric(df["FiscalYear"], errors="coerce").astype("Int64")

    # The source uses 0001-01-01 as a placeholder for missing dates.
    for col in DATE_COLS:
        if col in df:
            values = df[col].astype("string").str.strip()
            values = values.mask(values.str.startswith("0001-01-01", na=False))
            df[col] = pd.to_datetime(values, errors="coerce", utc=True).dt.tz_convert(None)

    df["DonorName"] = df["DonorName"].astype("string").str.strip()
    if "CountryCode" in df:
        df["CountryCode"] = df["CountryCode"].astype("string").str.strip().str.upper()

    df["UnpaidBalance"] = (df["PledgeAmt"] - df["PaidAmt"]).clip(lower=0)
    df["PaymentRatio"] = np.where(
        df["PledgeAmt"] > 0, df["PaidAmt"] / df["PledgeAmt"], np.nan
    )
    df["PledgeYear"] = df["PledgeDate"].dt.year if "PledgeDate" in df else pd.NA
    df["PaidYear"] = df["PaidDate"].dt.year if "PaidDate" in df else pd.NA
    return df


def top_share(series: pd.Series, n: int = 5) -> float:
    total = series.sum()
    return float(series.nlargest(n).sum() / total) if total else np.nan


def make_metrics(df: pd.DataFrame) -> dict:
    pledge = df["PledgeAmt"].sum(min_count=1)
    paid = df["PaidAmt"].sum(min_count=1)
    balance = (df["PledgeAmt"] - df["PaidAmt"]).sum(min_count=1)
    donor_paid = df.groupby("DonorName", dropna=False)["PaidAmt"].sum().sort_values(ascending=False)
    shares = donor_paid / donor_paid.sum() if donor_paid.sum() else donor_paid * np.nan
    hhi = float((shares.dropna() ** 2).sum()) if len(shares.dropna()) else np.nan
    return {
        "records": len(df),
        "donors": df["DonorName"].nunique(),
        "years": int(df["FiscalYear"].nunique()),
        "pledges": pledge,
        "payments": paid,
        "difference": balance,
        "payment_ratio": paid / pledge if pledge else np.nan,
        "top5_share": top_share(donor_paid, 5),
        "hhi": hhi,
        "zero_payment_rows": int((df["PaidAmt"].fillna(0) == 0).sum()),
    }


def money(value) -> str:
    return "—" if pd.isna(value) else f"{value:,.2f}"


st.title("Somalia Humanitarian Financing Intelligence")
st.caption("Country-Based Pooled Fund (CBPF) contributions • donor, pledge, payment and concentration analysis")

SOURCE_CSV_URL = "https://data.humdata.org/dataset/520c52a6-6caf-4cba-aecb-a57c063bffc9/resource/0e12f814-0de7-471e-9dfb-35a4fe6200ab/download/som_cbpf_contributions.csv"

@st.cache_data(ttl=21600, show_spinner=False)
def load_hdx_csv():
    """Download the latest published CSV from the official HDX resource."""
    response = requests.get(SOURCE_CSV_URL, timeout=45)
    response.raise_for_status()
    response.encoding = "utf-8"
    return pd.read_csv(BytesIO(response.content)), response.headers.get("Last-Modified")

uploaded = st.sidebar.file_uploader("Upload another CBPF contributions CSV (optional)", type=["csv"])
default_path = Path(__file__).parent / "som_cbpf_contributions.csv"
source_status = ""
if uploaded is not None:
    raw = pd.read_csv(uploaded)
    source_status = "Uploaded CSV"
elif default_path.exists():
    raw = pd.read_csv(default_path)
    source_status = "Local CSV"
else:
    try:
        with st.spinner("Loading the latest Somalia CBPF dataset from OCHA HDX..."):
            raw, source_modified = load_hdx_csv()
        source_status = "OCHA HDX live dataset"
    except Exception as exc:
        st.error(f"Could not retrieve the OCHA HDX dataset automatically: {exc}")
        st.info("You can still upload an authorized CSV using the sidebar. Check the source link below.")
        st.link_button("Open the official HDX dataset", "https://data.humdata.org/dataset/520c52a6-6caf-4cba-aecb-a57c063bffc9")
        st.stop()

st.caption(f"Data source: {source_status} • Original dataset: Somalia - CBPF Allocations and Contributions (OCHA)")
st.markdown("[View source dataset and licensing information on HDX](https://data.humdata.org/dataset/520c52a6-6caf-4cba-aecb-a57c063bffc9)")

try:
    df = clean_data(raw)
except Exception as exc:
    st.error(f"Could not process this file: {exc}")
    st.stop()

st.sidebar.header("Dashboard filters")
years = sorted(df["FiscalYear"].dropna().astype(int).unique())
if years:
    year_range = st.sidebar.slider(
        "Fiscal year range", int(min(years)), int(max(years)),
        (int(min(years)), int(max(years)))
    )
    filtered = df[df["FiscalYear"].between(*year_range)].copy()
else:
    filtered = df.copy()

donors = sorted(filtered["DonorName"].dropna().unique().tolist())
selected_donors = st.sidebar.multiselect("Donors", donors, default=donors)
filtered = filtered[filtered["DonorName"].isin(selected_donors)] if selected_donors else filtered.iloc[0:0]

metrics = make_metrics(filtered)
st.warning(
    "Currency note: PledgeAmt and PaidAmt are displayed as source-reported standardized "
    "amounts. The CSV alone does not establish their reporting currency. Verify the "
    "source data dictionary before describing these totals as USD."
)

cols = st.columns(4)
cols[0].metric("Contribution records", f"{metrics['records']:,}")
cols[1].metric("Total pledges (source units)", money(metrics["pledges"]))
cols[2].metric("Total payments (source units)", money(metrics["payments"]))
cols[3].metric(
    "Payment / pledge ratio",
    "—" if pd.isna(metrics["payment_ratio"]) else f"{metrics['payment_ratio']:.1%}"
)

cols = st.columns(4)
cols[0].metric("Unique donors", f"{metrics['donors']:,}")
cols[1].metric("Pledge less payment", money(metrics["difference"]))
cols[2].metric(
    "Top-five donor share",
    "—" if pd.isna(metrics["top5_share"]) else f"{metrics['top5_share']:.1%}"
)
cols[3].metric("Zero-payment records", f"{metrics['zero_payment_rows']:,}")

tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Executive Summary", "Trends", "Donors & concentration", "Currency", "Data quality", "Explore & download"]
)

with tab0:
    st.subheader("Somalia humanitarian financing at a glance")
    st.markdown(
        "This dashboard analyses recorded contributions to the Somalia Country-Based "
        "Pooled Fund (CBPF), using the OCHA dataset published through the Humanitarian "
        "Data Exchange (HDX). The summary below updates automatically with the selected "
        "fiscal years and donors."
    )

    summary_cols = st.columns(4)
    summary_cols[0].metric("Contribution records", f"{metrics['records']:,}")
    summary_cols[1].metric("Recorded pledges", money(metrics["pledges"]), help="Source-reported standardized amount units; currency not confirmed.")
    summary_cols[2].metric("Recorded payments", money(metrics["payments"]), help="Source-reported standardized amount units; currency not confirmed.")
    summary_cols[3].metric(
        "Payment / pledge ratio",
        "—" if pd.isna(metrics["payment_ratio"]) else f"{metrics['payment_ratio']:.1%}",
        help="Total recorded payments divided by total recorded pledges for the filtered records."
    )

    donor_view = (
        filtered.groupby("DonorName", dropna=False)["PaidAmt"]
        .sum().sort_values(ascending=False)
    )
    leading_donor = donor_view.index[0] if len(donor_view) and donor_view.iloc[0] > 0 else None
    leading_share = float(donor_view.iloc[0] / donor_view.sum()) if leading_donor is not None and donor_view.sum() else np.nan

    st.markdown("#### Key findings")
    finding_cols = st.columns(2)
    with finding_cols[0]:
        st.metric(
            "Top-five donor share of payments",
            "—" if pd.isna(metrics["top5_share"]) else f"{metrics['top5_share']:.1%}",
            help="Share of total recorded payments accounted for by the five largest donors."
        )
        if leading_donor is not None:
            st.write(f"**Largest recorded payment contributor:** {leading_donor} "
                     f"({leading_share:.1%} of payments).")
        else:
            st.write("No positive recorded payments are available for the current selection.")
    with finding_cols[1]:
        st.metric("Pledge less payment", money(metrics["difference"]))
        st.metric("Records with zero recorded payments", f"{metrics['zero_payment_rows']:,}")

    st.markdown("#### What the figures suggest")
    if pd.notna(metrics["payment_ratio"]):
        if metrics["payment_ratio"] >= 0.95:
            st.write("Recorded payments are high relative to recorded pledges in the selected data. "
                     "The remaining pledge-payment difference should be examined at contribution level.")
        elif metrics["payment_ratio"] >= 0.75:
            st.write("Recorded payments are below recorded pledges in the selected data. "
                     "Reviewing outstanding balances by donor and contribution may help identify where differences are concentrated.")
        else:
            st.write("The recorded payment-to-pledge ratio is comparatively low in the selected data. "
                     "Further review by donor, fiscal year and contribution record is recommended.")
    else:
        st.write("A payment-to-pledge ratio cannot be calculated for the current selection.")

    if pd.notna(metrics["top5_share"]) and metrics["top5_share"] >= 0.60:
        st.write("Payments are concentrated among a small group of major donors. "
                 "This makes donor diversification an important consideration when interpreting financing resilience.")
    elif pd.notna(metrics["top5_share"]):
        st.write("The five largest donors account for a smaller share of recorded payments in this selection; "
                 "review the donor breakdown for the full distribution.")

    st.markdown("#### Interpretation and limitations")
    st.info(
        "Currency: PledgeAmt and PaidAmt are shown in source-reported standardized amount units. "
        "The CSV alone does not establish the reporting currency, so these totals must not be labelled USD "
        "without confirmation from the source data dictionary.\n\n"
        "Scope: This dataset records contributions. It does not by itself measure fund allocations, "
        "project expenditures, implementation performance, humanitarian outputs or beneficiary outcomes.\n\n"
        "Coverage: Future fiscal-year records and unpaid balances should be interpreted in context; "
        "a pledge without a recorded payment is not automatically overdue."
    )
    st.caption("Source: OCHA, Somalia – CBPF Allocations and Contributions, Humanitarian Data Exchange (HDX).")

with tab1:
    st.subheader("Annual pledges and payments")
    annual = filtered.groupby("FiscalYear", dropna=True)[["PledgeAmt", "PaidAmt"]].sum().reset_index()
    if not annual.empty:
        long = annual.melt("FiscalYear", var_name="Measure", value_name="Amount")
        fig = px.bar(
            long, x="FiscalYear", y="Amount", color="Measure", barmode="group",
            title="Annual totals (source-reported amount units)"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No records match the selected filters.")

    st.subheader("Contribution timing")
    if "PledgeDate" in filtered and filtered["PledgeDate"].notna().any():
        timed = filtered.dropna(subset=["PledgeDate"]).copy()
        timed["PledgeMonth"] = timed["PledgeDate"].dt.to_period("M").astype(str)
        monthly = timed.groupby("PledgeMonth")["PledgeAmt"].sum().reset_index()
        fig = px.line(monthly, x="PledgeMonth", y="PledgeAmt", markers=True,
                      title="Pledges by pledge month")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No usable pledge dates are available.")

with tab2:
    st.subheader("Largest donors by payments")
    record_count = ("ContributionCode", "count") if "ContributionCode" in filtered else ("PaidAmt", "count")
    donor_summary = filtered.groupby("DonorName", dropna=False).agg(
        Pledges=("PledgeAmt", "sum"), Payments=("PaidAmt", "sum"),
        Records=record_count
    ).reset_index().sort_values("Payments", ascending=False)

    if not donor_summary.empty:
        fig = px.bar(
            donor_summary.head(15).sort_values("Payments"),
            x="Payments", y="DonorName", orientation="h",
            title="Top 15 donors by recorded payments"
        )
        st.plotly_chart(fig, use_container_width=True)
        if donor_summary["Payments"].sum() > 0:
            donor_summary["PaymentShare"] = donor_summary["Payments"] / donor_summary["Payments"].sum()
            ordered = donor_summary.sort_values("Payments", ascending=False)
            donor_summary["CumulativeShare"] = ordered["PaymentShare"].cumsum().reindex(donor_summary.index)
            st.metric("Top-five donor payment share", f"{top_share(donor_summary.set_index('DonorName')['Payments'], 5):.1%}")
            st.dataframe(donor_summary.sort_values("Payments", ascending=False),
                         use_container_width=True, hide_index=True)
    st.caption("HHI is a descriptive concentration measure based on donors' shares of recorded payments.")

with tab3:
    st.subheader("Local-currency composition")
    currency_col, amount_col = "PledgeAmtLocalCurrency", "PledgeAmtLocal"
    if currency_col in filtered and amount_col in filtered:
        currency_summary = (
            filtered.dropna(subset=[currency_col])
            .groupby(currency_col)[amount_col].sum().reset_index()
            .sort_values(amount_col, ascending=False)
        )
        fig = px.bar(
            currency_summary, x=currency_col, y=amount_col,
            title="Pledge amounts in original local currencies (not comparable across currencies)"
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(currency_summary, use_container_width=True, hide_index=True)
    else:
        st.info("Local-currency fields are not present in this file.")
    st.caption("Do not sum different local currencies. Apply documented conversion rules for cross-currency comparisons.")

with tab4:
    st.subheader("Data-quality checks")
    checks = [
        ("Duplicate contribution codes", int(filtered["ContributionCode"].duplicated().sum()) if "ContributionCode" in filtered else 0),
        ("Missing donor names", int(filtered["DonorName"].isna().sum())),
        ("Missing fiscal years", int(filtered["FiscalYear"].isna().sum())),
        ("Missing pledge amounts", int(filtered["PledgeAmt"].isna().sum())),
        ("Missing payment amounts", int(filtered["PaidAmt"].isna().sum())),
        ("Pledge amounts below zero", int((filtered["PledgeAmt"] < 0).sum())),
        ("Payment amounts below zero", int((filtered["PaidAmt"] < 0).sum())),
        ("Payments greater than pledges", int((filtered["PaidAmt"] > filtered["PledgeAmt"]).sum())),
        ("Placeholder / missing pledge dates", int(filtered["PledgeDate"].isna().sum()) if "PledgeDate" in filtered else 0),
    ]
    st.dataframe(pd.DataFrame(checks, columns=["Check", "Count"]),
                 use_container_width=True, hide_index=True)
    st.write("Records by fiscal year")
    st.dataframe(
        filtered.groupby("FiscalYear", dropna=False).size().rename("Records").reset_index(),
        use_container_width=True, hide_index=True
    )
    st.caption("Payments greater than pledges are flagged for review, not automatically treated as errors.")

with tab5:
    st.subheader("Filtered contribution records")
    st.dataframe(filtered, use_container_width=True, hide_index=True)
    st.download_button(
        "Download filtered and cleaned CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        "som_cbpf_cleaned_filtered.csv", "text/csv"
    )
    st.download_button(
        "Download KPI summary CSV",
        pd.DataFrame([metrics]).to_csv(index=False).encode("utf-8"),
        "som_cbpf_kpi_summary.csv", "text/csv"
    )
    annual_export = filtered.groupby("FiscalYear")[["PledgeAmt", "PaidAmt"]].sum().reset_index()
    st.download_button(
        "Download annual summary CSV",
        annual_export.to_csv(index=False).encode("utf-8"),
        "som_cbpf_annual_summary.csv", "text/csv"
    )

st.divider()
st.caption(
    "Analytical use only. Contribution records do not show allocations, expenditures, "
    "project outputs or beneficiary outcomes."
)
