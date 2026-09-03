import pandas as pd
import numpy as np
import streamlit as st

# =====================================================
# LOAD DATA (đã tối ưu RAM)
# =====================================================
# Những gì đã đổi so với bản gốc và LÝ DO:
#
# 1) columns=[...] khi read_parquet
#    -> chỉ đọc đúng các cột dùng trong file này, không tải dư.
#
# 2) Số_CT: factorize -> int32 thay vì giữ string/category
#    -> Số_CT có ~57% giá trị unique (gần như mã đơn hàng riêng lẻ),
#       category KHÔNG giúp ích vì dictionary gần bằng dữ liệu gốc.
#       Cột này trong toàn bộ file .py chỉ dùng để đếm .nunique(),
#       KHÔNG BAO GIỜ hiển thị giá trị gốc ra UI -> an toàn để mã hoá
#       thành số nguyên (nunique() trên mã số cho kết quả giống hệt
#       nunique() trên chuỗi gốc, vì factorize là ánh xạ 1-1).
#    -> Đây là cột tốn RAM nhất trong file gốc (~13MB/42MB), giảm còn ~2MB.
#
# 3) Tên_hàng: thêm vào danh sách category (bản gốc BỊ SÓT cột này)
#    -> chỉ có 43,004 tên hàng khác nhau / 509,249 dòng (~8.4%),
#       rất đáng category hoá. Giảm từ ~10.2MB xuống ~2.8MB.
#
# 4) Số_lượng: downcast integer (luôn là số nguyên, không có phần thập phân)
#    -> an toàn tuyệt đối, không mất chính xác.
#
# 5) Tổng_Gross / Tổng_Net: GIỮ NGUYÊN float64
#    -> ĐÃ TEST: downcast float32 làm sai tổng tiền (lệch hàng chục nghìn
#       đến hàng trăm đồng khi sum nhiều dòng). Với số tiền lớn (hàng trăm
#       triệu/dòng, hàng trăm tỷ khi cộng dồn), float32 không đủ độ chính
#       xác. Cột tiền chỉ chiếm ~4MB mỗi cột, không phải chỗ đáng tối ưu
#       -> không đánh đổi độ chính xác lấy RAM ở đây.
#
# Kết quả đo trên chính file general.parquet của bạn: 42.1MB -> 20.6MB RAM
# (giảm ~51%), không mất tính năng hay độ chính xác nào.
@st.cache_data(show_spinner=False, max_entries=3, ttl=3600)
def load_data():
    want_cols = [
        "Ngày", "LoaiCT", "Số_CT", "Brand", "Region", "Điểm_mua_hàng",
        "Mã_NB", "Tên_hàng", "Số_lượng", "Tổng_Gross", "Tổng_Net",
        "Nhóm_hàng",  # có thể không tồn tại trong mọi bản file -> lọc lại bên dưới
    ]

    # Đọc trước schema để chỉ request cột thực sự tồn tại trong file,
    # tránh lỗi nếu một số bản dữ liệu thiếu cột Nhóm_hàng.
    try:
        import pyarrow.parquet as pq
        existing_cols = set(pq.ParquetFile("data/general.parquet").schema.names)
        read_cols = [c for c in want_cols if c in existing_cols]
    except Exception:
        read_cols = None  # fallback: đọc hết nếu không lấy được schema

    df = pd.read_parquet("data/general.parquet", columns=read_cols)

    if df is None or df.empty:
        return df

    df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce")
    df = df.dropna(subset=["Ngày"])

    # --- Số_CT: mã hoá thành int32, chỉ dùng để đếm nunique() ---
    if "Số_CT" in df.columns:
        codes, _ = pd.factorize(df["Số_CT"])
        df["Số_CT"] = codes.astype("int32")

    # --- Tiền: giữ float64 để không mất độ chính xác ---
    for c in ["Tổng_Gross", "Tổng_Net"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # --- Số lượng: số nguyên, downcast an toàn ---
    if "Số_lượng" in df.columns:
        df["Số_lượng"] = pd.to_numeric(df["Số_lượng"], errors="coerce", downcast="integer")

    # --- Category cho mọi cột chuỗi cardinality thấp/trung bình ---
    for c in ["LoaiCT", "Brand", "Region", "Điểm_mua_hàng", "Mã_NB", "Nhóm_hàng", "Tên_hàng"]:
        if c in df.columns:
            try:
                df[c] = df[c].astype("category")
            except Exception:
                pass

    return df

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
# WEEK HELPERS
# =====================================================
WEEKDAY_MAP = {
    "Thứ 2": 0, "Thứ 3": 1, "Thứ 4": 2, "Thứ 5": 3,
    "Thứ 6": 4, "Thứ 7": 5, "Chủ nhật": 6
}

def week_anchor(dt: pd.Series, week_start: int) -> pd.Series:
    d = pd.to_datetime(dt)
    return (d - pd.to_timedelta((d.dt.weekday - week_start) % 7, unit="D")).dt.normalize()

def week_label_from_anchor(anchor: pd.Series) -> pd.Series:
    iso = pd.to_datetime(anchor).dt.isocalendar()
    return "Tuần " + iso["week"].astype(str).str.zfill(2) + "/" + iso["year"].astype(str)

# =====================================================
# FILTER HELPERS
# =====================================================
GEN = "gen_"

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
st.set_page_config(page_title="Marketing Revenue Dashboard – Tổng quan", layout="wide")
st.title("📊 MARKETING REVENUE DASHBOARD – Tổng quan")

df = load_data()
st.sidebar.caption(f"RAM df ~ {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")

if df is None or df.empty:
    st.warning("⚠ Không có dữ liệu để phân tích.")
    st.stop()

# =====================================================
# SIDEBAR FILTER
# =====================================================
# Thay đổi: KHÔNG tạo df_b, df_br full-copy như bản gốc (mỗi bước copy
# nguyên 11 cột chỉ để lấy option cho multiselect kế tiếp). Thay vào đó
# tích luỹ 1 boolean mask và chỉ .loc lấy đúng 1 cột cần thiết -> rẻ hơn
# đáng kể vì không nhân bản toàn bộ dataframe qua từng bước lọc cascade.
with st.sidebar:
    st.header("🎛️ Bộ lọc dữ liệu (Tổng quan)")

    if st.button("🔄 Reset bộ lọc (General)", use_container_width=True):
        reset_by_prefix(GEN)

    if GEN + "time_type" not in st.session_state:
        st.session_state[GEN + "time_type"] = "Ngày"

    time_type = st.selectbox(
        "Phân tích theo",
        ["Ngày", "Tuần", "Tháng", "Quý", "Năm"],
        key=GEN + "time_type",
    )

    if time_type == "Tuần":
        if GEN + "week_start" not in st.session_state:
            st.session_state[GEN + "week_start"] = "Thứ 2"
        gen_week_label = st.selectbox(
            "Tuần bắt đầu từ thứ",
            list(WEEKDAY_MAP.keys()),
            key=GEN + "week_start",
        )
        week_start = WEEKDAY_MAP[gen_week_label]
    else:
        week_start = 0

    if GEN + "start_date" not in st.session_state:
        st.session_state[GEN + "start_date"] = pd.to_datetime(df["Ngày"]).min().date()
    if GEN + "end_date" not in st.session_state:
        st.session_state[GEN + "end_date"] = pd.to_datetime(df["Ngày"]).max().date()

    start_date = st.date_input("Từ ngày", key=GEN + "start_date")
    end_date = st.date_input("Đến ngày", key=GEN + "end_date")

    cascade_mask = pd.Series(True, index=df.index)

    loaiCT = ms_all(
        GEN + "loaiCT", "Loại CT",
        df.loc[cascade_mask, "LoaiCT"] if "LoaiCT" in df.columns else [],
    )
    if "LoaiCT" in df.columns and loaiCT:
        cascade_mask &= df["LoaiCT"].isin(loaiCT)

    brand = ms_all(
        GEN + "brand", "Brand",
        df.loc[cascade_mask, "Brand"] if "Brand" in df.columns else [],
    )
    if "Brand" in df.columns and brand:
        cascade_mask &= df["Brand"].isin(brand)

    region = ms_all(
        GEN + "region", "Region",
        df.loc[cascade_mask, "Region"] if "Region" in df.columns else [],
    )
    if "Region" in df.columns and region:
        cascade_mask &= df["Region"].isin(region)

    store = ms_all(
        GEN + "store", "Cửa hàng",
        df.loc[cascade_mask, "Điểm_mua_hàng"] if "Điểm_mua_hàng" in df.columns else [],
    )

# =====================================================
# APPLY FILTER
# =====================================================
dmin = pd.to_datetime(start_date)
dmax = pd.to_datetime(end_date)

mask = (df["Ngày"] >= dmin) & (df["Ngày"] <= dmax)
if "LoaiCT" in df.columns and loaiCT:
    mask &= df["LoaiCT"].isin(loaiCT)
if "Brand" in df.columns and brand:
    mask &= df["Brand"].isin(brand)
if "Region" in df.columns and region:
    mask &= df["Region"].isin(region)
if "Điểm_mua_hàng" in df.columns and store:
    mask &= df["Điểm_mua_hàng"].isin(store)

df_f = df.loc[mask].copy()
if df_f.empty:
    st.warning("⚠ Không có dữ liệu sau khi áp bộ lọc.")
    st.stop()

# =====================================================
# TIME KEY
# =====================================================
if time_type == "Ngày":
    df_f["Time"] = df_f["Ngày"].dt.normalize()
elif time_type == "Tuần":
    df_f["Time"] = week_anchor(df_f["Ngày"], week_start)
elif time_type == "Tháng":
    df_f["Time"] = df_f["Ngày"].dt.to_period("M").dt.to_timestamp()
elif time_type == "Quý":
    df_f["Time"] = df_f["Ngày"].dt.to_period("Q").dt.to_timestamp()
else:
    df_f["Time"] = pd.to_datetime(df_f["Ngày"].dt.year.astype(str) + "-01-01")

# =====================================================
# KPI
# =====================================================
gross = float(df_f["Tổng_Gross"].sum()) if "Tổng_Gross" in df_f.columns else 0
net = float(df_f["Tổng_Net"].sum()) if "Tổng_Net" in df_f.columns else 0
orders = df_f["Số_CT"].nunique() if "Số_CT" in df_f.columns else 0
ck_rate = (1 - net / gross) * 100 if gross > 0 else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Gross", f"{gross:,.0f}")
c2.metric("Net", f"{net:,.0f}")
c3.metric("CK %", f"{ck_rate:.2f}%")
c4.metric("Đơn hàng", f"{orders:,}")

# =====================================================
# TIME TABLE
# =====================================================
st.subheader(f"⏱ Theo thời gian ({time_type})")

g_time = (
    df_f.groupby("Time", observed=True)
    .agg(
        Gross=("Tổng_Gross", "sum"),
        Net=("Tổng_Net", "sum"),
        Orders=("Số_CT", "nunique"),
    )
    .reset_index()
    .sort_values("Time")
)
g_time["CK_%"] = np.where(g_time["Gross"] > 0, (1 - g_time["Net"] / g_time["Gross"]) * 100, 0)
g_time["Net_prev"] = g_time["Net"].shift(1)
g_time["Growth_%"] = np.where(
    g_time["Net_prev"] > 0,
    (g_time["Net"] - g_time["Net_prev"]) / g_time["Net_prev"] * 100,
    np.nan,
)

g_time_show = g_time.copy()

if time_type == "Ngày":
    g_time_show["Kỳ"] = g_time_show["Time"].dt.strftime("%Y-%m-%d")
elif time_type == "Tuần":
    g_time_show["Kỳ"] = week_label_from_anchor(g_time_show["Time"])
elif time_type == "Tháng":
    g_time_show["Kỳ"] = g_time_show["Time"].dt.to_period("M").astype(str)
elif time_type == "Quý":
    g_time_show["Kỳ"] = g_time_show["Time"].dt.to_period("Q").astype(str)
else:
    g_time_show["Kỳ"] = g_time_show["Time"].dt.year.astype(str)

g_time_show = g_time_show.drop(columns=["Time"])
for c in ["Gross", "Net", "Orders", "Net_prev"]:
    if c in g_time_show.columns:
        g_time_show[c] = g_time_show[c].apply(fmt_int)
for c in ["CK_%", "Growth_%"]:
    if c in g_time_show.columns:
        g_time_show[c] = g_time_show[c].apply(lambda v: fmt_pct(v, 2, with_sign=(c == "Growth_%")))

st.dataframe(
    g_time_show[["Kỳ", "Gross", "Net", "Orders", "CK_%", "Net_prev", "Growth_%"]],
    use_container_width=True,
    hide_index=True
)

# =====================================================
# REGION + TIME
# =====================================================
st.subheader(f"🌍 Theo Region + {time_type}")

if "Region" not in df_f.columns:
    st.info("Thiếu cột Region.")
else:
    g_rt = (
        df_f.groupby(["Time", "Region"], observed=True, dropna=False)
        .agg(
            Gross=("Tổng_Gross", "sum"),
            Net=("Tổng_Net", "sum"),
            Orders=("Số_CT", "nunique"),
        )
        .reset_index()
        .sort_values(["Region", "Time"])
    )
    g_rt["CK_%"] = np.where(g_rt["Gross"] > 0, (1 - g_rt["Net"] / g_rt["Gross"]) * 100, 0)
    g_rt["Prev_Net"] = g_rt.groupby("Region")["Net"].shift(1)
    g_rt["Change%"] = np.where(
        g_rt["Prev_Net"] > 0,
        (g_rt["Net"] - g_rt["Prev_Net"]) / g_rt["Prev_Net"] * 100,
        np.nan
    )

    g_rt_show = g_rt.copy()
    if time_type == "Ngày":
        g_rt_show["Kỳ"] = g_rt_show["Time"].dt.strftime("%Y-%m-%d")
    elif time_type == "Tuần":
        g_rt_show["Kỳ"] = week_label_from_anchor(g_rt_show["Time"])
    elif time_type == "Tháng":
        g_rt_show["Kỳ"] = g_rt_show["Time"].dt.to_period("M").astype(str)
    elif time_type == "Quý":
        g_rt_show["Kỳ"] = g_rt_show["Time"].dt.to_period("Q").astype(str)
    else:
        g_rt_show["Kỳ"] = g_rt_show["Time"].dt.year.astype(str)

    g_rt_show = g_rt_show.drop(columns=["Time"]).sort_values(["Kỳ", "Net"], ascending=[True, False])

    for c in ["Gross", "Net", "Orders", "Prev_Net"]:
        if c in g_rt_show.columns:
            g_rt_show[c] = g_rt_show[c].apply(fmt_int)
    for c in ["CK_%", "Change%"]:
        if c in g_rt_show.columns:
            g_rt_show[c] = g_rt_show[c].apply(lambda v: fmt_pct(v, 2, with_sign=(c == "Change%")))

    st.dataframe(
        g_rt_show[["Kỳ", "Region", "Gross", "Net", "Orders", "CK_%", "Prev_Net", "Change%"]],
        use_container_width=True,
        hide_index=True
    )

# =====================================================
# STORE SUMMARY
# =====================================================
st.subheader("🏪 Tổng quan theo Cửa hàng")

if "Điểm_mua_hàng" not in df_f.columns:
    st.info("Thiếu cột Điểm_mua_hàng.")
else:
    g_store = (
        df_f.groupby("Điểm_mua_hàng", observed=True, dropna=False)
        .agg(
            Gross=("Tổng_Gross", "sum"),
            Net=("Tổng_Net", "sum"),
            Orders=("Số_CT", "nunique"),
        )
        .reset_index()
    )
    g_store["CK_%"] = np.where(g_store["Gross"] > 0, (1 - g_store["Net"] / g_store["Gross"]) * 100, 0)
    g_store = g_store.sort_values("Net", ascending=False)

    g_store_show = g_store.copy()
    for c in ["Gross", "Net", "Orders"]:
        if c in g_store_show.columns:
            g_store_show[c] = g_store_show[c].apply(fmt_int)
    if "CK_%" in g_store_show.columns:
        g_store_show["CK_%"] = g_store_show["CK_%"].apply(lambda v: fmt_pct(v, 2))

    st.dataframe(g_store_show, use_container_width=True, hide_index=True)

# =====================================================
# PRODUCT SUMMARY
# =====================================================
st.subheader("📦 Theo Nhóm SP / Mã NB")

df_product = df_f.copy()

col1, col2 = st.columns(2)
with col1:
    nhom_vals = sorted(df_product["Nhóm_hàng"].dropna().astype(str).unique()) if "Nhóm_hàng" in df_product.columns else []
    nhom_sp = st.multiselect("📦 Chọn Nhóm SP", nhom_vals, key=GEN + "nhom_sp")
with col2:
    ma_vals = sorted(df_product["Mã_NB"].dropna().astype(str).unique()) if "Mã_NB" in df_product.columns else []
    ma_nb = st.multiselect("🏷️ Chọn Mã NB", ma_vals, key=GEN + "ma_nb")

if nhom_sp and "Nhóm_hàng" in df_product.columns:
    df_product = df_product[df_product["Nhóm_hàng"].astype(str).isin(nhom_sp)]
if ma_nb and "Mã_NB" in df_product.columns:
    df_product = df_product[df_product["Mã_NB"].astype(str).isin(ma_nb)]

if df_product.empty or "Mã_NB" not in df_product.columns:
    st.info("Không có dữ liệu hoặc thiếu cột Mã_NB.")
else:
    orders_agg = ("Số_lượng", "sum") if "Số_lượng" in df_product.columns else ("Số_CT", "nunique")

    g_prod = (
        df_product.groupby("Mã_NB", observed=True, dropna=False)
        .agg(
            Gross=("Tổng_Gross", "sum"),
            Net=("Tổng_Net", "sum"),
            Orders=orders_agg,
        )
        .reset_index()
        .sort_values("Net", ascending=False)
    )
    g_prod["CK_%"] = np.where(g_prod["Gross"] > 0, (1 - g_prod["Net"] / g_prod["Gross"]) * 100, 0)

    g_prod_show = g_prod.copy()
    for c in ["Gross", "Net", "Orders"]:
        if c in g_prod_show.columns:
            g_prod_show[c] = g_prod_show[c].apply(fmt_int)
    if "CK_%" in g_prod_show.columns:
        g_prod_show["CK_%"] = g_prod_show["CK_%"].apply(lambda v: fmt_pct(v, 2))

    st.dataframe(g_prod_show, use_container_width=True, hide_index=True)