"""Adim 1: .csv.gz tablolarini Parquet'e cevirir (tek seferlik).

Tam veride chartevents cok buyuk oldugu icin sonraki betikler Parquet ile
dakikalar yerine saniyeler icinde calisir.

Kullanim:
    python code/01_parquet.py --veri <MIMIC_DIR>
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mimic_db import TABLOLAR, arguman_al  # noqa: E402

import duckdb  # noqa: E402

a = arguman_al("MIMIC-IV tablolarini Parquet'e cevirir")
veri = Path(a.veri)
hedef = veri / "parquet"
hedef.mkdir(exist_ok=True)

con = duckdb.connect()
con.execute(f"SET memory_limit='{a.bellek}'")
con.execute(f"SET temp_directory='{(veri / 'duckdb_tmp').as_posix()}'")

for tablo, modul in TABLOLAR.items():
    csv = veri / modul / f"{tablo}.csv.gz"
    pq = hedef / f"{tablo}.parquet"
    if pq.exists():
        print(f"[atlandi] {pq.name} zaten var")
        continue
    if not csv.exists():
        print(f"[UYARI] {csv} yok, atlandi")
        continue
    t = time.time()
    con.execute(
        f"COPY (SELECT * FROM read_csv_auto('{csv.as_posix()}', sample_size=-1)) "
        f"TO '{pq.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    n = con.execute(f"SELECT count(*) FROM read_parquet('{pq.as_posix()}')").fetchone()[0]
    print(f"[tamam] {tablo}: {n:,} satir, {time.time() - t:.0f} sn")
