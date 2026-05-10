"""Streamlit frontend for the Personal Finance Autopilot."""

import io
import json
import time
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ── Configuration ───────────────────────────────────────────────────────────

BACKEND_URL = st.secrets.get("BACKEND_URL", "http://localhost:8000")
MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_SHORT = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

st.set_page_config(
    page_title="Finance Autopilot",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session State ───────────────────────────────────────────────────────────

if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "current_page" not in st.session_state:
    st.session_state.current_page = "Upload"


def _api(method: str, path: str, **kwargs) -> requests.Response:
    """Make an API call to the backend."""
    url = f"{BACKEND_URL}{path}"
    return getattr(requests, method)(url, timeout=60, **kwargs)


def ensure_user():
    """Create or restore user session."""
    if not st.session_state.user_id:
        try:
            resp = _api("post", "/api/users")
            if resp.status_code == 200:
                st.session_state.user_id = resp.json()["user_id"]
        except requests.ConnectionError:
            st.error("Cannot connect to backend. Make sure the API is running.")
            st.stop()


def get_available_months():
    """Fetch months with uploaded data."""
    try:
        resp = _api("get", f"/api/months/{st.session_state.user_id}")
        if resp.status_code == 200:
            return resp.json().get("months", [])
    except Exception:
        pass
    return []


# ── Sidebar Navigation ─────────────────────────────────────────────────────

ensure_user()
available_months = get_available_months()
has_data = len(available_months) > 0

st.sidebar.title("Finance Autopilot")
st.sidebar.markdown("---")

pages = ["Upload"]
if has_data:
    pages.insert(0, "Dashboard")
    pages.append("Transactions")
    pages.append("Subscriptions")
if len(available_months) >= 2:
    pages.insert(2, "Trends")

page = st.sidebar.radio("Navigation", pages, index=0)

st.sidebar.markdown("---")
st.sidebar.caption(f"User: `{st.session_state.user_id[:8]}...`" if st.session_state.user_id else "")


# ── Page: Upload ────────────────────────────────────────────────────────────

def page_upload():
    st.header("Upload Bank Statement")

    col1, col2 = st.columns(2)
    with col1:
        month = st.selectbox("Month", range(1, 13), format_func=lambda x: MONTH_NAMES[x])
    with col2:
        year = st.selectbox("Year", range(2022, 2027), index=2)

    uploaded_file = st.file_uploader(
        "Upload your bank statement",
        type=["pdf", "csv", "xlsx"],
        help="Supported formats: PDF, CSV, Excel",
    )

    # Password field — only shown for PDF uploads, masked input
    pdf_password = ""
    if uploaded_file and uploaded_file.name.lower().endswith(".pdf"):
        pdf_password = st.text_input(
            "PDF Password",
            type="password",
            placeholder="Leave blank if not password-protected",
            help=(
                "Only required if your PDF is password-protected. "
                "The password is used solely to open the file in memory "
                "and is never stored or saved anywhere."
            ),
        )

    st.info(
        "**Well-supported banks:** HDFC, SBI, ICICI, Axis, Kotak, Yes Bank, PNB, "
        "Bank of Baroda, IndusInd, Federal Bank"
    )

    replace = False
    # Check if this month already has data
    existing = any(m["month"] == month and m["year"] == year for m in available_months)
    if existing:
        st.warning(f"You already have data for {MONTH_NAMES[month]} {year}.")
        replace = st.checkbox("Replace existing data")

    if st.button("Process Statement", type="primary", disabled=not uploaded_file):
        if existing and not replace:
            st.error("Statement already exists. Check 'Replace existing data' to overwrite.")
            return

        file_bytes = uploaded_file.read()
        files = {"file": (uploaded_file.name, file_bytes)}
        data = {
            "month": str(month),
            "year": str(year),
            "user_id": st.session_state.user_id,
            "replace": str(replace).lower(),
            "pdf_password": pdf_password,  # empty string if not provided / not a PDF
        }

        try:
            resp = _api("post", "/api/upload", files=files, data=data)
        except requests.ConnectionError:
            st.error("Cannot connect to backend.")
            return

        if resp.status_code == 409:
            st.error(resp.json().get("detail", "Duplicate statement"))
            return
        elif resp.status_code != 200:
            st.error(f"Upload failed: {resp.json().get('detail', resp.text)}")
            return

        job_id = resp.json()["job_id"]

        # Poll for progress
        status_messages = {
            "queued": "Queued for processing...",
            "parsing": "Parsing your statement...",
            "categorising": "Categorising transactions...",
            "detecting_subscriptions": "Detecting subscriptions...",
            "saving": "Saving to database...",
            "calculating": "Calculating your summary...",
            "generating_insights": "Generating insights...",
            "complete": "Done!",
            "failed": "Processing failed.",
        }

        progress_bar = st.progress(0)
        status_text = st.empty()

        while True:
            try:
                job_resp = _api("get", f"/api/jobs/{job_id}")
                job_data = job_resp.json()
            except Exception:
                time.sleep(2)
                continue

            status = job_data.get("status", "queued")
            progress = job_data.get("progress", 0)

            progress_bar.progress(min(progress, 100))
            status_text.markdown(f"**{status_messages.get(status, status)}**")

            if status == "complete":
                st.success(f"Successfully processed {MONTH_NAMES[month]} {year}!")
                st.balloons()
                time.sleep(1)
                st.rerun()
                break
            elif status == "failed":
                st.error(f"Error: {job_data.get('error', 'Unknown error')}")
                break

            time.sleep(2)

    if not has_data:
        st.markdown("---")
        st.markdown(
            "### Getting Started\n"
            "1. Select the **month** and **year** for your bank statement\n"
            "2. Upload your **PDF** or **CSV** bank statement\n"
            "3. We'll automatically parse, categorise, and analyse your transactions\n"
            "4. View your **dashboard** with spending insights and trends"
        )


# ── Page: Dashboard ─────────────────────────────────────────────────────────

def page_dashboard():
    st.header("Financial Dashboard")

    # Month selector
    month_options = [f"{MONTH_NAMES[m['month']]} {m['year']}" for m in available_months]
    if not month_options:
        st.info("No data yet. Upload a bank statement to get started.")
        return

    selected_label = st.selectbox("Select Month", month_options)
    selected_idx = month_options.index(selected_label)
    sel_month = available_months[selected_idx]["month"]
    sel_year = available_months[selected_idx]["year"]

    # Fetch summary
    try:
        resp = _api("get", f"/api/summary/{st.session_state.user_id}/{sel_year}/{sel_month}")
        if resp.status_code != 200:
            st.error("Could not load summary.")
            return
        summary = resp.json()
    except Exception as e:
        st.error(f"Error fetching summary: {e}")
        return

    # Top metrics row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Income", f"₹{summary['total_income']:,.0f}")
    with c2:
        st.metric("Expenses", f"₹{summary['total_expenses']:,.0f}")
    with c3:
        savings_delta = f"{summary['savings_rate']}%"
        st.metric("Savings", f"₹{summary['net_savings']:,.0f}", delta=savings_delta)
    with c4:
        hs = summary["health_score"]
        color = "🔴" if hs < 50 else "🟠" if hs < 75 else "🟢"
        st.metric("Health Score", f"{color} {hs}/100")

    # Insights
    st.markdown("---")
    st.subheader("AI Insights")
    st.info(summary.get("llm_insights", "No insights available."))

    # Charts row
    st.markdown("---")
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Spending by Category")
        cat_data = summary.get("category_breakdown", {})
        if isinstance(cat_data, str):
            cat_data = json.loads(cat_data)
        if cat_data:
            fig = px.pie(
                values=list(cat_data.values()),
                names=list(cat_data.keys()),
                hole=0.4,
            )
            fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.write("No category data available.")

    with col_right:
        st.subheader("Category Comparison")
        # Try to get previous month data for comparison
        if len(available_months) >= 2:
            try:
                comp_resp = _api("get", f"/api/comparison/{st.session_state.user_id}?months=2")
                if comp_resp.status_code == 200:
                    comp_data = comp_resp.json()
                    summaries = comp_data.get("summaries", [])
                    if len(summaries) >= 2:
                        prev = summaries[-2]["category_breakdown"]
                        curr = summaries[-1]["category_breakdown"]
                        if isinstance(prev, str):
                            prev = json.loads(prev)
                        if isinstance(curr, str):
                            curr = json.loads(curr)
                        all_cats = sorted(set(list(prev.keys()) + list(curr.keys())))
                        fig = go.Figure(data=[
                            go.Bar(
                                name=f"{MONTH_SHORT[summaries[-2]['month']]} {summaries[-2]['year']}",
                                x=all_cats,
                                y=[prev.get(c, 0) for c in all_cats],
                            ),
                            go.Bar(
                                name=f"{MONTH_SHORT[summaries[-1]['month']]} {summaries[-1]['year']}",
                                x=all_cats,
                                y=[curr.get(c, 0) for c in all_cats],
                            ),
                        ])
                        fig.update_layout(
                            barmode="group",
                            margin=dict(t=20, b=20, l=20, r=20),
                            height=400,
                            xaxis_tickangle=-45,
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.write("Upload another month to see comparisons.")
                else:
                    st.write("Upload another month to see comparisons.")
            except Exception:
                st.write("Could not load comparison data.")
        else:
            st.write("Upload another month to see comparisons.")

    # Subscriptions section
    sub_list = summary.get("subscription_list", {})
    if isinstance(sub_list, str):
        sub_list = json.loads(sub_list)
    if sub_list:
        st.markdown("---")
        st.subheader("Subscriptions This Month")
        sub_df = pd.DataFrame([
            {"Merchant": k, "Monthly Cost": f"₹{v:,.0f}", "Annual Cost (est.)": f"₹{v * 12:,.0f}"}
            for k, v in sub_list.items()
        ])
        st.dataframe(sub_df, use_container_width=True, hide_index=True)

    # Unusual transactions
    unusual = summary.get("unusual_transactions", [])
    if isinstance(unusual, str):
        unusual = json.loads(unusual)
    if unusual:
        st.markdown("---")
        st.subheader("Unusual Transactions")
        with st.expander(f"{len(unusual)} unusual transaction(s) detected", expanded=False):
            for u in unusual:
                st.markdown(
                    f"- **{u['merchant']}**: ₹{u['amount']:,.0f} "
                    f"({u['times_above_avg']}x the category average of ₹{u['category_avg']:,.0f} "
                    f"in {u['category']})"
                )


# ── Page: Trends ────────────────────────────────────────────────────────────

def page_trends():
    st.header("Financial Trends")

    try:
        resp = _api("get", f"/api/comparison/{st.session_state.user_id}?months=12")
        if resp.status_code != 200:
            st.warning("Need at least 2 months of data for trends.")
            return
        data = resp.json()
    except Exception as e:
        st.error(f"Error: {e}")
        return

    summaries = data.get("summaries", [])
    context = data.get("comparison_context", {})

    if len(summaries) < 2:
        st.info("Upload at least 2 months of statements to see trends.")
        return

    periods = [f"{MONTH_SHORT[s['month']]} {s['year']}" for s in summaries]

    # Summary stats at top
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Avg Monthly Savings", f"₹{context.get('avg_monthly_savings', 0):,.0f}")
    with c2:
        st.metric("Best Month", context.get("best_savings_month", "N/A"))
    with c3:
        st.metric("Worst Month", context.get("worst_savings_month", "N/A"))
    with c4:
        st.metric("Savings Trend", context.get("savings_trend", "N/A"))

    st.markdown("---")

    # Savings over time
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Savings Over Time")
        savings_data = [s["net_savings"] for s in summaries]
        fig = px.line(x=periods, y=savings_data, markers=True, labels={"x": "Month", "y": "Net Savings (₹)"})
        fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=350)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Health Score Over Time")
        hs_data = [s["health_score"] for s in summaries]
        fig = px.line(x=periods, y=hs_data, markers=True, labels={"x": "Month", "y": "Health Score"})
        fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=350, yaxis_range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)

    # Stacked bar: category breakdown across months
    st.markdown("---")
    st.subheader("Category Breakdown Across Months")

    all_cats_set = set()
    for s in summaries:
        cats = s["category_breakdown"]
        if isinstance(cats, str):
            cats = json.loads(cats)
        all_cats_set.update(cats.keys())

    stacked_data = []
    for s in summaries:
        cats = s["category_breakdown"]
        if isinstance(cats, str):
            cats = json.loads(cats)
        period = f"{MONTH_SHORT[s['month']]} {s['year']}"
        for cat in all_cats_set:
            stacked_data.append({"Month": period, "Category": cat, "Amount": cats.get(cat, 0)})

    if stacked_data:
        sdf = pd.DataFrame(stacked_data)
        fig = px.bar(sdf, x="Month", y="Amount", color="Category", barmode="stack")
        fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=450)
        st.plotly_chart(fig, use_container_width=True)

    # Category trend table
    st.markdown("---")
    st.subheader("Category Trends")
    cat_trends = context.get("category_trends", {})
    if cat_trends:
        trend_rows = []
        for cat, info in cat_trends.items():
            amounts = info.get("amounts", [])
            trend = info.get("trend", "N/A")
            arrow = "→"
            if "improving" in trend or "up" in trend.lower() if isinstance(trend, str) else False:
                arrow = "↑"
            elif "declining" in trend or "down" in trend.lower() if isinstance(trend, str) else False:
                arrow = "↓"

            # Compute % change vs 3-month avg
            if len(amounts) >= 2:
                avg_3m = sum(amounts[-3:]) / min(len(amounts), 3)
                latest = amounts[-1]
                pct_change = ((latest - avg_3m) / avg_3m * 100) if avg_3m > 0 else 0
                trend_rows.append({
                    "Category": cat,
                    "Trend": f"{arrow} {trend}",
                    "Latest": f"₹{latest:,.0f}",
                    "3M Avg": f"₹{avg_3m:,.0f}",
                    "Change": f"{pct_change:+.1f}%",
                })

        if trend_rows:
            st.dataframe(pd.DataFrame(trend_rows), use_container_width=True, hide_index=True)


# ── Page: Transactions ──────────────────────────────────────────────────────

def page_transactions():
    st.header("Transactions")

    month_options = [f"{MONTH_NAMES[m['month']]} {m['year']}" for m in available_months]
    if not month_options:
        st.info("No data available.")
        return

    selected_label = st.selectbox("Select Month", month_options, key="txn_month")
    selected_idx = month_options.index(selected_label)
    sel_month = available_months[selected_idx]["month"]
    sel_year = available_months[selected_idx]["year"]

    # Filters
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        categories = [
            "All", "Food & Dining", "Groceries", "Transport", "Shopping",
            "Entertainment", "Health & Fitness", "Utilities", "Finance & Insurance",
            "Education", "Salary", "Business Income", "ATM Withdrawal",
            "Bank Transfer", "EMI & Loans", "Subscriptions", "Rent",
            "Travel & Holidays", "Other",
        ]
        cat_filter = st.selectbox("Category", categories)
    with fc2:
        review_filter = st.selectbox("Review Status", ["All", "Needs Review", "Reviewed"])
    with fc3:
        type_filter = st.selectbox("Type", ["All", "Debit", "Credit"])

    # Build query params
    params = {"page": 1, "per_page": 100}
    if cat_filter != "All":
        params["category"] = cat_filter
    if review_filter == "Needs Review":
        params["needs_review"] = "true"
    elif review_filter == "Reviewed":
        params["needs_review"] = "false"
    if type_filter != "All":
        params["txn_type"] = type_filter.lower()

    try:
        resp = _api("get", f"/api/transactions/{st.session_state.user_id}/{sel_year}/{sel_month}", params=params)
        if resp.status_code != 200:
            st.error("Could not load transactions.")
            return
        data = resp.json()
    except Exception as e:
        st.error(f"Error: {e}")
        return

    transactions = data.get("transactions", [])
    total = data.get("total", 0)
    st.caption(f"Showing {len(transactions)} of {total} transactions")

    if not transactions:
        st.info("No transactions match your filters.")
        return

    # Build DataFrame for display
    rows = []
    for t in transactions:
        rows.append({
            "Date": t.get("date", "N/A"),
            "Merchant": t["merchant"],
            "Category": t["category"],
            "Amount": t["amount"],
            "Type": t["type"].title(),
            "Confidence": f"{t['confidence']:.0%}",
            "Review": "⚠️" if t["needs_review"] else "✓",
            "id": t["id"],
        })

    df = pd.DataFrame(rows)
    display_df = df.drop(columns=["id"])

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Inline category edit
    st.markdown("---")
    st.subheader("Edit Transaction Category")
    txn_ids = {f"{r['Merchant']} - ₹{r['Amount']} ({r['Date']})": r["id"] for _, r in df.iterrows()}
    selected_txn_label = st.selectbox("Select transaction to edit", list(txn_ids.keys()))
    new_category = st.selectbox("New category", categories[1:], key="edit_cat")

    if st.button("Update Category"):
        txn_id = txn_ids[selected_txn_label]
        try:
            resp = _api("patch", f"/api/transactions/{txn_id}", json={"category": new_category})
            if resp.status_code == 200:
                st.success("Updated!")
                st.rerun()
            else:
                st.error("Failed to update.")
        except Exception as e:
            st.error(f"Error: {e}")

    # Download button
    st.markdown("---")
    csv_data = display_df.to_csv(index=False)
    st.download_button(
        "Download as CSV",
        data=csv_data,
        file_name=f"transactions_{sel_year}_{sel_month}.csv",
        mime="text/csv",
    )


# ── Page: Subscriptions ────────────────────────────────────────────────────

def page_subscriptions():
    st.header("Subscriptions")

    try:
        resp = _api("get", f"/api/subscriptions/{st.session_state.user_id}")
        if resp.status_code != 200:
            st.info("No subscriptions detected yet.")
            return
        data = resp.json()
    except Exception as e:
        st.error(f"Error: {e}")
        return

    subscriptions = data.get("subscriptions", [])
    total_annual = data.get("total_annual_cost", 0)

    if not subscriptions:
        st.info("No recurring subscriptions detected. Upload more months for better detection.")
        return

    st.metric("Total Annual Subscription Spend", f"₹{total_annual:,.0f}")
    st.markdown("---")

    # Subscription cards
    cols = st.columns(min(len(subscriptions), 3))
    for i, sub in enumerate(subscriptions):
        with cols[i % 3]:
            st.markdown(f"### {sub['merchant']}")
            st.write(f"**Frequency:** {sub['frequency']}")
            st.write(f"**Monthly:** ₹{sub['amount']:,.0f}")
            st.write(f"**Annual:** ₹{sub['annual_cost']:,.0f}")
            if sub.get("last_charged"):
                st.write(f"**Last charged:** {sub['last_charged']}")
            st.markdown("---")

    # Potentially cancelled subscriptions
    st.subheader("Subscriptions You Might Want to Cancel")
    today = date.today()
    stale = []
    for sub in subscriptions:
        if sub.get("last_charged"):
            try:
                last = date.fromisoformat(sub["last_charged"])
                days_ago = (today - last).days
                if days_ago > 60:
                    stale.append({**sub, "days_since": days_ago})
            except (ValueError, TypeError):
                pass

    if stale:
        for s in stale:
            st.warning(
                f"**{s['merchant']}** — last charged {s['days_since']} days ago "
                f"(₹{s['annual_cost']:,.0f}/year). Still using it?"
            )
    else:
        st.success("All your subscriptions appear active!")


# ── Page Router ─────────────────────────────────────────────────────────────

if page == "Upload":
    page_upload()
elif page == "Dashboard":
    page_dashboard()
elif page == "Trends":
    page_trends()
elif page == "Transactions":
    page_transactions()
elif page == "Subscriptions":
    page_subscriptions()
