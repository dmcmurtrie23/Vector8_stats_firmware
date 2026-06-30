import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, date

st.set_page_config(page_title="Vector8 Tags Reporter", page_icon="📡", layout="wide")

st.title("📡 Vector8 Tags Reporter")

# =========================================================
# FILE UPLOADS
# =========================================================
col_a, col_b, col_c = st.columns(3)
with col_a:
    tags_file = st.file_uploader("📋 Tags JSON (daily snapshot)", type=["json"], key="tags")
with col_b:
    uploads_file = st.file_uploader("📤 Uploads JSON (weekly activity)", type=["json"], key="uploads")
with col_c:
    telemetry_file = st.file_uploader("📶 Telemetry JSON (fleet snapshot)", type=["json"], key="telemetry")

if not tags_file and not uploads_file and not telemetry_file:
    st.info("Upload one or more JSON files to get started.")
    st.stop()

# =========================================================
# PARSE TAGS FILE
# =========================================================
df = pd.DataFrame()
all_customers = []
accounts = []
generated_at = "N/A"

if tags_file:
    tags_data = json.load(tags_file)
    generated_at = tags_data.get("generated_at", "Unknown")
    accounts = tags_data.get("accounts", [])

    rows = []
    for account in accounts:
        customer_name = account.get("customer_name") or f"(No Name) ID: {account.get('customer_id', 'N/A')}"
        customer_id = account.get("customer_id")
        region = account.get("region", "Unknown")

        for tag in account.get("tags", []):
            telemetry = tag.get("latest_telemetry") or {}
            rows.append({
                "customer_name": customer_name,
                "customer_id": customer_id,
                "region": region,
                "serial": tag.get("serial"),
                "model": tag.get("model"),
                "generation": tag.get("generation"),
                "tag_created_at": tag.get("created_at"),
                "tag_updated_at": tag.get("updated_at"),
                "fw_version": telemetry.get("fw_version"),
                "telemetry_updated_at": telemetry.get("updated_at"),
            })

    df = pd.DataFrame(rows)
    for col in ["tag_updated_at", "tag_created_at", "telemetry_updated_at"]:
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    all_customers = sorted(df["customer_name"].unique())

# =========================================================
# PARSE UPLOADS FILE
# =========================================================
udf = pd.DataFrame()
upload_customer_ids = []

def safe_int(val, default=0):
    try:
        return int(float(str(val))) if val not in (None, "", "null") else default
    except Exception:
        return default

if uploads_file:
    uploads_data = json.loads(uploads_file.getvalue())
    urecords = uploads_data["data"]
    urows = []
    for r in urecords:
        urows.append({
            "customer_id": str(r.get("customer_id", "")),
            "customer_name": r.get("customer_name") or "",
            "region": r.get("region", "Unknown"),
            "serial": r.get("serial"),
            "filename": r.get("filename", ""),
            "file_size": safe_int(r.get("file_size"), 0),
            "upload_rate": safe_int(r.get("upload_rate"), 0),
            "download_rate": safe_int(r.get("download_rate"), 0),
            "time_to_cloud_ms": safe_int(r.get("time_to_cloud"), 0),
            "session_duration_ms": safe_int(r.get("session_duration"), 0),
            "session_index": r.get("session_index"),
            "error": r.get("upload_error_message") or "",
            "created_at_ms": safe_int(r.get("created_at"), 0),
            "sync_time_ms": safe_int(r.get("sync_time"), 0),
        })

    udf = pd.DataFrame(urows)

    # created_at and sync_time may arrive as strings or ints — normalise safely
    udf["created_at_ms"] = pd.to_numeric(udf["created_at_ms"], errors="coerce").fillna(0).astype("int64")
    udf["sync_time_ms"] = pd.to_numeric(udf["sync_time_ms"], errors="coerce").fillna(0).astype("int64")
    udf["created_at"] = pd.to_datetime(udf["created_at_ms"], unit="ms", utc=True, errors="coerce")
    udf["sync_time"] = pd.to_datetime(udf["sync_time_ms"], unit="ms", utc=True, errors="coerce")
    udf["date"] = udf["created_at"].dt.date
    udf["success"] = udf["error"] == ""
    udf["file_size_mb"] = udf["file_size"] / (1024 * 1024)
    udf["upload_rate_mbps"] = udf["upload_rate"] / (1024 * 1024)
    udf["download_rate_mbps"] = udf["download_rate"] / (1024 * 1024)
    udf["time_to_cloud_min"] = udf["time_to_cloud_ms"] / 1000 / 60

    # Use customer_name from uploads file if populated, otherwise fall back to tags file or customer_id
    has_names = udf["customer_name"].str.strip().ne("").any()
    if not has_names:
        if not df.empty:
            name_map = df[["customer_id", "customer_name"]].drop_duplicates("customer_id")
            udf = udf.merge(name_map, on="customer_id", how="left")
            udf["customer_name"] = udf["customer_name"].fillna(udf["customer_id"].apply(lambda x: f"(No Name) ID: {x}"))
        else:
            udf["customer_name"] = udf["customer_id"].apply(lambda x: f"ID: {x}")
    else:
        # Fill any blanks with customer_id fallback
        udf["customer_name"] = udf["customer_name"].str.strip()
        udf["customer_name"] = udf.apply(
            lambda row: row["customer_name"] if row["customer_name"] else f"(No Name) ID: {row['customer_id']}",
            axis=1
        )

    upload_customer_ids = sorted(udf["customer_id"].unique())

# =========================================================
# PARSE TELEMETRY FILE (fleet snapshot)
# =========================================================
tdf = pd.DataFrame()
tel_generated_at = "N/A"
tel_accounts = []

if telemetry_file:
    tel_data = json.load(telemetry_file)
    tel_generated_at = tel_data.get("generated_at", "Unknown")
    tel_accounts = tel_data.get("accounts", [])

    trows = []
    for account in tel_accounts:
        customer_name = account.get("customer_name") or f"(No Name) ID: {account.get('customer_id', 'N/A')}"
        customer_id = account.get("customer_id")
        region = account.get("region", "Unknown")

        for tag in account.get("tags", []):
            telemetry = tag.get("latest_telemetry") or {}
            trows.append({
                "customer_name": customer_name,
                "customer_id": customer_id,
                "region": region,
                "serial": tag.get("serial"),
                "model": tag.get("model"),
                "generation": tag.get("generation"),
                "fw_version": telemetry.get("fw_version"),
                "telemetry_updated_at": telemetry.get("updated_at"),
                "tag_updated_at": tag.get("updated_at"),
                "tag_created_at": tag.get("created_at"),
            })

    tdf = pd.DataFrame(trows)
    for col in ["telemetry_updated_at", "tag_updated_at", "tag_created_at"]:
        tdf[col] = pd.to_datetime(tdf[col], utc=True, errors="coerce")

    # Short firmware label (semantic version, dropping the build hash after '+')
    tdf["fw_base"] = tdf["fw_version"].fillna("Unknown").str.split("+").str[0]

# =========================================================
# HEADER
# =========================================================
now = datetime.now(timezone.utc)

def days_ago(dt):
    if pd.isna(dt):
        return "N/A"
    days = (now - dt).days
    if days == 0: return "Today"
    if days == 1: return "1 day ago"
    return f"{days} days ago"

info_parts = []
if tags_file:
    info_parts.append(f"📋 Tags snapshot: **{generated_at}** | 🏢 {len(accounts)} accounts | 🏷️ {len(df)} tags")
if uploads_file:
    date_range = f"{udf['date'].min()} → {udf['date'].max()}" if not udf.empty else "N/A"
    info_parts.append(f"📤 Uploads: **{date_range}** | {len(udf):,} sessions | {udf['serial'].nunique():,} unique tags")
if telemetry_file:
    info_parts.append(f"📶 Telemetry snapshot: **{tel_generated_at}** | 🏢 {len(tel_accounts)} accounts | 🏷️ {len(tdf):,} tags")

st.caption("  &nbsp;|&nbsp;  ".join(info_parts))
st.divider()

# =========================================================
# TABS
# =========================================================
tab_labels = []
if tags_file:
    tab_labels += ["📊 Compare Tags", "🔍 Customer Detail"]
if uploads_file:
    tab_labels += ["📤 Upload Activity", "📈 Upload Trends"]
if telemetry_file:
    tab_labels += ["📶 Latest Telemetry"]

tabs = st.tabs(tab_labels)
tab_index = 0

# =========================================================
# TAB: Compare Tags
# =========================================================
if tags_file:
    with tabs[tab_index]:
        tab_index += 1
        st.subheader("Compare Tag Counts Across Customers")

        search_compare = st.text_input("🔍 Search customers", placeholder="Type to filter...", key="search_compare")
        filtered_compare = [c for c in all_customers if search_compare.lower() in c.lower()] if search_compare else all_customers
        selected_customers = st.multiselect(
            "Select up to 15 customers to compare",
            options=filtered_compare,
            max_selections=15,
        )

        if not selected_customers:
            st.info("Select at least one customer to see the chart.")
        else:
            summary_rows = []
            for cust in selected_customers:
                cust_df = df[df["customer_name"] == cust]
                latest_telemetry = cust_df["telemetry_updated_at"].max()
                latest_tag_update = cust_df["tag_updated_at"].max()
                summary_rows.append({
                    "Customer": cust,
                    "Tag Count": len(cust_df),
                    "Region": cust_df["region"].iloc[0] if not cust_df.empty else "N/A",
                    "Last Telemetry": latest_telemetry.strftime("%Y-%m-%d %H:%M UTC") if not pd.isna(latest_telemetry) else "N/A",
                    "Last Tag Update": latest_tag_update.strftime("%Y-%m-%d %H:%M UTC") if not pd.isna(latest_tag_update) else "N/A",
                })

            summary_df = pd.DataFrame(summary_rows).sort_values("Tag Count", ascending=False)

            fig = px.bar(
                summary_df, x="Customer", y="Tag Count", color="Region",
                text="Tag Count", title="Number of Tags per Customer",
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(
                xaxis_tickangle=-35, xaxis_title=None, yaxis_title="Tag Count",
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=480,
            )
            fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Summary Table")
            st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # =========================================================
    # TAB: Customer Detail
    # =========================================================
    with tabs[tab_index]:
        tab_index += 1
        st.subheader("Customer Detail")

        search_detail = st.text_input("🔍 Search customer name", placeholder="Type to filter...", key="search_detail")
        filtered_detail = [c for c in all_customers if search_detail.lower() in c.lower()] if search_detail else all_customers
        selected_customer = st.selectbox("Select a Customer", options=filtered_detail, key="detail_selectbox")
        customer_df = df[df["customer_name"] == selected_customer].copy()

        col1, col2, col3, col4 = st.columns(4)
        latest_tag_update = customer_df["tag_updated_at"].max()
        latest_telemetry = customer_df["telemetry_updated_at"].max()

        with col1:
            st.metric("🏷️ Total Tags", len(customer_df))
        with col2:
            st.metric("🌏 Region", customer_df["region"].iloc[0] if not customer_df.empty else "N/A")
        with col3:
            st.metric(
                "🔄 Last Tag Update",
                latest_tag_update.strftime("%Y-%m-%d %H:%M UTC") if not pd.isna(latest_tag_update) else "N/A",
                delta=days_ago(latest_tag_update), delta_color="off",
            )
        with col4:
            st.metric(
                "📶 Last Telemetry",
                latest_telemetry.strftime("%Y-%m-%d %H:%M UTC") if not pd.isna(latest_telemetry) else "N/A",
                delta=days_ago(latest_telemetry), delta_color="off",
            )

        st.divider()
        st.subheader("🏷️ Tag Details")
        display_df = customer_df[[
            "serial", "model", "generation", "fw_version",
            "tag_updated_at", "telemetry_updated_at", "tag_created_at"
        ]].copy()
        for c in ["tag_updated_at", "telemetry_updated_at", "tag_created_at"]:
            display_df[c] = display_df[c].dt.strftime("%Y-%m-%d %H:%M UTC")
        display_df = display_df.rename(columns={
            "serial": "Serial", "model": "Model", "generation": "Generation",
            "fw_version": "FW Version", "tag_updated_at": "Tag Last Updated",
            "telemetry_updated_at": "Telemetry Last Updated", "tag_created_at": "Created At",
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        stale_threshold_days = st.slider("⚠️ Flag tags with telemetry older than (days):", 1, 60, 7)
        stale_df = customer_df[(now - customer_df["telemetry_updated_at"]).dt.days > stale_threshold_days]
        if not stale_df.empty:
            st.warning(f"⚠️ {len(stale_df)} tag(s) have not sent telemetry in over {stale_threshold_days} days.")
            stale_display = stale_df[["serial", "model", "telemetry_updated_at"]].copy()
            stale_display["telemetry_updated_at"] = stale_display["telemetry_updated_at"].dt.strftime("%Y-%m-%d %H:%M UTC")
            stale_display = stale_display.rename(columns={"serial": "Serial", "model": "Model", "telemetry_updated_at": "Last Telemetry"})
            st.dataframe(stale_display, use_container_width=True, hide_index=True)
        else:
            st.success(f"✅ All tags have reported telemetry within the last {stale_threshold_days} days.")

# =========================================================
# TAB: Upload Activity (per customer)
# =========================================================
if uploads_file:
    with tabs[tab_index]:
        tab_index += 1
        st.subheader("Upload Activity by Customer")

        upload_customers = sorted(udf["customer_name"].unique())
        search_upload = st.text_input("🔍 Search customer name", placeholder="Type to filter...", key="search_upload")
        filtered_upload = [c for c in upload_customers if search_upload.lower() in c.lower()] if search_upload else upload_customers
        sel_upload_customer = st.selectbox("Select a Customer", options=filtered_upload, key="upload_cust")
        cudf = udf[udf["customer_name"] == sel_upload_customer].copy()

        # Summary metrics
        total_sessions = len(cudf)
        success_sessions = cudf["success"].sum()
        error_sessions = total_sessions - success_sessions
        total_data_gb = cudf["file_size_mb"].sum() / 1024
        avg_upload_rate = cudf[cudf["upload_rate"] > 0]["upload_rate_mbps"].mean()
        median_upload_rate = cudf[cudf["upload_rate"] > 0]["upload_rate_mbps"].median()
        avg_file_size_mb = cudf["file_size_mb"].mean()
        avg_ttc_min_val = cudf[cudf["time_to_cloud_ms"] > 0]["time_to_cloud_min"].mean()

        # Row 1
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("📦 Total Sessions", f"{total_sessions:,}")
        with m2:
            st.metric("✅ Successful", f"{success_sessions:,}")
        with m3:
            st.metric("❌ Errors", f"{error_sessions:,}")
        with m4:
            st.metric("💾 Data Uploaded", f"{total_data_gb:.2f} GB")

        # Row 2
        m5, m6, m7, m8 = st.columns(4)
        with m5:
            st.metric("⚡ Avg Upload Speed", f"{avg_upload_rate:.1f} MB/s" if not pd.isna(avg_upload_rate) else "N/A")
        with m6:
            st.metric("⚡ Median Upload Speed", f"{median_upload_rate:.1f} MB/s" if not pd.isna(median_upload_rate) else "N/A")
        with m7:
            st.metric("📄 Avg File Size", f"{avg_file_size_mb:.1f} MB" if not pd.isna(avg_file_size_mb) else "N/A")
        with m8:
            st.metric("⏱️ Avg Upload Time", f"{avg_ttc_min_val:.1f} min" if not pd.isna(avg_ttc_min_val) else "N/A")

        st.divider()

        col_left, col_right = st.columns(2)

        # Uploads per day bar chart
        with col_left:
            day_summary = cudf.groupby("date").agg(
                Sessions=("serial", "count"),
                Errors=("success", lambda x: (~x).sum()),
            ).reset_index()
            day_summary["date"] = day_summary["date"].astype(str)

            fig_day = go.Figure()
            fig_day.add_bar(x=day_summary["date"], y=day_summary["Sessions"], name="Successful", marker_color="#4CAF50")
            fig_day.add_bar(x=day_summary["date"], y=day_summary["Errors"], name="Errors", marker_color="#F44336")
            fig_day.update_layout(
                barmode="stack", title="Sessions per Day",
                xaxis_title=None, yaxis_title="Sessions",
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", y=-0.2),
            )
            fig_day.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig_day, use_container_width=True)

        # Upload rate distribution
        with col_right:
            rate_data = cudf[cudf["upload_rate_mbps"] > 0]["upload_rate_mbps"]
            fig_rate = px.histogram(
                rate_data, nbins=30,
                title="Upload Rate Distribution (MB/s)",
                labels={"value": "Upload Rate (MB/s)", "count": "Sessions"},
                color_discrete_sequence=["#2196F3"],
            )
            fig_rate.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False, xaxis_title="Upload Rate (MB/s)", yaxis_title="Sessions",
            )
            fig_rate.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig_rate, use_container_width=True)

        # Avg upload speed per day
        col_left2, col_right2 = st.columns(2)

        with col_left2:
            daily_speed = (
                cudf[cudf["upload_rate_mbps"] > 0]
                .groupby("date")["upload_rate_mbps"]
                .mean()
                .reset_index()
            )
            daily_speed["date"] = daily_speed["date"].astype(str)
            daily_speed["upload_rate_mbps"] = daily_speed["upload_rate_mbps"].round(2)
            fig_speed = px.line(
                daily_speed, x="date", y="upload_rate_mbps",
                title="Avg Upload Speed per Day (MB/s)",
                markers=True,
                labels={"upload_rate_mbps": "MB/s", "date": "Date"},
                color_discrete_sequence=["#FF9800"],
            )
            fig_speed.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                xaxis_title=None, yaxis_title="MB/s",
            )
            fig_speed.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig_speed, use_container_width=True)

        with col_right2:
            daily_ttc = (
                cudf[cudf["time_to_cloud_ms"] > 0]
                .groupby("date")["time_to_cloud_min"]
                .mean()
                .reset_index()
            )
            daily_ttc["date"] = daily_ttc["date"].astype(str)
            daily_ttc["time_to_cloud_min"] = daily_ttc["time_to_cloud_min"].round(2)
            fig_ttc = px.line(
                daily_ttc, x="date", y="time_to_cloud_min",
                title="Avg Upload Time per Day (minutes)",
                markers=True,
                labels={"time_to_cloud_min": "Minutes", "date": "Date"},
                color_discrete_sequence=["#9C27B0"],
            )
            fig_ttc.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                xaxis_title=None, yaxis_title="Minutes",
            )
            fig_ttc.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig_ttc, use_container_width=True)

        # Errors detail
        if error_sessions > 0:
            st.subheader("❌ Error Details")
            err_df = cudf[~cudf["success"]][["serial", "date", "filename", "error"]].copy()
            err_df["date"] = err_df["date"].astype(str)
            err_df = err_df.rename(columns={"serial": "Serial", "date": "Date", "filename": "File", "error": "Error Message"})
            st.dataframe(err_df, use_container_width=True, hide_index=True)

        # Full session table
        with st.expander("📋 All Sessions"):
            show_df = cudf[["serial", "date", "file_size_mb", "upload_rate_mbps", "time_to_cloud_min", "session_index", "success"]].copy()
            show_df["date"] = show_df["date"].astype(str)
            show_df["file_size_mb"] = show_df["file_size_mb"].round(1)
            show_df["upload_rate_mbps"] = show_df["upload_rate_mbps"].round(2)
            show_df["time_to_cloud_min"] = show_df["time_to_cloud_min"].round(1)
            show_df = show_df.rename(columns={
                "serial": "Serial", "date": "Date", "file_size_mb": "File Size (MB)",
                "upload_rate_mbps": "Upload Rate (MB/s)", "time_to_cloud_min": "Time to Cloud (min)",
                "session_index": "Session #", "success": "Success",
            })
            st.dataframe(show_df, use_container_width=True, hide_index=True)

    # =========================================================
    # TAB: Upload Trends (global)
    # =========================================================
    with tabs[tab_index]:
        tab_index += 1
        st.subheader("Global Upload Trends")

        # Daily uploads across all customers
        daily_global = udf.groupby(["date", "region"]).agg(
            Sessions=("serial", "count"),
            Errors=("success", lambda x: (~x).sum()),
            Total_GB=("file_size_mb", lambda x: x.sum() / 1024),
            Avg_Rate_MBps=("upload_rate_mbps", lambda x: x[x > 0].mean()),
        ).reset_index()
        daily_global["date"] = daily_global["date"].astype(str)

        fig_global = px.bar(
            daily_global, x="date", y="Sessions", color="region",
            title="Daily Upload Sessions by Region",
            labels={"date": "Date", "Sessions": "Sessions", "region": "Region"},
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_global.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            xaxis_title=None, barmode="stack",
        )
        fig_global.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
        st.plotly_chart(fig_global, use_container_width=True)

        col1, col2 = st.columns(2)

        # Data volume per day
        with col1:
            daily_gb = udf.groupby("date")["file_size_mb"].sum().reset_index()
            daily_gb["GB"] = daily_gb["file_size_mb"] / 1024
            daily_gb["date"] = daily_gb["date"].astype(str)
            fig_gb = px.area(
                daily_gb, x="date", y="GB",
                title="Daily Data Volume (GB)",
                color_discrete_sequence=["#2196F3"],
            )
            fig_gb.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                xaxis_title=None,
            )
            fig_gb.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig_gb, use_container_width=True)

        # Top customers by upload volume
        with col2:
            top_customers = (
                udf.groupby("customer_name")["file_size_mb"]
                .sum()
                .reset_index()
                .sort_values("file_size_mb", ascending=False)
                .head(15)
            )
            top_customers["GB"] = top_customers["file_size_mb"] / 1024
            fig_top = px.bar(
                top_customers, x="GB", y="customer_name",
                orientation="h",
                title="Top 15 Customers by Data Uploaded (GB)",
                color="GB",
                color_continuous_scale="Blues",
            )
            fig_top.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                yaxis_title=None, xaxis_title="GB Uploaded",
                yaxis=dict(autorange="reversed"),
                coloraxis_showscale=False,
            )
            fig_top.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig_top, use_container_width=True)

        # Average upload time by region
        st.subheader("Average Upload Time by Region")

        region_time = (
            udf[udf["time_to_cloud_ms"] > 0]
            .groupby("region")
            .agg(
                Avg_Minutes=("time_to_cloud_min", "mean"),
                Median_Minutes=("time_to_cloud_min", "median"),
                Min_Minutes=("time_to_cloud_min", "min"),
                Max_Minutes=("time_to_cloud_min", "max"),
                Sessions=("serial", "count"),
            )
            .reset_index()
            .round(2)
        )

        # Summary metric cards — one per region
        region_cols = st.columns(len(region_time))
        for i, row in region_time.iterrows():
            with region_cols[i]:
                st.metric(
                    label=f"🌏 {row['region']}",
                    value=f"{row['Avg_Minutes']:.1f} min avg",
                    delta=f"median {row['Median_Minutes']:.1f} min",
                    delta_color="off",
                )

        col_rt1, col_rt2 = st.columns(2)

        with col_rt1:
            fig_region_bar = px.bar(
                region_time, x="region", y="Avg_Minutes",
                color="region",
                text=region_time["Avg_Minutes"].apply(lambda x: f"{x:.1f} min"),
                title="Average Time to Cloud by Region (minutes)",
                color_discrete_sequence=px.colors.qualitative.Set2,
                error_y=None,
            )
            fig_region_bar.update_traces(textposition="outside")
            fig_region_bar.update_layout(
                xaxis_title=None, yaxis_title="Minutes",
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            fig_region_bar.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig_region_bar, use_container_width=True)

        with col_rt2:
            # Box plot showing distribution per region
            box_data = udf[(udf["time_to_cloud_ms"] > 0) & (udf["time_to_cloud_min"] < udf["time_to_cloud_min"].quantile(0.99))]
            fig_box = px.box(
                box_data, x="region", y="time_to_cloud_min",
                color="region",
                title="Upload Time Distribution by Region (minutes, excl. top 1%)",
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"time_to_cloud_min": "Minutes", "region": "Region"},
            )
            fig_box.update_layout(
                xaxis_title=None, yaxis_title="Minutes",
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            fig_box.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig_box, use_container_width=True)

        # Summary table
        region_time_display = region_time.rename(columns={
            "region": "Region", "Avg_Minutes": "Avg (min)", "Median_Minutes": "Median (min)",
            "Min_Minutes": "Min (min)", "Max_Minutes": "Max (min)", "Sessions": "Sessions",
        })
        st.dataframe(region_time_display, use_container_width=True, hide_index=True)

        st.divider()

        # Error rate by customer
        st.subheader("Error Rate by Customer")
        err_summary = udf.groupby("customer_name").agg(
            Sessions=("serial", "count"),
            Errors=("success", lambda x: (~x).sum()),
        ).reset_index()
        err_summary["Error Rate %"] = (err_summary["Errors"] / err_summary["Sessions"] * 100).round(1)
        err_summary = err_summary[err_summary["Errors"] > 0].sort_values("Error Rate %", ascending=False)

        if not err_summary.empty:
            fig_err = px.bar(
                err_summary, x="customer_name", y="Error Rate %",
                text="Error Rate %",
                title="Upload Error Rate by Customer (customers with errors only)",
                color="Error Rate %", color_continuous_scale="Reds",
            )
            fig_err.update_traces(texttemplate="%{text}%", textposition="outside")
            fig_err.update_layout(
                xaxis_tickangle=-35, xaxis_title=None,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                coloraxis_showscale=False,
            )
            fig_err.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig_err, use_container_width=True)
        else:
            st.success("✅ No upload errors found across all customers!")

# =========================================================
# TAB: Latest Telemetry (fleet snapshot)
# =========================================================
if telemetry_file:
    with tabs[tab_index]:
        tab_index += 1
        st.subheader("📶 Fleet Telemetry Overview")

        # ---- Page-level date scope (hard floor 1 May 2026) ----
        # This date range applies to the ENTIRE Latest Telemetry page.
        HARD_START = date(2026, 5, 1)
        page_start = page_end = None
        _tel_dates_all = tdf["telemetry_updated_at"].dropna()
        if not _tel_dates_all.empty and _tel_dates_all.max().date() >= HARD_START:
            _page_max = _tel_dates_all.max().date()
            _page_sel = st.date_input(
                "📅 Telemetry reported between (applies to this whole page)",
                value=(HARD_START, _page_max),
                min_value=HARD_START, max_value=_page_max,
                key="tel_page_date",
            )
            if isinstance(_page_sel, (list, tuple)):
                page_start = _page_sel[0]
                page_end = _page_sel[1] if len(_page_sel) > 1 else _page_sel[0]
            else:
                page_start = page_end = _page_sel
            tdf = tdf[
                tdf["telemetry_updated_at"].notna()
                & (tdf["telemetry_updated_at"].dt.date >= page_start)
                & (tdf["telemetry_updated_at"].dt.date <= page_end)
            ].copy()
            st.caption(f"📅 Page scoped to telemetry reported **{page_start} → {page_end}** · {len(tdf):,} tags.")

        if tdf.empty:
            st.info("No telemetry was reported in the selected date range.")
            st.stop()

        # ---- Summary metrics ----
        total_tags_t = len(tdf)
        reporting = int(tdf["telemetry_updated_at"].notna().sum())
        silent = total_tags_t - reporting
        distinct_fw = tdf["fw_version"].dropna().nunique()
        fw_nonnull = tdf["fw_version"].dropna()
        most_common_fw = fw_nonnull.mode().iloc[0] if not fw_nonnull.empty else "N/A"
        latest_fleet_tel = tdf["telemetry_updated_at"].max()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("🏷️ Total Tags", f"{total_tags_t:,}")
        with c2:
            st.metric(
                "📶 Reporting Telemetry", f"{reporting:,}",
                delta=f"{silent:,} silent" if silent else "all reporting",
                delta_color="off",
            )
        with c3:
            st.metric("🔢 Firmware Versions", f"{distinct_fw}")
        with c4:
            st.metric(
                "🕒 Latest Fleet Telemetry",
                latest_fleet_tel.strftime("%Y-%m-%d %H:%M UTC") if not pd.isna(latest_fleet_tel) else "N/A",
                delta=days_ago(latest_fleet_tel), delta_color="off",
            )

        st.caption(f"Most common firmware: **{most_common_fw}**")
        st.divider()

        # ---- Telemetry freshness buckets ----
        tdf_age = tdf.copy()
        tdf_age["days_since"] = (now - tdf_age["telemetry_updated_at"]).dt.days

        def freshness_bucket(row):
            if pd.isna(row["telemetry_updated_at"]):
                return "Never reported"
            d = row["days_since"]
            if d <= 0: return "Today"
            if d <= 7: return "1–7 days"
            if d <= 30: return "8–30 days"
            return "31+ days"

        bucket_order = ["Today", "1–7 days", "8–30 days", "31+ days", "Never reported"]
        bucket_colors = {
            "Today": "#4CAF50", "1–7 days": "#8BC34A", "8–30 days": "#FF9800",
            "31+ days": "#F44336", "Never reported": "#9E9E9E",
        }
        tdf_age["freshness"] = tdf_age.apply(freshness_bucket, axis=1)

        col_l, col_r = st.columns(2)

        # Firmware distribution (top 15 by tag count)
        with col_l:
            fw_counts = (
                tdf["fw_version"].fillna("Unknown")
                .value_counts()
                .head(15)
                .reset_index()
            )
            fw_counts.columns = ["Firmware", "Tags"]
            fig_fw = px.bar(
                fw_counts, x="Tags", y="Firmware", orientation="h",
                title="Firmware Version Distribution (top 15)",
                color="Tags", color_continuous_scale="Blues", text="Tags",
            )
            fig_fw.update_traces(textposition="outside")
            fig_fw.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                yaxis_title=None, xaxis_title="Tags",
                yaxis=dict(autorange="reversed"), coloraxis_showscale=False,
            )
            fig_fw.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig_fw, use_container_width=True)

        # Telemetry freshness donut
        with col_r:
            fresh_counts = (
                tdf_age["freshness"].value_counts()
                .reindex(bucket_order)
                .dropna()
                .reset_index()
            )
            fresh_counts.columns = ["Freshness", "Tags"]
            fig_fresh = px.pie(
                fresh_counts, names="Freshness", values="Tags", hole=0.5,
                title="Telemetry Freshness",
                color="Freshness", color_discrete_map=bucket_colors,
                category_orders={"Freshness": bucket_order},
            )
            fig_fresh.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", y=-0.1),
            )
            st.plotly_chart(fig_fresh, use_container_width=True)

        # ---- Firmware by region ----
        st.subheader("Firmware Spread by Region")
        fw_region = (
            tdf.groupby(["region", "fw_base"]).size().reset_index(name="Tags")
        )
        fig_fwr = px.bar(
            fw_region, x="region", y="Tags", color="fw_base",
            title="Firmware (semantic version) by Region",
            labels={"region": "Region", "fw_base": "Firmware"},
            color_discrete_sequence=px.colors.qualitative.Set3,
        )
        fig_fwr.update_layout(
            barmode="stack", xaxis_title=None,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        fig_fwr.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
        st.plotly_chart(fig_fwr, use_container_width=True)

        st.divider()

        # ---- Firmware adoption by team ----
        st.subheader("🎯 Firmware Adoption by Team")

        col_region, col_fw = st.columns(2)
        with col_region:
            region_options = ["All"] + sorted(tdf["region"].dropna().unique().tolist())
            sel_region = st.selectbox(
                "Region", options=region_options, index=0, key="adopt_region"
            )
        with col_fw:
            fw_options = tdf["fw_version"].dropna().value_counts().index.tolist()
            default_idx = fw_options.index(most_common_fw) if most_common_fw in fw_options else 0
            target_fw = st.selectbox(
                "Target firmware version", options=fw_options, index=default_idx, key="target_fw"
            )

        adopt = tdf.copy()

        # Region filter
        if sel_region != "All":
            adopt = adopt[adopt["region"] == sel_region]

        # Date scope comes from the page-level filter above
        start_d, end_d = page_start, page_end

        if adopt.empty:
            st.info("No tags reported telemetry in the selected date range.")
        else:
            adopt["on_target"] = adopt["fw_version"] == target_fw
            team_adopt = adopt.groupby("customer_name").agg(
                On_Target=("on_target", "sum"),
                Total=("on_target", "count"),
            ).reset_index()
            team_adopt["Not_On_Target"] = team_adopt["Total"] - team_adopt["On_Target"]
            team_adopt["% On Target"] = (team_adopt["On_Target"] / team_adopt["Total"] * 100).round(1)
            team_adopt["Status"] = team_adopt["Not_On_Target"].apply(
                lambda n: "✅ Compliant" if n == 0 else "⚠️ Non-compliant"
            )
            team_adopt = team_adopt[
                ["customer_name", "On_Target", "Not_On_Target", "Total", "% On Target", "Status"]
            ].sort_values("Not_On_Target", ascending=False)

            # ---- Compliance summary for the whole fleet (within the date range) ----
            total_tags_range = len(adopt)
            tags_on_target = int(adopt["on_target"].sum())
            fleet_compliance_pct = (tags_on_target / total_tags_range * 100) if total_tags_range else 0
            total_teams = len(team_adopt)
            compliant_teams = int((team_adopt["Not_On_Target"] == 0).sum())
            noncompliant_teams = total_teams - compliant_teams
            team_compliance_pct = (compliant_teams / total_teams * 100) if total_teams else 0

            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                st.metric(
                    "🛡️ Fleet Compliance (tags)", f"{fleet_compliance_pct:.1f}%",
                    delta=f"{tags_on_target:,} / {total_tags_range:,} on target", delta_color="off",
                )
            with cc2:
                st.metric(
                    "🏢 Compliant Teams", f"{team_compliance_pct:.1f}%",
                    delta=f"{compliant_teams:,} / {total_teams:,} teams", delta_color="off",
                )
            with cc3:
                st.metric(
                    "⚠️ Non-compliant Teams", f"{noncompliant_teams:,}",
                    delta="1+ tag off target", delta_color="off",
                )

            noncompliant_only = st.checkbox(
                "Show only non-compliant teams (1+ tag not on target)", value=False, key="noncompliant_only"
            )
            if noncompliant_only:
                team_adopt = team_adopt[team_adopt["Not_On_Target"] > 0]

            range_note = f" (telemetry {start_d} → {end_d})" if start_d else ""
            region_note = "all regions" if sel_region == "All" else f"region {sel_region}"
            st.caption(
                f"**{tags_on_target:,}** of **{total_tags_range:,}** tags in {region_note} are on `{target_fw}`{range_note}."
            )

            team_adopt_display = team_adopt.rename(columns={
                "customer_name": "Team",
                "On_Target": f"On {target_fw}",
                "Not_On_Target": f"Not on {target_fw}",
            })
            st.dataframe(team_adopt_display, use_container_width=True, hide_index=True)

        st.divider()

        # ---- Stale telemetry flag ----
        st.subheader("⚠️ Stale Telemetry")
        stale_days_t = st.slider(
            "Flag tags with telemetry older than (days):",
            1, 90, 7, key="tel_stale",
        )
        stale_t = tdf_age[(tdf_age["days_since"] > stale_days_t) | (tdf_age["telemetry_updated_at"].isna())]
        if not stale_t.empty:
            st.warning(f"⚠️ {len(stale_t):,} tag(s) have not reported telemetry in over {stale_days_t} days (or never).")
            by_cust = (
                stale_t.groupby("customer_name").size()
                .reset_index(name="Stale Tags")
                .sort_values("Stale Tags", ascending=False)
                .head(20)
            )
            fig_stale = px.bar(
                by_cust, x="Stale Tags", y="customer_name", orientation="h",
                title=f"Top Customers by Stale Tags (> {stale_days_t} days)",
                color="Stale Tags", color_continuous_scale="Reds", text="Stale Tags",
            )
            fig_stale.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                yaxis_title=None, xaxis_title="Stale Tags",
                yaxis=dict(autorange="reversed"), coloraxis_showscale=False,
            )
            fig_stale.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig_stale, use_container_width=True)
        else:
            st.success(f"✅ All tags have reported telemetry within the last {stale_days_t} days.")

        st.divider()

        # ---- Per-customer drill-down ----
        st.subheader("🔍 Tag Telemetry by Customer")
        tel_customers = sorted(tdf["customer_name"].unique())
        search_tel = st.text_input("🔍 Search customer name", placeholder="Type to filter...", key="search_tel")
        filtered_tel = [c for c in tel_customers if search_tel.lower() in c.lower()] if search_tel else tel_customers
        sel_tel_customer = st.selectbox("Select a Customer", options=filtered_tel, key="tel_cust")
        ctdf = tdf_age[tdf_age["customer_name"] == sel_tel_customer].copy()

        detail = ctdf[["serial", "model", "fw_version", "telemetry_updated_at", "days_since", "freshness", "region"]].copy()
        detail["telemetry_updated_at"] = detail["telemetry_updated_at"].dt.strftime("%Y-%m-%d %H:%M UTC")
        detail["days_since"] = detail["days_since"].astype("Int64")
        detail = detail.rename(columns={
            "serial": "Serial", "model": "Model", "fw_version": "Firmware",
            "telemetry_updated_at": "Last Telemetry", "days_since": "Days Since",
            "freshness": "Freshness", "region": "Region",
        })
        st.dataframe(detail, use_container_width=True, hide_index=True)
