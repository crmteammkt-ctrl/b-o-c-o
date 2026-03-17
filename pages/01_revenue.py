# pages/01_revenue.py
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# =====================================================
# FORMAT HELPERS
# =====================================================
def fmt_int(x):
    if pd.isna(x):
        return ""
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return ""

def fmt_pct(x, decimals=2, with_sign=False):
    if pd.isna(x):
        return ""
    try:
        v = float(x)
        s = f"{v:,.{decimals}f}%"
        if with_sign and v > 0:
            s = "+" + s
        return s
    except Exception:
        return ""

# =====================================================
# LOAD DATA
# =====================================================
@st.cache_data(show_spinner=False)
def load_data():
    df = pd.read_parquet("data/revenue.parquet")

    if df is None or df.empty:
        return df

    if "Ngày" in df.columns:
        df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce")
        df = df.dropna(subset=["Ngày"])

    for c in ["Tổng_Gross", "Tổng_Net"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    for c in ["LoaiCT", "Region", "Điểm_mua_hàng", "Số_CT"]:
        if c in df.columns:
            df[c] = df[c].astype("category")

    return df

# =====================================================
# WEEK HELPERS
# =====================================================
WEEKDAY_MAP = {
    "Thứ 2": 0, "Thứ 3": 1, "Thứ 4": 2, "Thứ 5": 3,
    "Thứ 6": 4, "Thứ 7": 5, "Chủ nhật": 6
}

def week_anchor(dt: pd.Series, week_start: int) -> pd.Series:
    d = pd.to_datetime(dt)
    return (d - pd.to_timedelta((d.dt.weekday - week_start) % 7, unit="D")).dt.normalize()

def label_from_time(time_s: pd.Series, grain: str) -> pd.Series:
    t = pd.to_datetime(time_s)
    if grain == "Ngày":
        return t.dt.strftime("%Y-%m-%d")
    if grain == "Tuần":
        iso = t.dt.isocalendar()
        return "Tuần " + iso["week"].astype(str).str.zfill(2) + "/" + iso["year"].astype(str)
    if grain == "Tháng":
        return t.dt.to_period("M").astype(str)
    return t.dt.to_period("Q").astype(str)

# =====================================================
# FILTER HELPER
# =====================================================
REV = "rev_"

def reset_by_prefix(prefix: str):
    for k in list(st.session_state.keys()):
        if k.startswith(prefix):
            st.session_state.pop(k, None)
    st.rerun()

def ms_all(key: str, label: str, options, all_label="All", default_all=True):
    opts = pd.Series(list(options)).dropna().astype(str).str.strip()
    opts = sorted(opts.unique().tolist())
    ui_opts = [all_label] + opts

    if key not in st.session_state:
        st.session_state[key] = [all_label] if default_all else (opts[:1] if opts else [all_label])

    cur = [str(x).strip() for x in st.session_state.get(key, []) if str(x).strip() in ui_opts]
    if not cur:
        cur = [all_label] if default_all else (opts[:1] if opts else [all_label])
        st.session_state[key] = cur

    selected = st.multiselect(label, options=ui_opts, key=key)

    if (not selected) or (all_label in selected):
        return opts
    return [x for x in selected if x in opts]

# =====================================================
# PAGE
# =====================================================
st.set_page_config(page_title="📈 Báo cáo Doanh thu", layout="wide")
st.title("📈 Báo cáo Doanh thu")

df = load_data()

if df is None or df.empty:
    st.warning("⚠ Không có dữ liệu để phân tích.")
    st.stop()

st.sidebar.caption(f"RAM df ~ {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")

# =====================================================
# SIDEBAR FILTER
# =====================================================
with st.sidebar:
    st.header("🎛 Bộ lọc dữ liệu")

    if st.button("🔄 Reset bộ lọc (Revenue)", use_container_width=True):
        reset_by_prefix(REV)

    time_grain = st.selectbox(
        "Phân tích theo",
        ["Ngày", "Tuần", "Tháng", "Quý"],
        key=REV + "time_grain",
    )

    if time_grain == "Tuần":
        rev_week_label = st.selectbox(
            "Tuần bắt đầu từ thứ",
            list(WEEKDAY_MAP.keys()),
            key=REV + "week_start",
        )
        REV_WEEK_START = WEEKDAY_MAP[rev_week_label]
    else:
        REV_WEEK_START = 0

    if REV + "start_date" not in st.session_state:
        st.session_state[REV + "start_date"] = df["Ngày"].min().date()
    if REV + "end_date" not in st.session_state:
        st.session_state[REV + "end_date"] = df["Ngày"].max().date()

    start_date = st.date_input("Từ ngày", key=REV + "start_date")
    end_date = st.date_input("Đến ngày", key=REV + "end_date")

    loaict_filter = ms_all(
        key=REV + "loaict",
        label="Loại CT",
        options=df["LoaiCT"] if "LoaiCT" in df.columns else [],
    )

    region_filter = ms_all(
        key=REV + "region",
        label="Region",
        options=df["Region"] if "Region" in df.columns else [],
    )

    df_r = df[df["Region"].astype(str).isin(region_filter)] if ("Region" in df.columns and region_filter) else df

    store_filter = ms_all(
        key=REV + "store",
        label="Điểm mua hàng",
        options=df_r["Điểm_mua_hàng"] if "Điểm_mua_hàng" in df_r.columns else [],
    )

# =====================================================
# APPLY FILTER
# =====================================================
df_f = df[
    (df["Ngày"] >= pd.to_datetime(start_date)) &
    (df["Ngày"] <= pd.to_datetime(end_date))
].copy()

if "LoaiCT" in df_f.columns and loaict_filter:
    df_f = df_f[df_f["LoaiCT"].astype(str).isin(loaict_filter)]

if "Region" in df_f.columns and region_filter:
    df_f = df_f[df_f["Region"].astype(str).isin(region_filter)]

if "Điểm_mua_hàng" in df_f.columns and store_filter:
    df_f = df_f[df_f["Điểm_mua_hàng"].astype(str).isin(store_filter)]

if df_f.empty:
    st.warning("⚠ Không có dữ liệu sau khi áp bộ lọc.")
    st.stop()

# =====================================================
# ADD TIME + LABEL
# =====================================================
if time_grain == "Ngày":
    df_f["Time"] = df_f["Ngày"].dt.normalize()
elif time_grain == "Tuần":
    df_f["Time"] = week_anchor(df_f["Ngày"], REV_WEEK_START)
elif time_grain == "Tháng":
    df_f["Time"] = df_f["Ngày"].dt.to_period("M").dt.to_timestamp()
else:
    df_f["Time"] = df_f["Ngày"].dt.to_period("Q").dt.to_timestamp()

df_f["Label"] = label_from_time(df_f["Time"], time_grain)

# =====================================================
# BUILD SUMMARY
# =====================================================
summary = (
    df_f.groupby(["Time"], observed=True)
    .agg(
        Label=("Label", "first"),
        Tổng_Gross=("Tổng_Gross", "sum"),
        Tổng_Net=("Tổng_Net", "sum"),
        Số_đơn_hàng=("Số_CT", "nunique"),
    )
    .reset_index()
    .sort_values("Time")
)

summary["Tỷ_lệ_CK (%)"] = np.where(
    summary["Tổng_Gross"] != 0,
    (1 - summary["Tổng_Net"] / summary["Tổng_Gross"]) * 100,
    0,
)
summary["Change Net%"] = summary["Tổng_Net"].pct_change() * 100
summary["Change Gross%"] = summary["Tổng_Gross"].pct_change() * 100
summary["Change ĐH%"] = summary["Số_đơn_hàng"].pct_change() * 100
summary["AOV"] = np.where(
    summary["Số_đơn_hàng"] > 0,
    summary["Tổng_Net"] / summary["Số_đơn_hàng"],
    np.nan,
)

# =====================================================
# SUMMARY DISPLAY
# =====================================================
st.subheader("📊 Tổng hợp doanh thu")

summary_show = summary.copy()

for c in ["Tổng_Gross", "Tổng_Net", "Số_đơn_hàng", "AOV"]:
    if c in summary_show.columns:
        summary_show[c] = summary_show[c].apply(fmt_int)

if "Tỷ_lệ_CK (%)" in summary_show.columns:
    summary_show["Tỷ_lệ_CK (%)"] = summary_show["Tỷ_lệ_CK (%)"].apply(lambda v: fmt_pct(v, 2))

for c in ["Change Gross%", "Change Net%", "Change ĐH%"]:
    if c in summary_show.columns:
        summary_show[c] = summary_show[c].apply(lambda v: fmt_pct(v, 2, with_sign=True))

st.dataframe(
    summary_show[
        [
            "Label",
            "Tổng_Gross",
            "Tổng_Net",
            "Số_đơn_hàng",
            "AOV",
            "Tỷ_lệ_CK (%)",
            "Change Gross%",
            "Change Net%",
            "Change ĐH%",
        ]
    ].rename(columns={"Label": "Kỳ"}),
    use_container_width=True,
    hide_index=True
)

fig = px.line(
    summary,
    x="Time",
    y=["Tổng_Gross", "Tổng_Net"],
    markers=True,
    title=f"Doanh thu theo {time_grain}",
)
st.plotly_chart(fig, use_container_width=True)

show_aov_chart = st.checkbox("Hiện chart AOV", value=False)
if show_aov_chart:
    fig2 = px.line(
        summary,
        x="Time",
        y="AOV",
        markers=True,
        title="AOV theo thời gian"
    )
    st.plotly_chart(fig2, use_container_width=True)

# =====================================================
# REGION
# =====================================================
st.subheader("🌍 Theo Region")

if "Region" not in df_f.columns:
    st.info("Thiếu cột Region hoặc không có dữ liệu.")
else:
    reg = (
        df_f.groupby(["Region", "Time"], observed=True)
        .agg(
            Label=("Label", "first"),
            Tổng_Gross=("Tổng_Gross", "sum"),
            Tổng_Net=("Tổng_Net", "sum"),
            Số_đơn_hàng=("Số_CT", "nunique"),
        )
        .reset_index()
        .sort_values(["Region", "Time"])
    )

    reg["Tỷ_lệ_CK (%)"] = np.where(
        reg["Tổng_Gross"] != 0,
        (1 - reg["Tổng_Net"] / reg["Tổng_Gross"]) * 100,
        0,
    )
    reg["Change Net%"] = reg.groupby("Region")["Tổng_Net"].pct_change() * 100
    reg["Change Gross%"] = reg.groupby("Region")["Tổng_Gross"].pct_change() * 100
    reg["Change ĐH%"] = reg.groupby("Region")["Số_đơn_hàng"].pct_change() * 100
    reg["AOV"] = np.where(
        reg["Số_đơn_hàng"] > 0,
        reg["Tổng_Net"] / reg["Số_đơn_hàng"],
        np.nan,
    )

    periods = summary["Label"].tolist()
    sel_period = st.selectbox(
        "Chọn kỳ",
        periods,
        index=len(periods) - 1,
        key=REV + "region_period"
    )

    reg_view = reg[reg["Label"] == sel_period].sort_values("Tổng_Net", ascending=False).copy()

    reg_show = reg_view[
        [
            "Label",
            "Region",
            "Tổng_Gross",
            "Tổng_Net",
            "Số_đơn_hàng",
            "AOV",
            "Tỷ_lệ_CK (%)",
            "Change Gross%",
            "Change Net%",
            "Change ĐH%",
        ]
    ].rename(columns={"Label": "Kỳ"}).copy()

    for c in ["Tổng_Gross", "Tổng_Net", "Số_đơn_hàng", "AOV"]:
        if c in reg_show.columns:
            reg_show[c] = reg_show[c].apply(fmt_int)

    if "Tỷ_lệ_CK (%)" in reg_show.columns:
        reg_show["Tỷ_lệ_CK (%)"] = reg_show["Tỷ_lệ_CK (%)"].apply(lambda v: fmt_pct(v, 2))

    for c in ["Change Gross%", "Change Net%", "Change ĐH%"]:
        if c in reg_show.columns:
            reg_show[c] = reg_show[c].apply(lambda v: fmt_pct(v, 2, with_sign=True))

    st.dataframe(reg_show, use_container_width=True, hide_index=True)

# =====================================================
# TOP / BOTTOM 10 STORE
# =====================================================
st.subheader("🏪 Top / Bottom 10")

if "Điểm_mua_hàng" not in df_f.columns:
    st.info("Thiếu cột Điểm_mua_hàng hoặc không có dữ liệu.")
else:
    store = (
        df_f.groupby(["Điểm_mua_hàng", "Time"], observed=True)
        .agg(
            Label=("Label", "first"),
            Tổng_Gross=("Tổng_Gross", "sum"),
            Tổng_Net=("Tổng_Net", "sum"),
            Số_đơn_hàng=("Số_CT", "nunique"),
        )
        .reset_index()
        .sort_values(["Điểm_mua_hàng", "Time"])
    )

    store["Tỷ_lệ_CK (%)"] = np.where(
        store["Tổng_Gross"] != 0,
        (1 - store["Tổng_Net"] / store["Tổng_Gross"]) * 100,
        0,
    )
    store["Change Net%"] = store.groupby("Điểm_mua_hàng")["Tổng_Net"].pct_change() * 100
    store["Change Gross%"] = store.groupby("Điểm_mua_hàng")["Tổng_Gross"].pct_change() * 100
    store["Change ĐH%"] = store.groupby("Điểm_mua_hàng")["Số_đơn_hàng"].pct_change() * 100
    store["AOV"] = np.where(
        store["Số_đơn_hàng"] > 0,
        store["Tổng_Net"] / store["Số_đơn_hàng"],
        np.nan,
    )

    if "Region" in df_f.columns:
        store_region_map = (
            df_f[["Label", "Điểm_mua_hàng", "Region"]]
            .dropna()
            .groupby(["Label", "Điểm_mua_hàng"])["Region"]
            .agg(lambda x: x.value_counts().index[0])
            .reset_index()
        )
    else:
        store_region_map = pd.DataFrame(columns=["Label", "Điểm_mua_hàng", "Region"])

    periods2 = summary["Label"].tolist()
    sel_period2 = st.selectbox(
        "Chọn kỳ (Top/Bottom)",
        periods2,
        index=len(periods2) - 1,
        key=REV + "store_period",
    )

    s_view = store[store["Label"] == sel_period2].copy()

    if not store_region_map.empty:
        mode_map = store_region_map[store_region_map["Label"] == sel_period2].copy()
        s_view = s_view.merge(mode_map[["Điểm_mua_hàng", "Region"]], on="Điểm_mua_hàng", how="left")
    else:
        s_view["Region"] = np.nan

    region_opts = sorted([r for r in s_view["Region"].dropna().astype(str).unique().tolist()])
    region_ui = ["All"] + region_opts

    if REV + "tb_region" not in st.session_state:
        st.session_state[REV + "tb_region"] = "All"

    sel_r = st.selectbox(
        "Lọc Region (Top/Bottom)",
        region_ui,
        index=region_ui.index(st.session_state[REV + "tb_region"])
        if st.session_state[REV + "tb_region"] in region_ui else 0,
        key=REV + "tb_region",
    )

    if sel_r != "All":
        s_view = s_view[s_view["Region"].astype(str) == sel_r].copy()

    if s_view.empty:
        st.info("Không có dữ liệu Top/Bottom theo lựa chọn hiện tại.")
        st.stop()

    top10 = s_view.sort_values("Tổng_Net", ascending=False).head(10).copy()
    bottom10 = s_view.sort_values("Tổng_Net", ascending=True).head(10).copy()

    def _fmt_store(df_in: pd.DataFrame) -> pd.DataFrame:
        cols = [
            "Label",
            "Điểm_mua_hàng",
            "Tổng_Gross",
            "Tổng_Net",
            "Số_đơn_hàng",
            "AOV",
            "Tỷ_lệ_CK (%)",
            "Change Gross%",
            "Change Net%",
            "Change ĐH%",
        ]

        if "Region" in df_in.columns:
            cols.insert(2, "Region")

        cols = [c for c in cols if c in df_in.columns]

        out = df_in[cols].rename(columns={"Label": "Kỳ"}).copy()

        for c in ["Tổng_Gross", "Tổng_Net", "Số_đơn_hàng", "AOV"]:
            if c in out.columns:
                out[c] = out[c].apply(fmt_int)

        if "Tỷ_lệ_CK (%)" in out.columns:
            out["Tỷ_lệ_CK (%)"] = out["Tỷ_lệ_CK (%)"].apply(lambda v: fmt_pct(v, 2))

        for c in ["Change Gross%", "Change Net%", "Change ĐH%"]:
            if c in out.columns:
                out[c] = out[c].apply(lambda v: fmt_pct(v, 2, with_sign=True))

        return out

    colA, colB = st.columns(2)
    with colA:
        st.markdown("### 🏆 Top 10 Điểm mua hàng")
        st.dataframe(_fmt_store(top10), use_container_width=True, hide_index=True)
    with colB:
        st.markdown("### 📉 Bottom 10 Điểm mua hàng")
        st.dataframe(_fmt_store(bottom10), use_container_width=True, hide_index=True)