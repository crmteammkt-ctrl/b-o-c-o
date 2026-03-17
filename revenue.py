# pages/01_revenue_report.py
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# =====================================================
# LOAD DATA
# =====================================================
@st.cache_data(show_spinner=False)
def load_data():
    df = pd.read_parquet("data/revenue.parquet")

    if df is None or df.empty:
        return df

    df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce")

    # tối ưu RAM
    cat_cols = ["LoaiCT", "Region", "Điểm_mua_hàng"]
    for c in cat_cols:
        if c in df.columns:
            df[c] = df[c].astype("category")

    # numeric
    for c in ["Tổng_Gross", "Tổng_Net"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df

df = load_data()

if df is None or df.empty:
    st.warning("⚠ Không có dữ liệu.")
    st.stop()

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(page_title="📈 Báo cáo Doanh thu", layout="wide")
st.title("📈 Báo cáo Doanh thu")

# =====================================================
# WEEK
# =====================================================
WEEKDAY_MAP = {
    "Thứ 2": 0, "Thứ 3": 1, "Thứ 4": 2, "Thứ 5": 3,
    "Thứ 6": 4, "Thứ 7": 5, "Chủ nhật": 6
}

def week_anchor(dt, week_start):
    return (dt - pd.to_timedelta((dt.dt.weekday - week_start) % 7, unit="D")).dt.normalize()

def label_from_time(time_s, grain):
    t = pd.to_datetime(time_s)
    if grain == "Ngày":
        return t.dt.strftime("%Y-%m-%d")
    if grain == "Tuần":
        iso = t.dt.isocalendar()
        return "Tuần " + iso["week"].astype(str).str.zfill(2)
    if grain == "Tháng":
        return t.dt.to_period("M").astype(str)
    return t.dt.to_period("Q").astype(str)

# =====================================================
# FILTER
# =====================================================
with st.sidebar:
    st.header("🎛 Bộ lọc")

    time_grain = st.selectbox("Phân tích theo", ["Ngày", "Tuần", "Tháng", "Quý"])

    if time_grain == "Tuần":
        week_start = WEEKDAY_MAP[st.selectbox("Tuần bắt đầu", list(WEEKDAY_MAP.keys()))]
    else:
        week_start = 0

    start = st.date_input("Từ ngày", df["Ngày"].min())
    end = st.date_input("Đến ngày", df["Ngày"].max())

    loaict = st.multiselect("Loại CT", df["LoaiCT"].dropna().unique())
    region = st.multiselect("Region", df["Region"].dropna().unique())
    store = st.multiselect("Cửa hàng", df["Điểm_mua_hàng"].dropna().unique())

# =====================================================
# APPLY FILTER
# =====================================================
df_f = df[
    (df["Ngày"] >= pd.to_datetime(start)) &
    (df["Ngày"] <= pd.to_datetime(end))
].copy()

if loaict:
    df_f = df_f[df_f["LoaiCT"].isin(loaict)]
if region:
    df_f = df_f[df_f["Region"].isin(region)]
if store:
    df_f = df_f[df_f["Điểm_mua_hàng"].isin(store)]

if df_f.empty:
    st.warning("⚠ Không có dữ liệu")
    st.stop()

# =====================================================
# TIME
# =====================================================
if time_grain == "Ngày":
    df_f["Time"] = df_f["Ngày"].dt.normalize()
elif time_grain == "Tuần":
    df_f["Time"] = week_anchor(df_f["Ngày"], week_start)
elif time_grain == "Tháng":
    df_f["Time"] = df_f["Ngày"].dt.to_period("M").dt.to_timestamp()
else:
    df_f["Time"] = df_f["Ngày"].dt.to_period("Q").dt.to_timestamp()

df_f["Label"] = label_from_time(df_f["Time"], time_grain)

# =====================================================
# SUMMARY
# =====================================================
summary = (
    df_f.groupby("Time")
    .agg(
        Label=("Label", "first"),
        Gross=("Tổng_Gross", "sum"),
        Net=("Tổng_Net", "sum"),
        Orders=("Số_CT", "nunique"),
    )
    .reset_index()
    .sort_values("Time")
)

summary["CK_%"] = np.where(summary["Gross"] > 0, (1 - summary["Net"] / summary["Gross"]) * 100, 0)
summary["Growth_%"] = summary["Net"].pct_change() * 100
summary["AOV"] = np.where(summary["Orders"] > 0, summary["Net"] / summary["Orders"], 0)

# =====================================================
# DISPLAY
# =====================================================
st.subheader("📊 Tổng quan")

show = summary.copy()
show["Gross"] = show["Gross"].map(lambda x: f"{x:,.0f}")
show["Net"] = show["Net"].map(lambda x: f"{x:,.0f}")
show["Orders"] = show["Orders"].map(lambda x: f"{x:,}")
show["AOV"] = show["AOV"].map(lambda x: f"{x:,.0f}")
show["CK_%"] = show["CK_%"].map(lambda x: f"{x:.2f}%")
show["Growth_%"] = show["Growth_%"].map(lambda x: f"{x:.2f}%")

st.dataframe(show.drop(columns=["Time"]), use_container_width=True)

# =====================================================
# CHART
# =====================================================
fig = px.line(summary, x="Time", y=["Gross", "Net"], markers=True)
st.plotly_chart(fig, use_container_width=True)

# =====================================================
# REGION
# =====================================================
st.subheader("🌍 Theo Region")

g_region = (
    df_f.groupby(["Region", "Time"])
    .agg(Net=("Tổng_Net", "sum"))
    .reset_index()
)

latest = g_region["Time"].max()
g_region = g_region[g_region["Time"] == latest].sort_values("Net", ascending=False)

st.dataframe(g_region, use_container_width=True)

# =====================================================
# STORE
# =====================================================
st.subheader("🏪 Top / Bottom")

g_store = (
    df_f.groupby(["Điểm_mua_hàng", "Time"])
    .agg(Net=("Tổng_Net", "sum"))
    .reset_index()
)

latest = g_store["Time"].max()
g_store = g_store[g_store["Time"] == latest]

top10 = g_store.sort_values("Net", ascending=False).head(10)
bottom10 = g_store.sort_values("Net", ascending=True).head(10)

col1, col2 = st.columns(2)

with col1:
    st.write("Top 10")
    st.dataframe(top10, use_container_width=True)

with col2:
    st.write("Bottom 10")
    st.dataframe(bottom10, use_container_width=True)
