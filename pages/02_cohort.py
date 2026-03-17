# pages/02_CRM_Cohort.py
import pandas as pd
import numpy as np
import streamlit as st
from io import BytesIO

# =====================================================
# LOAD DATA (QUAN TRỌNG NHẤT)
# =====================================================
@st.cache_data(show_spinner=False)
def load_data():
    df = pd.read_parquet("data/crm_cohort.parquet")

    if df is None or df.empty:
        return df

    df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce")

    # tối ưu RAM
    cat_cols = ["LoaiCT", "Brand", "Region", "Điểm_mua_hàng"]
    for c in cat_cols:
        if c in df.columns:
            df[c] = df[c].astype("category")

    # numeric
    for c in ["Tổng_Gross", "Tổng_Net"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df

@st.cache_data(show_spinner=False)
def get_first_purchase(df):
    return (
        df.groupby("Số_điện_thoại")["Ngày"]
        .min()
        .reset_index()
        .rename(columns={"Ngày": "First_Date"})
    )

df = load_data()

if df is None or df.empty:
    st.warning("⚠ Không có dữ liệu.")
    st.stop()

# =====================================================
# UI
# =====================================================
st.title("📤 CRM & Cohort Retention")

# =====================================================
# FILTER
# =====================================================
with st.sidebar:
    st.header("🎛️ Bộ lọc")

    start = st.date_input("Từ ngày", df["Ngày"].min())
    end = st.date_input("Đến ngày", df["Ngày"].max())

    brand = st.multiselect("Brand", df["Brand"].dropna().unique())
    region = st.multiselect("Region", df["Region"].dropna().unique())
    store = st.multiselect("Cửa hàng", df["Điểm_mua_hàng"].dropna().unique())

# =====================================================
# APPLY FILTER
# =====================================================
df_f = df[
    (df["Ngày"] >= pd.to_datetime(start)) &
    (df["Ngày"] <= pd.to_datetime(end))
].copy()

if brand:
    df_f = df_f[df_f["Brand"].isin(brand)]
if region:
    df_f = df_f[df_f["Region"].isin(region)]
if store:
    df_f = df_f[df_f["Điểm_mua_hàng"].isin(store)]

if df_f.empty:
    st.warning("⚠ Không có dữ liệu")
    st.stop()

today = df_f["Ngày"].max()

# =====================================================
# CRM TABLE
# =====================================================
df_export = (
    df_f.groupby("Số_điện_thoại")
    .agg(
        Name=("tên_KH", "first"),
        Gross=("Tổng_Gross", "sum"),
        Net=("Tổng_Net", "sum"),
        Orders=("Số_CT", "nunique"),
        First_Order=("Ngày", "min"),
        Last_Order=("Ngày", "max"),
    )
    .reset_index()
)

df_export["CK_%"] = np.where(
    df_export["Gross"] > 0,
    (df_export["Gross"] - df_export["Net"]) / df_export["Gross"] * 100,
    0,
)

df_export["Days_Inactive"] = (today - df_export["Last_Order"]).dt.days

# =====================================================
# KPI CRM
# =====================================================
st.subheader("📊 CRM Summary")

col1, col2, col3 = st.columns(3)

col1.metric("Tổng KH", f"{df_export['Số_điện_thoại'].nunique():,}")
col2.metric("Tổng Net", f"{df_export['Net'].sum():,.0f}")
col3.metric("CK %", f"{df_export['CK_%'].mean():.2f}%")

# =====================================================
# TABLE CRM
# =====================================================
st.subheader("📄 Danh sách KH")

df_show = df_export.copy()

for c in ["Gross", "Net", "Orders"]:
    df_show[c] = df_show[c].map(lambda x: f"{x:,.0f}")

df_show["CK_%"] = df_show["CK_%"].map(lambda x: f"{x:.2f}%")
df_show["Last_Order"] = df_show["Last_Order"].dt.strftime("%Y-%m-%d")

st.dataframe(df_show, use_container_width=True)

# =====================================================
# EXPORT
# =====================================================
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

st.download_button(
    "📥 Export Excel",
    data=to_excel(df_export),
    file_name="crm.xlsx"
)

# =====================================================
# NEW VS RETURN
# =====================================================
df_fp = get_first_purchase(df)
df_kh = df_f.merge(df_fp, on="Số_điện_thoại", how="left")

df_kh["Type"] = np.where(
    df_kh["First_Date"] >= pd.to_datetime(start),
    "KH mới",
    "KH quay lại",
)

st.subheader("👥 KH mới vs KH quay lại")
st.dataframe(
    df_kh.groupby("Type")["Số_điện_thoại"].nunique().reset_index(name="Số KH"),
    use_container_width=True,
)

# =====================================================
# COHORT
# =====================================================
st.subheader("🏅 Cohort Retention")

df_c = df_f.copy()
df_c["Order_Month"] = df_c["Ngày"].dt.to_period("M")
df_c["First_Month"] = df_c.groupby("Số_điện_thoại")["Order_Month"].transform("min")

df_c["Index"] = (
    (df_c["Order_Month"].dt.year - df_c["First_Month"].dt.year) * 12 +
    (df_c["Order_Month"].dt.month - df_c["First_Month"].dt.month)
)

cohort = (
    df_c.groupby(["First_Month", "Index"])["Số_điện_thoại"]
    .nunique()
    .unstack()
)

cohort = cohort.divide(cohort[0], axis=0) * 100
cohort = cohort.round(2)

st.dataframe(cohort, use_container_width=True)
