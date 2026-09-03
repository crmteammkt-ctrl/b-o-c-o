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

def fmt_signed_int(x):
    """Format a number with explicit + sign for positive values, e.g. +8,000 / -27,600."""
    if pd.isna(x):
        return ""
    try:
        v = float(x)
        sign = "+" if v > 0 else ""
        return sign + fmt_int(v)
    except Exception:
        return ""

# =====================================================
# LOAD DATA (đã tối ưu RAM)
# =====================================================
# Cùng nguyên tắc như 00_general.py:
# - Số_CT chỉ dùng để đếm nunique() trong toàn bộ file này -> factorize
#   thành int32 thay vì category (Số_CT có cardinality cao ~57%, category
#   không tiết kiệm được nhiều, có khi còn tốn hơn do overhead dictionary).
# - Tổng_Gross / Tổng_Net GIỮ float64 (đã test: float32 làm sai tổng tiền).
# - Region, Điểm_mua_hàng, LoaiCT: category hoá (cardinality thấp).
@st.cache_data(show_spinner=False, max_entries=3, ttl=3600)
def load_data():
    want_cols = ["Ngày", "LoaiCT", "Region", "Điểm_mua_hàng", "Tổng_Gross", "Tổng_Net", "Số_CT"]

    try:
        import pyarrow.parquet as pq
        existing_cols = set(pq.ParquetFile("data/revenue.parquet").schema.names)
        read_cols = [c for c in want_cols if c in existing_cols]
    except Exception:
        read_cols = None

    df = pd.read_parquet("data/revenue.parquet", columns=read_cols)

    if df is None or df.empty:
        return df

    if "Ngày" in df.columns:
        df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce")
        df = df.dropna(subset=["Ngày"])

    for c in ["Tổng_Gross", "Tổng_Net"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    if "Số_CT" in df.columns:
        codes, _ = pd.factorize(df["Số_CT"])
        df["Số_CT"] = codes.astype("int32")

    for c in ["LoaiCT", "Region", "Điểm_mua_hàng"]:
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
# Thay đổi: bỏ df_r = df[...] (full-copy) để lấy option cho store filter.
# Dùng boolean mask + .loc lấy đúng 1 cột thay vì copy cả dataframe.
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

    region_mask = (
        df["Region"].astype(str).isin(region_filter)
        if ("Region" in df.columns and region_filter)
        else pd.Series(True, index=df.index)
    )

    store_filter = ms_all(
        key=REV + "store",
        label="Điểm mua hàng",
        options=df.loc[region_mask, "Điểm_mua_hàng"] if "Điểm_mua_hàng" in df.columns else [],
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

    # Net Impact = Net kỳ hiện tại - Net kỳ trước (chênh lệch tuyệt đối bằng tiền).
    # Khác với Change Net% (biến động tương đối), Impact cho biết cửa hàng
    # thực tế làm tăng/giảm bao nhiêu tiền Net so với kỳ trước.
    store["Net Impact"] = store.groupby("Điểm_mua_hàng")["Tổng_Net"].diff()

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

    # =====================================================
    # BIẾN ĐỘNG THEO CỬA HÀNG (TORNADO CHART)
    # Dùng chung bộ lọc kỳ + region của phần Top/Bottom (s_view)
    # =====================================================
    st.markdown(f"### 📊 Biến động theo cửa hàng — {sel_period2}")

    metric_options = {
        "Net": "Change Net%",
        "Gross": "Change Gross%",
        "Đơn hàng": "Change ĐH%",
    }

    sel_metric_label = st.selectbox(
        "Chọn chỉ số biến động",
        list(metric_options.keys()),
        key=REV + "tb_change_metric",
    )
    sel_metric_col = metric_options[sel_metric_label]

    chart_data = s_view.dropna(subset=[sel_metric_col]).copy()

    if chart_data.empty:
        st.info("Không có dữ liệu biến động cho kỳ này (kỳ đầu tiên không có kỳ trước để so sánh).")
    else:
        chart_data = chart_data.sort_values(sel_metric_col, ascending=True)

        fig_change = px.bar(
            chart_data,
            x=sel_metric_col,
            y="Điểm_mua_hàng",
            orientation="h",
            text=chart_data[sel_metric_col].apply(lambda v: fmt_pct(v, 2, with_sign=True)),
        )

        colors = np.where(chart_data[sel_metric_col] >= 0, "#2ECC71", "#5B9BF0")
        fig_change.update_traces(marker_color=colors, textposition="outside")
        fig_change.update_layout(
            xaxis_title=None,
            yaxis_title=None,
            yaxis=dict(
                categoryorder="array",
                categoryarray=chart_data["Điểm_mua_hàng"].tolist(),
            ),
            height=max(300, len(chart_data) * 35),
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig_change, use_container_width=True)

    # =====================================================
    # FORMAT HELPER FOR STORE TABLES
    # =====================================================
    def _fmt_store(df_in: pd.DataFrame, include_impact: bool = True) -> pd.DataFrame:
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
            "Net Impact",
            "Change ĐH%",
        ]

        if not include_impact:
            cols = [c for c in cols if c != "Net Impact"]

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

        if "Net Impact" in out.columns:
            out["Net Impact"] = out["Net Impact"].apply(fmt_signed_int)

        return out

    st.caption(
        "💡 Net Impact = Tổng_Net kỳ đang chọn − Tổng_Net kỳ trước. "
        "Chỉ số này cho biết cửa hàng thực tế đóng góp/tổn thất bao nhiêu tiền Net, "
        "không chỉ nhìn % tăng giảm."
    )

    # -----------------------------------------------------
    # Top / Bottom theo DOANH THU (Tổng_Net hiện tại)
    # -----------------------------------------------------
    top10 = s_view.sort_values("Tổng_Net", ascending=False).head(10).copy()
    bottom10 = s_view.sort_values("Tổng_Net", ascending=True).head(10).copy()

    colA, colB = st.columns(2)
    with colA:
        st.markdown("### 🏆 Top 10 Điểm mua hàng (theo doanh thu)")
        st.dataframe(_fmt_store(top10), use_container_width=True, hide_index=True)
    with colB:
        st.markdown("### 📉 Bottom 10 Điểm mua hàng (theo doanh thu)")
        st.dataframe(_fmt_store(bottom10), use_container_width=True, hide_index=True)

    # -----------------------------------------------------
    # Top / Bottom theo NET IMPACT (cửa hàng tăng/giảm nhiều tiền nhất)
    # -----------------------------------------------------
    st.markdown("### 🎯 Top 10 Impact — cửa hàng ảnh hưởng lớn nhất đến kết quả kỳ này")
    st.caption(
        "Xếp theo Net Impact (chênh lệch Net tuyệt đối so với kỳ trước), "
        "không phải theo quy mô doanh thu — giúp thấy đúng cửa hàng nào đang "
        "kéo tăng/giảm kết quả chung, bất kể cửa hàng lớn hay nhỏ."
    )

    impact_view = s_view.dropna(subset=["Net Impact"]).copy()

    if impact_view.empty:
        st.info(
            "Không có dữ liệu Net Impact cho kỳ này "
            "(kỳ đầu tiên không có kỳ trước để so sánh)."
        )
    else:
        top10_impact = impact_view.sort_values("Net Impact", ascending=False).head(10).copy()
        bottom10_impact = impact_view.sort_values("Net Impact", ascending=True).head(10).copy()

        colC, colD = st.columns(2)
        with colC:
            st.markdown("### 🟢 Top 10 Positive Impact")
            st.dataframe(_fmt_store(top10_impact), use_container_width=True, hide_index=True)
        with colD:
            st.markdown("### 🔴 Top 10 Negative Impact")
            st.dataframe(_fmt_store(bottom10_impact), use_container_width=True, hide_index=True)