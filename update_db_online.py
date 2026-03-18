import os
from pathlib import Path

def main():
    print("update_db_online đang chạy")

    # Tạo thư mục tạm
    base = Path("runtime")
    base.mkdir(exist_ok=True)

    out_dir = base / "parquet_out"
    out_dir.mkdir(exist_ok=True)

    # Tạm thời tạo file giả để test workflow trước
    (out_dir / "general.parquet").write_text("test")
    (out_dir / "revenue.parquet").write_text("test")
    (out_dir / "crm_cohort.parquet").write_text("test")

    print("done")

if __name__ == "__main__":
    main()
