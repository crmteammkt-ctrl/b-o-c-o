import os
import sqlite3
import traceback
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

# ================== CONFIG RUNTIME ==================
BASE_DIR = Path("runtime")
BASE_DIR.mkdir(exist_ok=True)

database_path = str(BASE_DIR / "thiensondb.db")
table_name = "data"

PARQUET_OUT_DIR = BASE_DIR / "parquet_data"
PARQUET_OUT_DIR.mkdir(parents=True, exist_ok=True)

FINAL_OUT_DIR = BASE_DIR / "final_parquet"
FINAL_OUT_DIR.mkdir(parents=True, exist_ok=True)

sheet_name = os.environ.get("SHEET_NAME", "data")
DATA_URL = os.environ.get("DATA_URL", "").strip()

if not DATA_URL:
    raise ValueError("Thiếu DATA_URL trong environment variables.")

# ================== CỘT EXCEL & DB ==================
cols_old = [
    "Source.Name","LoaiCT","Ngày","Số CT","Brand","Cửa hàng","Vị trí",
    "Region","Thông tin KH","Kiểm tra tên","Số điện thoại","Check SĐT",
    "Ngày Bán","Giới tính khách hàng","Nhân viên","Thông tin độ tuổi","Mã NB",
    "Tên Hàng","ĐVT","Nhóm Hàng","Chủng Loại","Thương Hiệu","Số Lượng","Giảm Giá Chi Tiết",
    "Đơn Giá","Thành tiền trước CK","Thành Tiền CK","Điểm KH","Hạng Thẻ","Dòng SP.1",
    "Dòng SP.2","Ghi chú","Region.1.Miền","Region.1.Tỉnh/TP"
]

cols_new = [
    "Source","LoaiCT","Ngày","Số_CT","Brand","Cửa_hàng","Vị_trí","Region",
    "Thông_tin_KH","Kiểm_tra_tên","Số_điện_thoại","Check_SĐT","Ngày_bán",
    "Giới_tính_khách_hàng","Nhân_viên","Thông_tin_độ_tuổi","Mã_NB","Tên_hàng",
    "ĐVT","Nhóm_hàng","Chủng_loại","Thương_hiệu","Số_lượng","Giảm_giá_chi_tiết","Đơn_giá",
    "Thành_tiền_trước_CK","Thành_tiền_CK","Điểm_KH","Hạng_thẻ","Dòng_SP1","Dòng_SP2",
    "Ghi_chú","Miền","Tỉnh_TP"
]

mapping = dict(zip(cols_old, cols_new))

# ================== TẠO BẢNG ==================
create_table_sql = f"""
CREATE TABLE IF NOT EXISTS {table_name} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    Source TEXT,
    LoaiCT TEXT,
    Ngày TEXT,
    Số_CT TEXT,
    Brand TEXT,
    Cửa_hàng TEXT,
    Vị_trí TEXT,
    Region TEXT,
    Thông_tin_KH TEXT,
    Kiểm_tra_tên TEXT,
    Số_điện_thoại TEXT,
    Check_SĐT TEXT,
    Ngày_bán TEXT,
    Giới_tính_khách_hàng TEXT,
    Nhân_viên TEXT,
    Thông_tin_độ_tuổi TEXT,
    Mã_NB TEXT,
    Tên_hàng TEXT,
    ĐVT TEXT,
    Nhóm_hàng TEXT,
    Chủng_loại TEXT,
    Thương_hiệu TEXT,
    Số_lượng REAL,
    Giảm_giá_chi_tiết REAL,
    Đơn_giá REAL,
    Thành_tiền_trước_CK REAL,
    Thành_tiền_CK REAL,
    Điểm_KH REAL,
    Hạng_thẻ TEXT,
    Dòng_SP1 TEXT,
    Dòng_SP2 TEXT,
    Ghi_chú TEXT,
    Miền TEXT,
    Tỉnh_TP TEXT
);
"""

# ================== HELPERS ==================
def log(msg: str):
    print(msg, flush=True)

def apply_sqlite_pragmas(conn: sqlite3.Connection):
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-200000;")

def download_source_excel() -> BytesIO:
    log(f"⬇️ Đang tải dữ liệu từ: {DATA_URL[:120]}...")
    resp = requests.get(DATA_URL, timeout=300)
    resp.raise_for_status()
    return BytesIO(resp.content)

def read_excel_data() -> pd.DataFrame:
    bio = download_source_excel()

    df = pd.read_excel(
        bio,
        sheet_name=sheet_name,
        usecols=cols_old,
    )

    df.rename(columns=mapping, inplace=True)

    df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce").dt.date

    df["Ngày_bán"] = pd.to_datetime(df["Ngày_bán"], errors="coerce")
    df["Ngày_bán"] = df["Ngày_bán"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # chuẩn hóa null
    df = df.where(pd.notnull(df), None)

    # bỏ dòng không có ngày
    df = df[df["Ngày"].notna()].copy()

    return df

def export_parquet_by_month(db_path, table="tinhhinhbanhang", out_dir=PARQUET_OUT_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    df = pd.read_sql(f"SELECT * FROM {table}", conn)
    conn.close()

    if df.empty:
        return {"ok": True, "msg": "⚠️ Bảng tinhhinhbanhang không có dữ liệu, không xuất Parquet."}

    df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce")
    df = df.dropna(subset=["Ngày"])

    df["Year"] = df["Ngày"].dt.year
    df["Month"] = df["Ngày"].dt.month

    wrote = 0
    for (y, m), d in df.groupby(["Year", "Month"]):
        folder = out_dir / f"{y}"
        folder.mkdir(exist_ok=True)
        fname = folder / f"{y}-{m:02d}.parquet"
        d.drop(columns=["Year", "Month"]).to_parquet(fname, index=False)
        wrote += 1

    return {"ok": True, "msg": f"✅ Export Parquet theo tháng xong ({wrote} file).", "dir": str(out_dir)}

def export_final_app_parquets(db_path, table="tinhhinhbanhang", out_dir=FINAL_OUT_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    df = pd.read_sql(f"SELECT * FROM {table}", conn)
    conn.close()

    if df.empty:
        raise ValueError("Bảng tinhhinhbanhang không có dữ liệu để export final parquet.")

    # chuẩn hóa hiển thị
    if "Ngày" in df.columns:
        df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce")

    general_cols = [
        "Ngày","LoaiCT","Số_CT","Brand","Region","Điểm_mua_hàng",
        "Mã_NB","Tên_hàng","Nhóm_hàng","Số_lượng","Tổng_Gross","Tổng_Net","Tỷ_lệ_CK"
    ]
    revenue_cols = [
        "Ngày","LoaiCT","Region","Điểm_mua_hàng","Tổng_Gross","Tổng_Net","Số_CT"
    ]
    crm_cols = [
        "Ngày","tên_KH","LoaiCT","Brand","Region","Số_điện_thoại",
        "Số_CT","Điểm_mua_hàng","Kiểm_tra_tên","Trạng_thái_số_điện_thoại",
        "Tổng_Gross","Tổng_Net"
    ]

    def pick(cols):
        return [c for c in cols if c in df.columns]

    df[pick(general_cols)].to_parquet(out_dir / "general.parquet", index=False)
    df[pick(revenue_cols)].to_parquet(out_dir / "revenue.parquet", index=False)
    df[pick(crm_cols)].to_parquet(out_dir / "crm_cohort.parquet", index=False)

    log(f"✅ Export final parquet xong tại: {out_dir}")

# ================== PIPELINE ==================
def run_pipeline():
    log("📖 Đang đọc Excel online...")
    df = read_excel_data()

    if df.empty:
        raise ValueError("Excel không có dữ liệu sau khi đọc.")

    log(f"📥 Tổng số dòng đọc được: {len(df):,}")

    conn = sqlite3.connect(database_path, timeout=120)
    apply_sqlite_pragmas(conn)
    cur = conn.cursor()

    log("🧱 Tạo bảng data...")
    cur.execute(create_table_sql)
    conn.commit()

    # online workflow: luôn rebuild full table cho sạch
    log("🧹 Xóa toàn bộ data cũ...")
    cur.execute(f"DELETE FROM {table_name}")
    conn.commit()

    placeholders = ",".join(["?"] * len(cols_new))
    insert_sql = f"INSERT INTO {table_name} ({','.join(cols_new)}) VALUES ({placeholders})"

    rows_iter = df[cols_new].itertuples(index=False, name=None)

    log("🧱 Insert vào SQLite...")
    conn.execute("BEGIN;")
    cur.executemany(insert_sql, rows_iter)
    conn.commit()

    log("⚡ Tạo index...")
    cur.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_ngay ON {table_name}(Ngày)')
    cur.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_sdt ON {table_name}(Số_điện_thoại)')
    cur.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_soct ON {table_name}(Số_CT)')
    cur.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_manb ON {table_name}(Mã_NB)')
    conn.commit()

    cur.close()
    conn.close()

    log("🧮 Tạo bảng tinhhinhbanhang...")
    conn = sqlite3.connect(database_path)
    apply_sqlite_pragmas(conn)
    cur = conn.cursor()

    query = """
    DROP TABLE IF EXISTS tinhhinhbanhang;

    CREATE TABLE tinhhinhbanhang AS
    SELECT
        Ngày,
        Số_điện_thoại,
        MIN(Check_SĐT) AS Trạng_thái_số_điện_thoại,
        MIN(LoaiCT) AS LoaiCT,
        Số_CT,
        MIN(Brand) AS Brand,
        MIN(Cửa_hàng) AS Điểm_mua_hàng,
        MIN(Region) AS Region,
        MIN(Tỉnh_TP) AS Tỉnh_TP,

        Mã_NB,
        Tên_hàng,
        Chủng_loại,
        Nhóm_hàng,
        Dòng_SP1,

        SUM(COALESCE(Số_lượng, 0)) AS Số_lượng,

        MIN(Thông_tin_KH) AS tên_KH,
        MIN(Kiểm_tra_tên) AS Kiểm_tra_tên,
        MIN(Giới_tính_khách_hàng) AS Giới_tính_khách_hàng,
        MIN(Ghi_chú) AS Ghi_chú,

        SUM(COALESCE(Điểm_KH, 0)) AS Point,
        SUM(COALESCE(Thành_tiền_trước_CK, 0)) AS Tổng_Gross,
        SUM(COALESCE(Thành_tiền_CK, 0)) AS Tổng_Net,

        ROUND(
            CASE
                WHEN SUM(COALESCE(Thành_tiền_trước_CK, 0)) > 0
                     AND SUM(COALESCE(Thành_tiền_trước_CK, 0)) > SUM(COALESCE(Thành_tiền_CK, 0))
                THEN
                    (((SUM(COALESCE(Thành_tiền_trước_CK, 0)) - SUM(COALESCE(Thành_tiền_CK, 0))) * 1.0)
                      / SUM(COALESCE(Thành_tiền_trước_CK, 0))) * 100
                ELSE 0
            END,
            2
        ) AS Tỷ_lệ_CK

    FROM data
    WHERE LoaiCT IN ('Bán lẻ', 'Hàng bán trả lại')
    GROUP BY
        Ngày,
        Số_điện_thoại,
        Số_CT,
        Mã_NB, Tên_hàng;
    """
    cur.executescript(query)
    conn.commit()
    cur.close()
    conn.close()

    log("📦 Export parquet theo tháng...")
    export_parquet_by_month(database_path, table="tinhhinhbanhang", out_dir=PARQUET_OUT_DIR)

    log("📦 Export 3 parquet cuối cho app...")
    export_final_app_parquets(database_path, table="tinhhinhbanhang", out_dir=FINAL_OUT_DIR)

    log("🎉 Hoàn tất update_db_online.")

# ================== MAIN ==================
if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception:
        print("❌ Lỗi khi chạy update_db_online.py")
        print(traceback.format_exc())
        raise