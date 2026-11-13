"""MIMIC-IV tablolarina DuckDB uzerinden erisim.

Klasorde Parquet dosyasi varsa onu, yoksa .csv.gz dosyasini okur.
Klasor yapisi PhysioNet'teki gibi olmalidir:
    <veri_klasoru>/hosp/patients.csv.gz
    <veri_klasoru>/icu/chartevents.csv.gz
Parquet donusumunden sonra:
    <veri_klasoru>/parquet/chartevents.parquet
"""
import argparse
import os
from pathlib import Path

import duckdb

TABLOLAR = {
    "patients": "hosp",
    "admissions": "hosp",
    "icustays": "icu",
    "d_items": "icu",
    "chartevents": "icu",
    "datetimeevents": "icu",
    "labevents": "hosp",
    "d_labitems": "hosp",
    "inputevents": "icu",
    "procedureevents": "icu",
    "diagnoses_icd": "hosp",
    "d_icd_diagnoses": "hosp",
    "outputevents": "icu",
}


def arguman_al(aciklama, ekle=None):
    """Ortak argumanlar; ekle(p) betige ozel argumanlari ekler."""
    p = argparse.ArgumentParser(description=aciklama)
    p.add_argument(
        "--veri",
        default=os.environ.get("MIMIC_DIR"),
        help="MIMIC-IV klasoru (icinde hosp/ ve icu/ olan). MIMIC_DIR ortam degiskeni de kullanilabilir.",
    )
    p.add_argument("--cikti", default="outputs", help="Ciktilarin yazilacagi klasor")
    p.add_argument("--bellek", default="8GB", help="DuckDB bellek siniri, ornek: 8GB")
    if ekle:
        ekle(p)
    a = p.parse_args()
    if not a.veri:
        p.error("--veri ile MIMIC-IV klasorunu belirtin.")
    return a


def baglan(veri_klasoru, bellek="8GB"):
    veri = Path(veri_klasoru)
    if not (veri / "icu").exists():
        raise SystemExit(f"{veri} icinde icu/ klasoru bulunamadi. Yolu kontrol edin.")
    tmp = veri / "duckdb_tmp"
    tmp.mkdir(exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{bellek}'")
    con.execute(f"SET temp_directory='{tmp.as_posix()}'")
    for tablo, modul in TABLOLAR.items():
        pq = veri / "parquet" / f"{tablo}.parquet"
        csv = veri / modul / f"{tablo}.csv.gz"
        if pq.exists():
            kaynak = f"read_parquet('{pq.as_posix()}')"
        elif csv.exists():
            kaynak = f"read_csv_auto('{csv.as_posix()}', sample_size=-1)"
        else:
            raise SystemExit(f"{tablo} tablosu bulunamadi: {pq} veya {csv}")
        con.execute(f"CREATE VIEW {tablo} AS SELECT * FROM {kaynak}")
    return con


def cikti_klasorleri(kok):
    """Iki ayri klasor: ozel (yalnizca sizin icin) ve paylasilabilir (kucuk hucreler gizli)."""
    kok = Path(kok)
    ozel = kok / "ozel"
    paylas = kok / "paylasilabilir"
    ozel.mkdir(parents=True, exist_ok=True)
    paylas.mkdir(parents=True, exist_ok=True)
    return ozel, paylas


def kucuk_hucre_gizle(df, sutunlar, esik=5):
    """Paylasilacak tablolarda 1-4 arasi sayilari '<5' yapar (0 aynen kalir)."""
    df = df.copy()
    for s in sutunlar:
        df[s] = df[s].apply(lambda x: "<5" if x is not None and 0 < x < esik else x)
    return df


def ozet_tablosu_gizle(ozet, anahtar, dolu_yuzde, ek_gizle=(), korunan=None):
    """Degisken ozeti tablolarini (05a, 06 Tablo 1) paylasilabilir yapar.

    Beklenen sutunlar: tip, dolu, bos, sayi, yuzde, medyan, q1, q3 ve dolu_yuzde (doluluk/eksik yuzdesi).
    anahtar: ayni dagilima ait satirlari belirleyen sutunlar (or. ["degisken"] veya ["degisken", "grup"]).
    - 1-4 arasi sayilar "<5"; kucuk bir hucreyi geri hesaplatan sayilar "gizli".
    - Kategorik degiskende tek gizli kategori kalirsa en kucuk ikinci kategori de gizlenir.
    - Gizli sayiya ait yuzde ve ek_gizle sutunlari bos; 5'ten az dolu satirda medyan/IQR bos.
    korunan: degisken -> kategoriler; tamamlayici olarak mumkunse secilmez (baska tabloda acik yazilan sayi).
    """
    import pandas as pd
    p = ozet.copy()
    gizli_dolu = p["dolu"].between(1, 4) | p["bos"].between(1, 4)
    gizli_sayi = (p["sayi"].between(1, 4) | (p["dolu"] - p["sayi"]).between(1, 4)
                  | (p["sayi"].notna() & gizli_dolu))
    korunan = korunan or {}
    for _, grup in p[p["tip"] == "kategorik"].groupby(anahtar):
        if gizli_sayi[grup.index].sum() == 1 and len(grup) > 1:
            aday = grup.loc[~gizli_sayi[grup.index]]
            serbest = ~aday["kategori"].astype(str).isin([str(k) for k in korunan.get(aday["degisken"].iloc[0], [])])
            gizli_sayi[(aday[serbest] if serbest.any() else aday)["sayi"].idxmin()] = True
    p.loc[gizli_dolu, dolu_yuzde] = None
    p.loc[gizli_sayi, ["yuzde", *ek_gizle]] = None
    p.loc[p["dolu"] < 5, ["medyan", "q1", "q3"]] = None
    tamamlayici = {"dolu": gizli_dolu & ~p["dolu"].between(1, 4),
                   "bos": gizli_dolu & ~p["bos"].between(1, 4),
                   "sayi": gizli_sayi & ~p["sayi"].between(1, 4)}
    p = kucuk_hucre_gizle(p, ["dolu", "bos", "sayi"])
    p[["dolu", "bos", "sayi"]] = p[["dolu", "bos", "sayi"]].astype(object)
    for s, maske in tamamlayici.items():
        p.loc[maske, s] = "gizli"
    for s in ["dolu", "bos", "sayi"]:  # 11.0 yerine 11 yazilsin
        p[s] = pd.Series([v if isinstance(v, str) or pd.isna(v) else int(v) for v in p[s]],
                         dtype=object, index=p.index)
    return p
