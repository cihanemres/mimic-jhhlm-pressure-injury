"""Adim 5 (Faz 2): Analiz veri seti. Her yatis icin tek satir, 04'teki birincil kohort.

Kural: tum degiskenler intime ile intime + 72 saat arasindan hesaplanir (sizinti olmasin).
SOFA ilk 24 saatten. Komorbidite taburculuk ICD kodlarindan (yatisin tamami; zaman bilgisi yok).

Kohort ve sonuc zamanlari 04'un yazdigi <cikti>/ozel/04_kohort.parquet dosyasindan okunur;
once 04 calistirilmali.

SOFA, mekanik ventilasyon, vazopresorler ve Charlson icin mimic-code concept SQL'leri
(code/mimic_code_sql/, kaynak README'de) kohort hastalariyla sinirli tablolar uzerinde calistirilir.

Ciktilar:
    <cikti>/ozel/analiz_seti.parquet           (hasta duzeyi, yalnizca ozel)
    <cikti>/paylasilabilir/05a_degisken_ozeti.csv (doluluk, medyan/IQR veya yuzde; kucuk hucre gizli)

Kullanim:
    python code/05_analiz_seti.py --veri <MIMIC_DIR>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurallar import (ANALIZ_IKILI, ANALIZ_KATEGORIK, BMI_ARALIK, BOY_ARALIK, BOY_CARPAN,  # noqa: E402
                      BRADEN_ITEMID, BRADEN_MOBILITE_DISI, CIHAZ_YOK,
                      IDARI_SANSUR_GUN, JH_GRUP, KILO_ARALIK, KILO_CARPAN, KISITLAMA_VAR, LAB_EN_KOTU,
                      MARUZIYET_SAAT, PENCERE_SAAT, SABIT_PENCERE_BITIS, SOFA_SAAT, braden_puan,
                      jh_hlm_sayi, rass_sayi)
from mimic_db import arguman_al, baglan, cikti_klasorleri, ozet_tablosu_gizle  # noqa: E402

import pandas as pd  # noqa: E402

a = arguman_al("Analiz veri seti")
con = baglan(a.veri, a.bellek)
ozel, paylas = cikti_klasorleri(a.cikti)

try:
    from duckdb.sqltypes import INTEGER, VARCHAR
except ImportError:
    from duckdb.typing import INTEGER, VARCHAR
con.create_function("jh_hlm", jh_hlm_sayi, [VARCHAR], INTEGER, null_handling="special")
con.create_function("rass", rass_sayi, [VARCHAR], INTEGER, null_handling="special")

# ---- Onayli itemid'ler ----
onayli = Path("config/itemids_onayli.csv")
it = pd.read_csv(onayli)
if {"kayit_sayisi", "yatis_sayisi"} & set(it.columns):
    print("UYARI: config/itemids_onayli.csv kayit_sayisi/yatis_sayisi sutunu iceriyor. Bu sutunlari silin "
          "(depoya girmemeli); onay dosyasini ozel/itemid_onay_sablonu.csv'den uretin.")
it = it[pd.to_numeric(it["onay"], errors="coerce") == 1]  # bos onay varsa sutun ondalik okunur


def ids(*gruplar):
    s = it.loc[it["degisken_grubu"].isin(gruplar), "itemid"].astype(int).tolist()
    return ",".join(map(str, s)) if s else "-1"


W, S = PENCERE_SAAT, SOFA_SAAT

# ---- Kohort ----
kohort_yol = ozel / "04_kohort.parquet"
if not kohort_yol.exists():
    raise SystemExit(f"{kohort_yol} yok. Once 04_kritik_kontroller.py calistirin.")
con.execute(f"""
CREATE TEMP TABLE kohort AS
SELECT *, intime + INTERVAL {W} HOUR AS pencere_bitis, intime + INTERVAL {S} HOUR AS sofa_bitis
FROM read_parquet('{kohort_yol.as_posix()}')
""")
n_kohort = con.execute("SELECT count(*) FROM kohort").fetchone()[0]

# Pencere icindeki chartevents kayitlari (onayli itemid'ler, saat olarak)
con.execute(f"""
CREATE TEMP TABLE ce AS
SELECT e.stay_id, e.itemid, e.charttime, e.value, e.valuenum,
       date_diff('minute', k.intime, e.charttime) / 60.0 AS saat
FROM chartevents e JOIN kohort k USING (stay_id)
WHERE e.itemid IN ({','.join(map(str, it['itemid'].astype(int)))})
  AND e.charttime >= k.intime AND e.charttime < k.pencere_bitis
""")
con.register("it", it[["degisken_grubu", "itemid"]])

# ---- 1. Demografi ----
demo = con.execute("""
SELECT k.stay_id, k.yas, p.gender AS cinsiyet, ad.admission_type AS kabul_tipi,
       k.first_careunit AS ilk_yb_birimi, k.anchor_year_group
FROM kohort k JOIN patients p USING (subject_id) JOIN admissions ad USING (hadm_id)
""").df()

# BMI: ilk boy ve ilk kilo. Istisna: pencere hastane yatisinin basindan (admittime) intime + 72 saate;
# boy ve kilo cogunlukla YB girisinden once kaydediliyor ve sonuc bilgisi tasimiyor.
# Aralik disi boy/kilo kaydi kullanilmaz (ilk aralik ici kayit alinir); aralik disi BMI bos sayilir.
con.register("boy_carpan", pd.DataFrame(list(BOY_CARPAN.items()), columns=["itemid", "carpan"]))
con.register("kilo_carpan", pd.DataFrame(list(KILO_CARPAN.items()), columns=["itemid", "carpan"]))
bmi = con.execute(f"""
WITH olcum AS (
    SELECT k.stay_id, e.itemid, e.charttime, e.valuenum
    FROM chartevents e
    JOIN kohort k ON e.hadm_id = k.hadm_id
    JOIN admissions ad ON ad.hadm_id = k.hadm_id
    WHERE e.itemid IN ({ids('boy', 'kilo')})
      AND e.charttime >= ad.admittime AND e.charttime < k.pencere_bitis
), boy AS (
    SELECT stay_id, arg_min(valuenum * carpan, charttime)
               FILTER (WHERE valuenum * carpan BETWEEN {BOY_ARALIK[0]} AND {BOY_ARALIK[1]}) AS boy_cm
    FROM olcum JOIN boy_carpan USING (itemid)
    WHERE itemid IN ({ids('boy')}) AND valuenum IS NOT NULL
    GROUP BY 1
), kilo AS (
    SELECT stay_id, arg_min(valuenum * carpan, charttime)
               FILTER (WHERE valuenum * carpan BETWEEN {KILO_ARALIK[0]} AND {KILO_ARALIK[1]}) AS kilo_kg
    FROM olcum JOIN kilo_carpan USING (itemid)
    WHERE itemid IN ({ids('kilo')}) AND valuenum IS NOT NULL
    GROUP BY 1
)
SELECT k.stay_id, b.boy_cm, w.kilo_kg, w.kilo_kg / ((b.boy_cm / 100) ^ 2) AS bmi,
       b.stay_id IS NOT NULL AS boy_kayitli, w.stay_id IS NOT NULL AS kilo_kayitli
FROM kohort k LEFT JOIN boy b USING (stay_id) LEFT JOIN kilo w USING (stay_id)
""").df()
# Aralik disi nedeniyle bos sayilan yatislar (05a'ya yazilir). Boy/kilo: kaydi var ama hicbiri aralik
# icinde degil. BMI: aralik ici boy ve kiloyla hesaplanan deger aralik disi.
bmi_disi = bmi["bmi"].notna() & ~bmi["bmi"].between(*BMI_ARALIK)
aralik_disi = pd.DataFrame({
    "degisken": ["boy_cm", "kilo_kg", "bmi"], "tip": "aralik_disi_eksik",
    "kategori": [f"{BOY_ARALIK[0]}-{BOY_ARALIK[1]} cm disi", f"{KILO_ARALIK[0]}-{KILO_ARALIK[1]} kg disi",
                 f"{BMI_ARALIK[0]}-{BMI_ARALIK[1]} disi"],
    "sayi": [int((bmi.pop("boy_kayitli") & bmi["boy_cm"].isna()).sum()),
             int((bmi.pop("kilo_kayitli") & bmi["kilo_kg"].isna()).sum()), int(bmi_disi.sum())]})
bmi.loc[bmi_disi, "bmi"] = None

# ---- 2. mimic-code concept tablolari (kohort hastalariyla sinirli) ----
con.execute("CREATE SCHEMA mimiciv_hosp; CREATE SCHEMA mimiciv_icu; CREATE SCHEMA mimiciv_derived")
for sema, tablo, kosul in [
    ("mimiciv_hosp", "patients", "subject_id IN (SELECT subject_id FROM kohort)"),
    ("mimiciv_hosp", "admissions", "hadm_id IN (SELECT hadm_id FROM kohort)"),
    # Basinc yarasi tani kodlari (ICD-9 707.0x, ICD-10 L89) hicbir degiskene girmez
    ("mimiciv_hosp", "diagnoses_icd", "hadm_id IN (SELECT hadm_id FROM kohort) "
     "AND NOT (icd_version = 9 AND icd_code LIKE '7070%') AND NOT (icd_version = 10 AND icd_code LIKE 'L89%')"),
    ("mimiciv_hosp", "labevents", "subject_id IN (SELECT subject_id FROM kohort)"),
    ("mimiciv_icu", "chartevents", "stay_id IN (SELECT stay_id FROM kohort)"),
    ("mimiciv_icu", "inputevents", "stay_id IN (SELECT stay_id FROM kohort)"),
    ("mimiciv_icu", "outputevents", "stay_id IN (SELECT stay_id FROM kohort)"),
]:
    con.execute(f"CREATE VIEW {sema}.{tablo} AS SELECT * FROM main.{tablo} WHERE {kosul}")
# bg.sql FiO2 icin chartevents'i subject_id ile birlestirir; kohort hastasinin diger yatislari
# disarida kalir ama pencere (intime..) zaten yalnizca bu yatisi kapsar.
sql_klasor = Path(__file__).parent / "mimic_code_sql"
for ad in ["age", "charlson", "bg", "chemistry", "complete_blood_count", "enzyme", "gcs",
           "oxygen_delivery", "ventilator_setting", "vitalsign", "urine_output", "ventilation",
           "norepinephrine", "epinephrine", "dopamine", "dobutamine", "phenylephrine", "vasopressin"]:
    con.execute((sql_klasor / f"{ad}.sql").read_text(encoding="utf-8"))

# ---- 3. SOFA (ilk 24 saat; puanlama mimic-code first_day_sofa ile ayni) ----
sofa = con.execute("""
WITH vaso_stg AS (
    SELECT k.stay_id, 'norepinephrine' AS ilac, v.vaso_rate AS rate FROM kohort k
    JOIN mimiciv_derived.norepinephrine v ON v.stay_id = k.stay_id
     AND v.starttime >= k.intime AND v.starttime <= k.sofa_bitis
    UNION ALL
    SELECT k.stay_id, 'epinephrine', v.vaso_rate FROM kohort k
    JOIN mimiciv_derived.epinephrine v ON v.stay_id = k.stay_id
     AND v.starttime >= k.intime AND v.starttime <= k.sofa_bitis
    UNION ALL
    SELECT k.stay_id, 'dobutamine', v.vaso_rate FROM kohort k
    JOIN mimiciv_derived.dobutamine v ON v.stay_id = k.stay_id
     AND v.starttime >= k.intime AND v.starttime <= k.sofa_bitis
    UNION ALL
    SELECT k.stay_id, 'dopamine', v.vaso_rate FROM kohort k
    JOIN mimiciv_derived.dopamine v ON v.stay_id = k.stay_id
     AND v.starttime >= k.intime AND v.starttime <= k.sofa_bitis
), vaso AS (
    SELECT stay_id,
           max(CASE WHEN ilac = 'norepinephrine' THEN rate END) AS rate_norepinephrine,
           max(CASE WHEN ilac = 'epinephrine' THEN rate END) AS rate_epinephrine,
           max(CASE WHEN ilac = 'dopamine' THEN rate END) AS rate_dopamine,
           max(CASE WHEN ilac = 'dobutamine' THEN rate END) AS rate_dobutamine
    FROM vaso_stg GROUP BY 1
), pafi AS (
    SELECT k.stay_id,
           min(CASE WHEN vd.stay_id IS NULL THEN bg.pao2fio2ratio END) AS pao2fio2_novent_min,
           min(CASE WHEN vd.stay_id IS NOT NULL THEN bg.pao2fio2ratio END) AS pao2fio2_vent_min
    FROM kohort k
    JOIN mimiciv_derived.bg bg ON bg.subject_id = k.subject_id
     AND bg.charttime >= k.intime AND bg.charttime <= k.sofa_bitis AND bg.specimen = 'ART.'
    LEFT JOIN mimiciv_derived.ventilation vd ON vd.stay_id = k.stay_id
     AND bg.charttime >= vd.starttime AND bg.charttime <= vd.endtime
     AND vd.ventilation_status = 'InvasiveVent'
    GROUP BY 1
), vital AS (
    SELECT k.stay_id, min(v.mbp) AS mbp_min FROM kohort k
    JOIN mimiciv_derived.vitalsign v ON v.stay_id = k.stay_id
     AND v.charttime >= k.intime AND v.charttime <= k.sofa_bitis
    GROUP BY 1
), lab AS (
    SELECT k.stay_id,
           max(c.creatinine) AS creatinine_max, max(e.bilirubin_total) AS bilirubin_max,
           min(b.platelet) AS platelet_min
    FROM kohort k
    LEFT JOIN mimiciv_derived.chemistry c ON c.subject_id = k.subject_id
     AND c.charttime >= k.intime AND c.charttime <= k.sofa_bitis
    LEFT JOIN mimiciv_derived.enzyme e ON e.subject_id = k.subject_id
     AND e.charttime >= k.intime AND e.charttime <= k.sofa_bitis
    LEFT JOIN mimiciv_derived.complete_blood_count b ON b.subject_id = k.subject_id
     AND b.charttime >= k.intime AND b.charttime <= k.sofa_bitis
    GROUP BY 1
), uo AS (
    SELECT k.stay_id, sum(u.urineoutput) AS urineoutput FROM kohort k
    JOIN mimiciv_derived.urine_output u ON u.stay_id = k.stay_id
     AND u.charttime >= k.intime AND u.charttime <= k.sofa_bitis
    GROUP BY 1
), gcs AS (
    SELECT k.stay_id, min(g.gcs) AS gcs_min FROM kohort k
    JOIN mimiciv_derived.gcs g ON g.stay_id = k.stay_id
     AND g.charttime >= k.intime AND g.charttime <= k.sofa_bitis
    GROUP BY 1
), sc AS (
    SELECT k.stay_id, v.*, p.pao2fio2_novent_min, p.pao2fio2_vent_min, vi.mbp_min,
           l.creatinine_max, l.bilirubin_max, l.platelet_min, u.urineoutput, g.gcs_min
    FROM kohort k
    LEFT JOIN vaso v USING (stay_id) LEFT JOIN pafi p USING (stay_id) LEFT JOIN vital vi USING (stay_id)
    LEFT JOIN lab l USING (stay_id) LEFT JOIN uo u USING (stay_id) LEFT JOIN gcs g USING (stay_id)
), puan AS (
    SELECT stay_id,
      CASE WHEN pao2fio2_vent_min < 100 THEN 4 WHEN pao2fio2_vent_min < 200 THEN 3
           WHEN pao2fio2_novent_min < 300 THEN 2 WHEN pao2fio2_novent_min < 400 THEN 1
           WHEN coalesce(pao2fio2_vent_min, pao2fio2_novent_min) IS NULL THEN NULL ELSE 0 END AS sofa_solunum,
      CASE WHEN platelet_min < 20 THEN 4 WHEN platelet_min < 50 THEN 3 WHEN platelet_min < 100 THEN 2
           WHEN platelet_min < 150 THEN 1 WHEN platelet_min IS NULL THEN NULL ELSE 0 END AS sofa_koagulasyon,
      CASE WHEN bilirubin_max >= 12.0 THEN 4 WHEN bilirubin_max >= 6.0 THEN 3 WHEN bilirubin_max >= 2.0 THEN 2
           WHEN bilirubin_max >= 1.2 THEN 1 WHEN bilirubin_max IS NULL THEN NULL ELSE 0 END AS sofa_karaciger,
      CASE WHEN rate_dopamine > 15 OR rate_epinephrine > 0.1 OR rate_norepinephrine > 0.1 THEN 4
           WHEN rate_dopamine > 5 OR rate_epinephrine <= 0.1 OR rate_norepinephrine <= 0.1 THEN 3
           WHEN rate_dopamine > 0 OR rate_dobutamine > 0 THEN 2 WHEN mbp_min < 70 THEN 1
           WHEN coalesce(mbp_min, rate_dopamine, rate_dobutamine, rate_epinephrine, rate_norepinephrine) IS NULL
           THEN NULL ELSE 0 END AS sofa_kardiyovaskuler,
      CASE WHEN gcs_min >= 13 AND gcs_min <= 14 THEN 1 WHEN gcs_min >= 10 AND gcs_min <= 12 THEN 2
           WHEN gcs_min >= 6 AND gcs_min <= 9 THEN 3 WHEN gcs_min < 6 THEN 4
           WHEN gcs_min IS NULL THEN NULL ELSE 0 END AS sofa_mss,
      CASE WHEN creatinine_max >= 5.0 THEN 4 WHEN urineoutput < 200 THEN 4
           WHEN creatinine_max >= 3.5 AND creatinine_max < 5.0 THEN 3 WHEN urineoutput < 500 THEN 3
           WHEN creatinine_max >= 2.0 AND creatinine_max < 3.5 THEN 2
           WHEN creatinine_max >= 1.2 AND creatinine_max < 2.0 THEN 1
           WHEN coalesce(urineoutput, creatinine_max) IS NULL THEN NULL ELSE 0 END AS sofa_bobrek
    FROM sc
)
SELECT stay_id,
       coalesce(sofa_solunum, 0) + coalesce(sofa_koagulasyon, 0) + coalesce(sofa_karaciger, 0)
       + coalesce(sofa_kardiyovaskuler, 0) + coalesce(sofa_mss, 0) + coalesce(sofa_bobrek, 0) AS sofa_24s,
       sofa_solunum, sofa_koagulasyon, sofa_karaciger, sofa_kardiyovaskuler, sofa_mss, sofa_bobrek
FROM puan
""").df()

# ---- 4. Tedavi (0-72 saat) ----
# Aralik tipi kayitlar: pencereyle ortusen (starttime < pencere_bitis ve endtime > intime)
vazo = " UNION ALL ".join(
    f"SELECT stay_id, starttime, endtime FROM mimiciv_derived.{t}"
    for t in ["norepinephrine", "epinephrine", "dopamine", "phenylephrine", "vasopressin"])
sedatif = ", ".join(
    f"max(CASE WHEN i.itemid IN ({ids(g)}) THEN 1 ELSE 0 END) AS {ad}"
    for g, ad in [("sedatif_propofol", "propofol"), ("sedatif_midazolam", "midazolam"),
                  ("sedatif_deksmedetomidin", "deksmedetomidin")])
tedavi = con.execute(f"""
WITH mv AS (
    SELECT DISTINCT v.stay_id FROM mimiciv_derived.ventilation v JOIN kohort k USING (stay_id)
    WHERE v.ventilation_status = 'InvasiveVent' AND v.starttime < k.pencere_bitis AND v.endtime > k.intime
), vz AS (
    SELECT DISTINCT v.stay_id FROM ({vazo}) v JOIN kohort k USING (stay_id)
    WHERE v.starttime < k.pencere_bitis AND v.endtime > k.intime
), sed AS (
    SELECT i.stay_id, {sedatif}
    FROM inputevents i JOIN kohort k USING (stay_id)
    WHERE i.itemid IN ({ids('sedatif_propofol', 'sedatif_midazolam', 'sedatif_deksmedetomidin')})
      AND i.ordercategorydescription = 'Continuous Med'
      AND i.starttime < k.pencere_bitis AND i.endtime > k.intime
    GROUP BY 1
), rs AS (
    SELECT stay_id, min(rass(value)) AS rass_en_dusuk, avg(rass(value)) AS rass_ortalama
    FROM ce WHERE itemid IN ({ids('rass')}) GROUP BY 1
), kis AS (
    SELECT DISTINCT stay_id FROM ce
    WHERE itemid IN ({ids('kisitlama')}) AND lower(trim(value)) IN ({','.join(f"'{d}'" for d in KISITLAMA_VAR)})
)
SELECT k.stay_id,
       (mv.stay_id IS NOT NULL)::INTEGER AS mekanik_ventilasyon,
       (vz.stay_id IS NOT NULL)::INTEGER AS vazopresor,
       coalesce(sed.propofol, 0) AS sedatif_propofol,
       coalesce(sed.midazolam, 0) AS sedatif_midazolam,
       coalesce(sed.deksmedetomidin, 0) AS sedatif_deksmedetomidin,
       (sed.stay_id IS NOT NULL)::INTEGER AS sedatif_herhangi,
       rs.rass_en_dusuk, rs.rass_ortalama,
       (kis.stay_id IS NOT NULL)::INTEGER AS fiziksel_kisitlama
FROM kohort k
LEFT JOIN mv USING (stay_id) LEFT JOIN vz USING (stay_id) LEFT JOIN sed USING (stay_id)
LEFT JOIN rs USING (stay_id) LEFT JOIN kis USING (stay_id)
""").df()

# ---- 5. Laboratuvar (0-72 saat; ilk ve en kotu) ----
lab_parca = []
for grup, yon in LAB_EN_KOTU.items():
    ad = grup.removeprefix("lab_")
    lab_parca.append(con.execute(f"""
    SELECT k.stay_id,
           arg_min(l.valuenum, l.charttime) AS {ad}_ilk,
           {yon}(l.valuenum) AS {ad}_en_kotu
    FROM kohort k JOIN labevents l ON l.hadm_id = k.hadm_id
     AND l.charttime >= k.intime AND l.charttime < k.pencere_bitis
    WHERE l.itemid IN ({ids(grup)}) AND l.valuenum IS NOT NULL
    GROUP BY 1
    """).df().set_index("stay_id"))
lab = pd.concat(lab_parca, axis=1).reset_index() if lab_parca else pd.DataFrame(columns=["stay_id"])

# ---- 6. Komorbidite (mimic-code Charlson; ICD-9 ve ICD-10) ----
komorb = con.execute("""
SELECT k.stay_id,
       c.charlson_comorbidity_index AS charlson,
       c.charlson_comorbidity_index - c.age_score AS charlson_yassiz,
       (c.diabetes_without_cc > 0 OR c.diabetes_with_cc > 0)::INTEGER AS diyabet,
       c.peripheral_vascular_disease AS periferik_damar,
       c.congestive_heart_failure AS kalp_yetmezligi
FROM kohort k LEFT JOIN mimiciv_derived.charlson c USING (hadm_id)
""").df()

# ---- 7. Hemsirelik (0-72 saat) ----
# Braden: alti alt boyutun ayni anda kaydedildigi tam setler; ilk ve en dusuk
br = con.execute(f"SELECT stay_id, charttime, itemid, value FROM ce WHERE itemid IN "
                 f"({','.join(map(str, BRADEN_ITEMID))})").df()
alt = list(BRADEN_ITEMID.values())
braden_sut = ["braden_toplam"] + [f"braden_{x}" for x in alt] + ["braden_mobilite_disi"]
if len(br):
    br["alt"] = br["itemid"].map(BRADEN_ITEMID)
    br["puan"] = [braden_puan(a_, v) for a_, v in zip(br["alt"], br["value"])]
    g = br.pivot_table(index=["stay_id", "charttime"], columns="alt", values="puan", aggfunc="last")
    g = g.reindex(columns=alt).dropna().reset_index().sort_values("charttime")
    g["braden_toplam"] = g[alt].sum(axis=1)
    g["braden_mobilite_disi"] = g[BRADEN_MOBILITE_DISI].sum(axis=1)
    g = g.rename(columns={x: f"braden_{x}" for x in alt})
    braden = pd.concat([g.groupby("stay_id")[braden_sut].first().add_suffix("_ilk"),
                        g.groupby("stay_id")[braden_sut].min().add_suffix("_en_dusuk")], axis=1).reset_index()
else:
    braden = pd.DataFrame(columns=["stay_id"])

# JH-HLM: ayni anda celiskili kayitta en yuksek duzey
jh = con.execute(f"""
WITH an AS (
    SELECT stay_id, charttime, max(jh_hlm(value)) AS duzey FROM ce
    WHERE itemid IN ({ids('jh_hlm')}) AND jh_hlm(value) IS NOT NULL
    GROUP BY 1, 2
)
SELECT stay_id, arg_min(duzey, charttime) AS jh_hlm_ilk, max(duzey) AS jh_hlm_en_yuksek,
       avg(duzey) AS jh_hlm_ortalama, count(*) AS jh_hlm_kayit_sayisi
FROM an GROUP BY 1
""").df()
jh["jh_hlm_grup"] = jh["jh_hlm_en_yuksek"].map(JH_GRUP)


def var_mi(grup):
    """Grupta bos olmayan ve CIHAZ_YOK listesinde olmayan bir kayit varsa 1."""
    yok = ", ".join(f"'{d}'" for d in CIHAZ_YOK.get(grup, set()))
    yok_sql = f"AND lower(trim(value)) NOT IN ({yok})" if yok else ""
    return (f"max(CASE WHEN itemid IN ({ids(grup)}) AND trim(value) <> '' {yok_sql} "
            f"THEN 1 ELSE 0 END)")


hems = con.execute(f"""
SELECT k.stay_id,
       coalesce(p.pozisyon_24s, 0) AS pozisyon_degistirme_24s,
       coalesce(c.tedavi_edici_yatak, 0) AS tedavi_edici_yatak,
       coalesce(c.basinc_azaltici_cihaz, 0) AS basinc_azaltici_cihaz,
       coalesce(c.yardimci_cihaz, 0) AS yardimci_cihaz,
       coalesce(c.rn_mobilite_hedefi, 0) AS rn_mobilite_hedefi,
       c.am_pac_ilk, c.am_pac_en_dusuk,
       coalesce(c.ncp_impaired_mobility, 0) AS ncp_impaired_mobility,
       coalesce(c.ncp_activity_intolerance, 0) AS ncp_activity_intolerance,
       coalesce(c.ncp_skin_integrity, 0) AS ncp_skin_integrity
FROM kohort k
LEFT JOIN (
    -- Pozisyon degistirme: Turn/Position kaydi olan farkli zaman sayisi, 24 saate gore
    SELECT stay_id, count(DISTINCT charttime) / ({W} / 24.0) AS pozisyon_24s
    FROM ce WHERE itemid IN ({ids('pozisyon')}) GROUP BY 1
) p USING (stay_id)
LEFT JOIN (
    SELECT stay_id,
           {var_mi('tedavi_edici_yatak')} AS tedavi_edici_yatak,
           {var_mi('basinc_azaltici_cihaz')} AS basinc_azaltici_cihaz,
           {var_mi('yardimci_cihaz')} AS yardimci_cihaz,
           {var_mi('rn_mobilite_hedefi')} AS rn_mobilite_hedefi,
           arg_min(TRY_CAST(value AS DOUBLE), charttime)
               FILTER (WHERE itemid IN ({ids('am_pac')}) AND TRY_CAST(value AS DOUBLE) IS NOT NULL) AS am_pac_ilk,
           min(TRY_CAST(value AS DOUBLE)) FILTER (WHERE itemid IN ({ids('am_pac')})) AS am_pac_en_dusuk,
           {var_mi('ncp_impaired_mobility')} AS ncp_impaired_mobility,
           {var_mi('ncp_activity_intolerance')} AS ncp_activity_intolerance,
           {var_mi('ncp_skin_integrity')} AS ncp_skin_integrity
    FROM ce GROUP BY 1
) c USING (stay_id)
""").df()

# ---- 8. Sonuclar (04'un yazdigi zamanlardan) ----
# Olaya kadar sure 72. saatten itibaren (saat). Olay: ilk yeni BY; yoksa YB cikisi (olum/taburculuk);
# 28. gunde idari sansur. YB cikis saati olum icin de kullanilir. YB cikisindan sonraki BY kaydi olay sayilmaz.
sinir = IDARI_SANSUR_GUN * 24
# "_bilinen": BILINMIYOR haric (olay zamani bilinen evreli ilk kayit; 04b'deki yeni_by_bilinmiyor_haric)
k = con.execute("SELECT stay_id, yb_saat, yb_olum, ilk_by_saat, ilk_evre2_saat, ilk_bilinen_by_saat "
                "FROM kohort").df()
sonuc = k[["stay_id"]].copy()
for ek, sut in [("", "ilk_by_saat"), ("_evre2", "ilk_evre2_saat"), ("_bilinen", "ilk_bilinen_by_saat")]:
    by_olay = k[sut].notna() & (k[sut] <= k["yb_saat"]) & (k[sut] <= sinir)
    cikis_olay = ~by_olay & (k["yb_saat"] <= sinir)
    bitis = k["yb_saat"].clip(upper=sinir).where(~by_olay, k[sut])
    sonuc[f"sure_saat{ek}"] = bitis - MARUZIYET_SAAT
    sonuc[f"olay_tipi{ek}"] = "sansur"
    sonuc.loc[cikis_olay & k["yb_olum"], f"olay_tipi{ek}"] = "yb_olum"
    sonuc.loc[cikis_olay & ~k["yb_olum"], f"olay_tipi{ek}"] = "taburculuk"
    sonuc.loc[by_olay, f"olay_tipi{ek}"] = "yeni_by"
    # 72-168 saat penceresinde yeni BY (04b'deki yeni_by_72_168 ile ayni tanim; YB cikisindan sonraki kayit sayilmaz)
    sonuc[f"yeni_by_72_168{ek}"] = (by_olay & (k[sut] < SABIT_PENCERE_BITIS)).astype(int)
print(f"YB cikisindan sonra kaydedilen ilk yeni BY (olay sayilmadi; 04b'de de sayilmaz): "
      f"{int((k['ilk_by_saat'] > k['yb_saat']).sum())}")

# ---- Birlestir ve kaydet ----
analiz = demo
for df in [bmi, sofa, tedavi, lab, komorb, braden, jh, hems, sonuc]:
    analiz = analiz.merge(df, on="stay_id", how="left")
assert len(analiz) == n_kohort and analiz["stay_id"].is_unique

# Var/yok ve sayim degiskenleri: ilgili itemid grubu onaylanmamissa 0 degil bos
ONAY_GEREKEN = {
    "sedatif_propofol": ["sedatif_propofol"], "sedatif_midazolam": ["sedatif_midazolam"],
    "sedatif_deksmedetomidin": ["sedatif_deksmedetomidin"],
    "sedatif_herhangi": ["sedatif_propofol", "sedatif_midazolam", "sedatif_deksmedetomidin"],
    "fiziksel_kisitlama": ["kisitlama"], "pozisyon_degistirme_24s": ["pozisyon"],
    "tedavi_edici_yatak": ["tedavi_edici_yatak"], "basinc_azaltici_cihaz": ["basinc_azaltici_cihaz"],
    "yardimci_cihaz": ["yardimci_cihaz"], "rn_mobilite_hedefi": ["rn_mobilite_hedefi"],
    "ncp_impaired_mobility": ["ncp_impaired_mobility"], "ncp_activity_intolerance": ["ncp_activity_intolerance"],
    "ncp_skin_integrity": ["ncp_skin_integrity"],
}
onayli_gruplar = set(it["degisken_grubu"])
for sut, gruplar in ONAY_GEREKEN.items():
    if not set(gruplar) <= onayli_gruplar:
        analiz[sut] = None
        print(f"UYARI: {sut} bos birakildi (onaylanmamis grup: {sorted(set(gruplar) - onayli_gruplar)})")
    if sut != "pozisyon_degistirme_24s":
        analiz[sut] = analiz[sut].astype("Int64")
analiz.to_parquet(ozel / "analiz_seti.parquet", index=False)

# ---- 05a: degisken ozeti ----
KATEGORIK, IKILI = ANALIZ_KATEGORIK, ANALIZ_IKILI
satirlar = []
for s in analiz.columns.drop("stay_id"):
    x = analiz[s]
    dolu = int(x.notna().sum())
    temel = {"degisken": s, "n": len(x), "dolu": dolu, "bos": len(x) - dolu,
             "doluluk_yuzde": round(100 * dolu / len(x), 1) if len(x) else None}
    ikili = s in IKILI
    if s in KATEGORIK or ikili:
        for deger, sayi in x.value_counts().sort_index().items():
            if ikili and deger == 0:
                continue
            satirlar.append({**temel, "tip": "ikili" if ikili else "kategorik", "kategori": deger,
                             "sayi": int(sayi), "yuzde": round(100 * sayi / dolu, 1)})
        if ikili and not (x == 1).any():
            satirlar.append({**temel, "tip": "ikili", "kategori": 1,
                             "sayi": 0 if dolu else None, "yuzde": 0.0 if dolu else None})
    else:
        x = pd.to_numeric(x, errors="coerce").astype(float)  # bos iceren Int32'de medyan Windows'ta tasiyor
        satirlar.append({**temel, "tip": "sayisal", "medyan": x.median(),
                         "q1": x.quantile(.25), "q3": x.quantile(.75)})
ozet = pd.DataFrame(satirlar, columns=["degisken", "tip", "kategori", "n", "dolu", "bos", "doluluk_yuzde",
                                       "sayi", "yuzde", "medyan", "q1", "q3"])
ozet = pd.concat([ozet, aralik_disi.assign(n=len(analiz))], ignore_index=True)
ozet.to_csv(ozel / "05a_degisken_ozeti.csv", index=False, encoding="utf-8-sig")

# Paylasilabilir: kurallar mimic_db.ozet_tablosu_gizle'de
ozet_tablosu_gizle(ozet, ["degisken"], "doluluk_yuzde").to_csv(
    paylas / "05a_degisken_ozeti.csv", index=False, encoding="utf-8-sig")

print(f"Analiz seti: {len(analiz)} yatis, {analiz.shape[1] - 1} degisken -> {ozel / 'analiz_seti.parquet'}")
print(ozet[["degisken", "tip", "kategori", "doluluk_yuzde", "sayi", "medyan"]].to_string(index=False))
print(f"\nCiktilar: {ozel} ve {paylas}")
