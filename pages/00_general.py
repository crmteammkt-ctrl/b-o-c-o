# pages/00_general_report.py
import pandas as pd
import numpy as np
import streamlit as st

# =====================================================
# LOAD DATA
# =====================================================
@st.cache_data(show_spinner=False)
def load_data():
    df = pd.read_parquet("data/general.parquet")

    if df is None or df.empty:
        return df

    df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce")

    # tối ưu
    cat_cols = ["LoaiCT", "Brand", "Region", "Điểm_mua_hàng", "Mã_NB"]
    for c in cat_cols:
        if c in df.columns:
            df[c] = df[c].astype("category")

    return df

df = load_data()

if df is None or df.empty:
    st.warning("⚠ Không có dữ liệu.")
    st.stop()

# =====================================================
# UI
# =====================================================
st.set_page_config(page_title="General Dashboard", layout="wide")
st.title("📊 GENERAL DASHBOARD")

# =====================================================
# FILTER
# =====================================================
with st.sidebar:
    st.header("🎛️ Bộ lọc")

    start_date = st.date_input("Từ ngày", df["Ngày"].min())
    end_date = st.date_input("Đến ngày", df["Ngày"].max())

    loaiCT = st.multiselect("Loại CT", df["LoaiCT"].dropna().unique())
    brand = st.multiselect("Brand", df["Brand"].dropna().unique())
    region = st.multiselect("Region", df["Region"].dropna().unique())
    store = st.multiselect("Cửa hàng", df["Điểm_mua_hàng"].dropna().unique())

# =====================================================
# APPLY FILTER
# =====================================================
df_f = df[
    (df["Ngày"] >= pd.to_datetime(start_date)) &
    (df["Ngày"] <= pd.to_datetime(end_date))
].copy()

if loaiCT:
    df_f = df_f[df_f["LoaiCT"].isin(loaiCT)]
if brand:
    df_f = df_f[df_f["Brand"].isin(brand)]
if region:
    df_f = df_f[df_f["Region"].isin(region)]
if store:
    df_f = df_f[df_f["Điểm_mua_hàng"].isin(store)]

if df_f.empty:
    st.warning("⚠ Không có dữ liệu sau filter")
    st.stop()

# =====================================================
# KPI
# =====================================================
gross = df_f["Tổng_Gross"].sum()
net = df_f["Tổng_Net"].sum()
orders = df_f["Số_CT"].nunique()

ck = (1 - net / gross) * 100 if gross > 0 else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Gross", f"{gross:,.0f}")
c2.metric("Net", f"{net:,.0f}")
c3.metric("CK %", f"{ck:.2f}%")
c4.metric("Đơn hàng", f"{orders:,}")

# =====================================================
# TIME TABLE
# =====================================================
st.subheader("⏱ Theo thời gian")

df_f["Time"] = df_f["Ngày"].dt.date

g_time = (
    df_f.groupby("Time")
    .agg(
        Gross=("Tổng_Gross", "sum"),
        Net=("Tổng_Net", "sum"),
        Orders=("Số_CT", "nunique"),
    )
    .reset_index()
    .sort_values("Time")
)

g_time["CK_%"] = np.where(
    g_time["Gross"] > 0,
    (1 - g_time["Net"] / g_time["Gross"]) * 100,
    0
)

g_time["Time"] = g_time["Time"].astype(str)

st.dataframe(g_time, use_container_width=True)

# =====================================================
# REGION
# =====================================================
st.subheader("🌍 Theo Region")

g_region = (
    df_f.groupby("Region")
    .agg(
        Gross=("Tổng_Gross", "sum"),
        Net=("Tổng_Net", "sum"),
        Orders=("Số_CT", "nunique"),
    )
    .reset_index()
    .sort_values("Net", ascending=False)
)

g_region["CK_%"] = np.where(
    g_region["Gross"] > 0,
    (1 - g_region["Net"] / g_region["Gross"]) * 100,
    0
)

st.dataframe(g_region, use_container_width=True)

# =====================================================
# STORE
# =====================================================
st.subheader("🏪 Theo Cửa hàng")

g_store = (
    df_f.groupby("Điểm_mua_hàng")
    .agg(
        Gross=("Tổng_Gross", "sum"),
        Net=("Tổng_Net", "sum"),
        Orders=("Số_CT", "nunique"),
    )
    .reset_index()
    .sort_values("Net", ascending=False)
)

g_store["CK_%"] = np.where(
    g_store["Gross"] > 0,
    (1 - g_store["Net"] / g_store["Gross"]) * 100,
    0
)

st.dataframe(g_store, use_container_width=True)

# =====================================================
# PRODUCT
# =====================================================
st.subheader("📦 Theo Mã NB")

g_prod = (
    df_f.groupby("Mã_NB")
    .agg(
        Gross=("Tổng_Gross", "sum"),
        Net=("Tổng_Net", "sum"),
        Orders=("Số_lượng", "sum"),
    )
    .reset_index()
    .sort_values("Net", ascending=False)
)

g_prod["CK_%"] = np.where(
    g_prod["Gross"] > 0,
    (1 - g_prod["Net"] / g_prod["Gross"]) * 100,
    0
)

st.dataframe(g_prod, use_container_width=True)
