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
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

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


def build_pdf_report(metrics: dict, donor_summary: pd.DataFrame, annual_summary: pd.DataFrame,
                     year_range_label: str, donor_count: int) -> bytes:
    """Create a filtered PDF report from the currently selected contribution records."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                            topMargin=17*mm, bottomMargin=17*mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Somalia Humanitarian Financing Intelligence", styles["Title"]),
        Paragraph("CBPF Contributions — Analytical Report", styles["Heading2"]),
        Paragraph(f"Selected fiscal years: {year_range_label} | Donors selected: {donor_count}", styles["Normal"]),
        Spacer(1, 8),
        Paragraph("Executive summary", styles["Heading1"]),
        Paragraph(
            f"The selected data contain {metrics['records']:,} contribution records from "
            f"{metrics['donors']:,} donors. Recorded pledges total {money(metrics['pledges'])} "
            f"source units and recorded payments total {money(metrics['payments'])} source units. "
            f"The payment-to-pledge ratio is "
            f"{'not available' if pd.isna(metrics['payment_ratio']) else f\"{metrics['payment_ratio']:.1%}\"}.",
            styles["BodyText"]
        ),
        Spacer(1, 6),
    ]
    kpi_rows = [
        ["Indicator", "Value"],
        ["Pledge less payment (source units)", money(metrics["difference"])],
        ["Top-one donor share of payments", "—" if pd.isna(metrics.get("top1_share")) else f"{metrics['top1_share']:.1%}"],
        ["Top-three donor share of payments", "—" if pd.isna(metrics.get("top3_share")) else f"{metrics['top3_share']:.1%}"],
        ["Top-five donor share of payments", "—" if pd.isna(metrics.get("top5_share")) else f"{metrics['top5_share']:.1%}"],
        ["Normalized HHI (0–1)", "—" if pd.isna(metrics.get("hhi")) else f"{metrics['hhi']:.4f}"],
        ["Records with zero recorded payments", f"{metrics['zero_payment_rows']:,}"],
    ]
    story += [Table(kpi_rows, colWidths=[105*mm, 55*mm]), Spacer(1, 10),
              Paragraph("Donor dependency analysis", styles["Heading1"])]
    if not donor_summary.empty:
        donor_rows = [["Donor", "Pledges", "Payments", "Payment share"]]
        for _, row in donor_summary.head(10).iterrows():
            donor_rows.append([str(row["DonorLabel"]), money(row["Pledges"]),
                               money(row["Payments"]), f"{row['PaymentShare']:.1%}" if pd.notna(row.get("PaymentShare")) else "—"])
        story.append(Table(donor_rows, repeatRows=1, colWidths=[55*mm, 38*mm, 38*mm, 29*mm]))
    else:
        story.append(Paragraph("No donor payment records are available for this selection.", styles["BodyText"]))
    story += [Spacer(1, 10), Paragraph("Year-on-year contribution analysis", styles["Heading1"])]
    if not annual_summary.empty:
        annual_rows = [["Fiscal year", "Pledges", "YoY change", "Payments", "YoY change"]]
        for _, row in annual_summary.iterrows():
            annual_rows.append([
                str(int(row["FiscalYear"])),
                money(row["PledgeAmt"]),
                "—" if pd.isna(row["PledgeYoYPct"]) else f"{row['PledgeYoYPct']:+.1f}%",
                money(row["PaidAmt"]),
                "—" if pd.isna(row["PaidYoYPct"]) else f"{row['PaidYoYPct']:+.1f}%"
            ])
        story.append(Table(annual_rows, repeatRows=1, colWidths=[22*mm, 36*mm, 28*mm, 36*mm, 28*mm]))
    story += [
        Spacer(1, 10), Paragraph("Methodology and limitations", styles["Heading1"]),
        Paragraph(
            "Donor shares are calculated as each donor's recorded payments divided by total recorded "
            "payments in the selected records. Top-one, top-three and top-five shares sum the largest "
            "donor shares. The normalized Herfindahl–Hirschman Index (HHI) is the sum of squared donor "
            "payment shares and ranges from 0 to 1. Year-on-year growth compares a fiscal year only with "
            "the immediately preceding fiscal year; it is not calculated across missing years.",
            styles["BodyText"]),
        Spacer(1, 5),
        Paragraph(
            "Currency: PledgeAmt and PaidAmt are source-standardized fields. The CSV alone does not "
            "establish their reporting currency; values are therefore labelled source units, not USD. "
            "The dataset records contributions and does not measure allocations, expenditures, project "
            "outputs or beneficiary outcomes. Current-year and future-year records may be incomplete; "
            "a pledge without a recorded payment is not automatically overdue.",
            styles["BodyText"]),
        Spacer(1, 8),
        Paragraph("Source: OCHA, Somalia – CBPF Allocations and Contributions, Humanitarian Data Exchange (HDX).",
                  styles["Italic"])
    ]
    table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C8D0D9")),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("LEADING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6F9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    for item in story:
        if isinstance(item, Table):
            item.setStyle(table_style)
    doc.build(story)
    return buffer.getvalue()


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

# Donor-level payment concentration; unknown donor names remain visible as a separate group.
donor_summary = filtered.groupby("DonorName", dropna=False).agg(
    Pledges=("PledgeAmt", "sum"), Payments=("PaidAmt", "sum"),
    Records=("PaidAmt", "count")
).reset_index()
donor_summary["DonorLabel"] = donor_summary["DonorName"].fillna("Unspecified donor")
total_donor_payments = donor_summary["Payments"].sum()
donor_summary["PaymentShare"] = (
    donor_summary["Payments"] / total_donor_payments if total_donor_payments > 0 else np.nan
)
donor_summary = donor_summary.sort_values("Payments", ascending=False, na_position="last").reset_index(drop=True)
positive_shares = donor_summary.loc[donor_summary["PaymentShare"] > 0, "PaymentShare"].dropna()
metrics["top1_share"] = float(positive_shares.head(1).sum()) if len(positive_shares) else np.nan
metrics["top3_share"] = float(positive_shares.head(3).sum()) if len(positive_shares) else np.nan
metrics["hhi"] = float((positive_shares ** 2).sum()) if len(positive_shares) else np.nan

annual = (
    filtered.dropna(subset=["FiscalYear"])
    .groupby("FiscalYear")[["PledgeAmt", "PaidAmt"]].sum()
    .reset_index().sort_values("FiscalYear")
)
annual["PreviousFiscalYear"] = annual["FiscalYear"] - 1
previous = annual[["FiscalYear", "PledgeAmt", "PaidAmt"]].copy()
previous["FiscalYear"] = previous["FiscalYear"] + 1
previous = previous.rename(columns={"PledgeAmt": "PreviousPledges", "PaidAmt": "PreviousPayments"})
annual = annual.merge(previous, on="FiscalYear", how="left")
annual["PledgeYoYChange"] = annual["PledgeAmt"] - annual["PreviousPledges"]
annual["PaidYoYChange"] = annual["PaidAmt"] - annual["PreviousPayments"]
annual["PledgeYoYPct"] = np.where(
    annual["PreviousPledges"] > 0,
    annual["PledgeYoYChange"] / annual["PreviousPledges"] * 100, np.nan
)
annual["PaidYoYPct"] = np.where(
    annual["PreviousPayments"] > 0,
    annual["PaidYoYChange"] / annual["PreviousPayments"] * 100, np.nan
)
annual["YearStatus"] = np.where(
    annual["FiscalYear"] > pd.Timestamp.now().year, "Future fiscal year",
    np.where(annual["FiscalYear"] == pd.Timestamp.now().year, "Current calendar year; may be incomplete",
             "Historical fiscal year; completeness not independently verified")
)

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
    if not annual.empty:
        long = annual.melt("FiscalYear", value_vars=["PledgeAmt", "PaidAmt"],
                           var_name="Measure", value_name="Amount")
        fig = px.bar(
            long, x="FiscalYear", y="Amount", color="Measure", barmode="group",
            title="Annual totals (source-reported amount units)"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No records match the selected filters.")

    st.subheader("Year-on-year changes")
    st.caption("Growth is calculated against the immediately preceding fiscal year only. A missing prior year or a zero prior-year value produces no growth rate.")
    if not annual.empty:
        yoy_cols = st.columns(2)
        latest_valid = annual.dropna(subset=["PledgeYoYPct", "PaidYoYPct"], how="all")
        if not latest_valid.empty:
            latest = latest_valid.iloc[-1]
            yoy_cols[0].metric("Latest annual pledge change",
                               "—" if pd.isna(latest["PledgeYoYPct"]) else f"{latest['PledgeYoYPct']:+.1f}%",
                               help=f"Fiscal year {int(latest['FiscalYear'])} compared with fiscal year {int(latest['FiscalYear'])-1}.")
            yoy_cols[1].metric("Latest annual payment change",
                               "—" if pd.isna(latest["PaidYoYPct"]) else f"{latest['PaidYoYPct']:+.1f}%",
                               help=f"Fiscal year {int(latest['FiscalYear'])} compared with fiscal year {int(latest['FiscalYear'])-1}.")
        yoy_long = annual.melt("FiscalYear", value_vars=["PledgeYoYPct", "PaidYoYPct"],
                               var_name="Measure", value_name="YoY growth (%)")
        yoy_long["Measure"] = yoy_long["Measure"].map({
            "PledgeYoYPct": "Pledges", "PaidYoYPct": "Payments"
        })
        fig = px.line(yoy_long, x="FiscalYear", y="YoY growth (%)", color="Measure",
                      markers=True, title="Year-on-year growth (%)")
        fig.add_hline(y=0, line_dash="dot", line_color="gray")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            annual[["FiscalYear", "PledgeAmt", "PledgeYoYChange", "PledgeYoYPct",
                    "PaidAmt", "PaidYoYChange", "PaidYoYPct", "YearStatus"]],
            use_container_width=True, hide_index=True
        )
        st.caption("Fiscal-year status is a cautious calendar-year flag, not confirmation that a reporting period is complete. Future-year records are not interpreted as overdue.")
    st.download_button(
        "Download year-on-year analysis CSV",
        annual.to_csv(index=False).encode("utf-8"),
        "som_cbpf_year_on_year_analysis.csv", "text/csv"
    )

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
    st.subheader("Donor dependency and payment concentration")
    dep_cols = st.columns(4)
    dep_cols[0].metric("Top-one donor share", "—" if pd.isna(metrics["top1_share"]) else f"{metrics['top1_share']:.1%}")
    dep_cols[1].metric("Top-three donor share", "—" if pd.isna(metrics["top3_share"]) else f"{metrics['top3_share']:.1%}")
    dep_cols[2].metric("Top-five donor share", "—" if pd.isna(metrics["top5_share"]) else f"{metrics['top5_share']:.1%}")
    dep_cols[3].metric("Normalized HHI", "—" if pd.isna(metrics["hhi"]) else f"{metrics['hhi']:.4f}",
                       help="Sum of squared donor payment shares. Ranges from near 0 to 1; higher values indicate greater concentration.")

    if not donor_summary.empty:
        plot_donors = donor_summary.head(15).sort_values("Payments").copy()
        fig = px.bar(
            plot_donors, x="Payments", y="DonorLabel", orientation="h",
            title="Top 15 donors by recorded payments",
            hover_data={"PaymentShare": ":.1%", "Pledges": ":,.2f"}
        )
        st.plotly_chart(fig, use_container_width=True)
        donor_summary["CumulativeShare"] = donor_summary["PaymentShare"].fillna(0).cumsum()
        st.dataframe(
            donor_summary[["DonorLabel", "Pledges", "Payments", "PaymentShare", "CumulativeShare", "Records"]],
            use_container_width=True, hide_index=True,
            column_config={
                "PaymentShare": st.column_config.NumberColumn("Payment share", format="%.1f%%"),
                "CumulativeShare": st.column_config.NumberColumn("Cumulative share", format="%.1f%%")
            }
        )
    st.caption("Donor dependency is measured using each donor's share of recorded payments in the selected data. HHI is the normalized sum of squared shares (0–1); it is descriptive, not a causal or credit-risk measure.")
    st.caption("Unknown donor names are retained as an 'Unspecified donor' category rather than silently excluded.")

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
    st.subheader("Downloadable analytical report")
    year_label = f"{int(year_range[0])}–{int(year_range[1])}" if years else "All available years"
    pdf_bytes = build_pdf_report(metrics, donor_summary, annual, year_label, len(selected_donors))
    st.download_button(
        "Download filtered analytical report (PDF)",
        data=pdf_bytes,
        file_name="somalia_cbpf_financial_analytics_report.pdf",
        mime="application/pdf"
    )
    st.caption("The PDF uses the current fiscal-year and donor filters. Amounts are labelled in source units because the standardized fields' currency is not confirmed.")

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
    "Analytical use only. This contribution dataset does not show allocations, expenditures, "
    "project outputs or beneficiary outcomes. Allocation and expenditure analysis requires "
    "additional compatible source datasets."
)
