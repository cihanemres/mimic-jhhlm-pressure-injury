"""Adim 4: Calismanin yapilabilirligini belirleyen kontroller.

1. Kohort akisi: her dahil etme/dislama adiminda kalan yatis sayisi
2. Yeni basinc yarasi sayisi (72. saatten sonra, YB yatisi suresince ve 72-168. saat penceresinde)
3. JH-HLM kaydinin yil gruplarina gore dagilimi
4. Braden alt boyutlarinin eksiksizligi ve hesaplanan toplam skor
5. Hemsirelik bakim planlarinin kayitlardaki gorunurlugu
6. Ayni stay_id ve charttime'da ayni gruptan birden fazla itemid (JH-HLM, Therapeutic Bed, Assistance Device)
7. Yeni sayilan yaralarda tespit tarihi 72. saatten once mi (onceden var olan yara kontrolu)
8. Ayni yatista hem eski sablon evre kaydi hem JH-HLM kaydi
9. Tutarlilik: onceki tanimla yeni sayilip tespit tarihi 72. saatten once olanlar yeni kohortta kaldi mi
10. Uzlastirma: onceki tanim ile birincil tanim arasinda yeni basinc yarasi gecisi ve nedenleri

Karar kurali: yeni basinc yarasi sayisi birkac yuzun altindaysa sonuc tanimi
genisletilmeli (hocayla birlikte karar verin).

Kullanim:
    python code/04_kritik_kontroller.py --veri <MIMIC_DIR>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurallar import (BRADEN_ITEMID, BRADEN_MOBILITE_DISI, IDARI_SANSUR_GUN,  # noqa: E402
                      MARUZIYET_SAAT, SABIT_PENCERE_BITIS, braden_puan, by_evre, jh_hlm_sayi)
from mimic_db import arguman_al, baglan, cikti_klasorleri, kucuk_hucre_gizle  # noqa: E402

import pandas as pd  # noqa: E402

a = arguman_al("Kritik kontroller")
con = baglan(a.veri, a.bellek)
ozel, paylas = cikti_klasorleri(a.cikti)

# Kurallar.py'deki Python fonksiyonlarini SQL icinde kullanilabilir yap
# (DuckDB surumune gore tip modulunun adi farkli)
try:
    from duckdb.sqltypes import INTEGER, VARCHAR
except ImportError:
    from duckdb.typing import INTEGER, VARCHAR
con.create_function("jh_hlm", jh_hlm_sayi, [VARCHAR], INTEGER, null_handling="special")
con.create_function("evre", by_evre, [VARCHAR], VARCHAR, null_handling="special")

# ---- Itemid gruplari ----
onayli = Path("config/itemids_onayli.csv")
if onayli.exists():
    it = pd.read_csv(onayli)
    if {"kayit_sayisi", "yatis_sayisi"} & set(it.columns):
        print("UYARI: config/itemids_onayli.csv kayit_sayisi/yatis_sayisi sutunu iceriyor. Bu sutunlari silin "
              "(depoya girmemeli); onay dosyasini ozel/itemid_onay_sablonu.csv'den uretin.")
    it = it[pd.to_numeric(it["onay"], errors="coerce") == 1]  # bos onay varsa sutun ondalik okunur
else:
    it = pd.read_csv(ozel / "itemid_adaylari.csv")
    it = it[it["kayit_sayisi"] > 0]
    print("UYARI: config/itemids_onayli.csv yok. Aday listesi kullaniliyor (yalnizca deneme icin).")


def ids(*gruplar):
    s = it.loc[it["degisken_grubu"].isin(gruplar), "itemid"].astype(int).tolist()
    return ",".join(map(str, s)) if s else "-1"


M, P = MARUZIYET_SAAT, SABIT_PENCERE_BITIS

# ---- Temel yatis tablosu ----
con.execute(f"""
CREATE TEMP TABLE yatis AS
SELECT s.subject_id, s.hadm_id, s.stay_id, s.intime, s.outtime, s.first_careunit,
       p.anchor_year_group,
       p.anchor_age + (year(s.intime) - p.anchor_year) AS yas,
       date_diff('minute', s.intime, s.outtime) / 60.0 AS yb_saat,
       (a.deathtime IS NOT NULL AND a.deathtime BETWEEN s.intime AND s.outtime) AS yb_olum
FROM icustays s
JOIN patients p USING (subject_id)
JOIN admissions a USING (hadm_id)
""")

# JH-HLM kayitlari (gecerli deger, saat olarak)
con.execute(f"""
CREATE TEMP TABLE jh AS
SELECT * FROM (
    SELECT e.stay_id, date_diff('minute', y.intime, e.charttime) / 60.0 AS saat,
           jh_hlm(e.value) AS jh
    FROM chartevents e JOIN yatis y USING (stay_id)
    WHERE e.itemid IN ({ids('jh_hlm')})
) WHERE jh IS NOT NULL
""")

# Basinc yarasi evre kayitlari: by_ham tum kayitlar, by_kayit yalnizca yara olanlar
# ("Not applicable" gibi yara olmayan degerler ve 'tanimsiz' disarida)
con.execute(f"""
CREATE TEMP TABLE by_ham AS
SELECT e.stay_id, e.itemid, date_diff('minute', y.intime, e.charttime) / 60.0 AS saat,
       evre(e.value) AS evre
FROM chartevents e JOIN yatis y USING (stay_id)
WHERE e.itemid IN ({ids('by_evre_eski', 'by_evre_yeni')})
""")
con.execute("CREATE TEMP TABLE by_kayit AS SELECT * FROM by_ham WHERE evre IS NOT NULL AND evre <> 'tanimsiz'")
tanimsiz = con.execute(f"""
SELECT count(*) FROM chartevents
WHERE itemid IN ({ids('by_evre_eski', 'by_evre_yeni')}) AND evre(value) = 'tanimsiz'
""").fetchone()[0]

# Kabulde basinc yarasi isareti
con.execute(f"""
CREATE TEMP TABLE kabulde_by AS
SELECT DISTINCT stay_id FROM chartevents
WHERE itemid IN ({ids('by_kabulde_var')})
  AND lower(trim(value)) IN ('1', 'yes', 'checked', 'true')
""")

# Yara numarasi etiketteki "#N" (tespit tarihi ve evre itemid'leri icin)
yara = it.loc[it["degisken_grubu"].isin(["by_tespit_tarihi", "by_evre_eski", "by_evre_yeni"]),
              ["degisken_grubu", "itemid", "label"]].copy()
yara["yara_no"] = yara["label"].str.extract(r"#(\d+)", expand=False).astype(int)
con.register("yara_no", yara[["degisken_grubu", "itemid", "yara_no"]])

# Tespit tarihi kayitlari: kohort adimi ve 7. bolum ayni tablodan okur (ayni alanlar, ayni saat hesabi).
# Saat bilgisi olmayan tarih TIMESTAMP'e cevrilince 00:00 olur.
con.execute("""
CREATE TEMP TABLE tespit_ham AS
SELECT e.stay_id, n.yara_no,
       date_diff('minute', y.intime, TRY_CAST(e.value AS TIMESTAMP)) / 60.0 AS tespit_saat
FROM datetimeevents e JOIN yara_no n USING (itemid) JOIN yatis y USING (stay_id)
WHERE n.degisken_grubu = 'by_tespit_tarihi'
""")
# Tespit tarihi 72. saatten once olan yara (yara numarasi eslestirilmez: herhangi bir yara yeterli)
con.execute(f"CREATE TEMP TABLE tespit_erken AS SELECT DISTINCT stay_id FROM tespit_ham WHERE tespit_saat < {M}")

# ---- 1. Kohort akisi ----
# BILINMIYOR evre (yara var, evre bilinmiyor) by_kayit icinde: dislamada ve sonucta yara sayilir
adimlar = [
    ("Tum YB yatislari", "TRUE"),
    ("Yas >= 18", "yas >= 18"),
    (f"YB'de >= {M} saat", f"yb_saat >= {M}"),
    (f"0-{M}. saatte >= 1 gecerli JH-HLM",
     f"stay_id IN (SELECT stay_id FROM jh WHERE saat >= 0 AND saat < {M})"),
    ("Kabulde basinc yarasi isareti yok", "stay_id NOT IN (SELECT stay_id FROM kabulde_by)"),
    (f"0-{M}. saatte basinc yarasi kaydi yok",
     f"stay_id NOT IN (SELECT stay_id FROM by_kayit WHERE saat < {M})"),
    (f"Tespit tarihi {M}. saatten once olan yara yok", "stay_id NOT IN (SELECT stay_id FROM tespit_erken)"),
]
kosul, akis = [], []
for ad, k in adimlar:
    kosul.append(k)
    n = con.execute(f"SELECT count(*), count(DISTINCT subject_id) FROM yatis WHERE {' AND '.join(kosul)}").fetchone()
    akis.append({"adim": ad, "yatis": n[0], "hasta": n[1]})
akis = pd.DataFrame(akis)
akis["dislanan"] = (akis["yatis"].shift(1) - akis["yatis"]).fillna(0).astype(int)
con.execute(f"CREATE TEMP TABLE kohort AS SELECT * FROM yatis WHERE {' AND '.join(kosul)}")
sinir = IDARI_SANSUR_GUN * 24
# Olay penceresinin ust siniri (05/06 ile ayni): 28. gun ve YB cikisi. YB cikisindan sonraki yara kaydi
# olay sayilmaz. Kullanan sorgularda kohort/yatis tablosu 'k' takma adiyla birlestirilir.
olay_ust = f"least({sinir}, k.yb_saat)"

# ---- Yara numarasina gore evre ve tespit tarihi (2. ve 7. bolum icin) ----
# Tespit tarihi #N yalnizca yeni sablondaki evre #N ile eslestirilir. Eski sablon icin
# eslestirme yapilmaz: ayni yatista tespit tarihi dolu mu, ona bakilir.
con.execute("""
CREATE TEMP TABLE yara_evre AS
SELECT b.stay_id, n.degisken_grubu, n.yara_no, min(b.saat) AS evre_saat
FROM by_kayit b JOIN yara_no n USING (itemid) JOIN kohort k USING (stay_id)
GROUP BY 1, 2, 3
""")
con.execute("""
CREATE TEMP TABLE yara_tarih AS
SELECT t.stay_id, t.yara_no, min(t.tespit_saat) AS tespit_saat
FROM tespit_ham t JOIN kohort k USING (stay_id)
GROUP BY 1, 2
""")

# ---- 2. Sonuc sayilari ----
# 'tanimsiz' evre kayitlari yara sayilmiyor (by_kayit disinda); asagidaki uc sutun etkisini gosterir
sonuc = con.execute(f"""
WITH ilk_by AS (
    SELECT b.stay_id, min(b.saat) AS ilk_saat,
           arg_min(b.evre, b.saat) AS ilk_evre,
           max(CASE WHEN b.evre NOT IN ('1', 'BILINMIYOR') THEN 1 ELSE 0 END) AS evre2_ustu_var,
           max(CASE WHEN b.evre <> 'BILINMIYOR' THEN 1 ELSE 0 END) AS bilinen_evre_var
    FROM by_kayit b JOIN kohort k USING (stay_id)
    WHERE b.saat >= {M} AND b.saat <= {olay_ust}
    GROUP BY 1
),
tanimsiz_by AS (
    SELECT DISTINCT b.stay_id FROM by_ham b JOIN kohort k USING (stay_id)
    WHERE b.evre = 'tanimsiz' AND b.saat >= {M} AND b.saat <= {olay_ust}
)
SELECT
    (SELECT count(*) FROM kohort) AS kohort_yatis,
    count(*) AS yeni_by_yb_suresince,
    sum(CASE WHEN ilk_saat < {P} THEN 1 ELSE 0 END) AS yeni_by_72_168,
    sum(evre2_ustu_var) AS yeni_by_evre2_ve_ustu,
    (SELECT sum(CASE WHEN yb_olum THEN 1 ELSE 0 END) FROM kohort) AS yb_olum,
    (SELECT median(yb_saat) FROM kohort) AS yb_saat_medyan,
    sum(CASE WHEN stay_id IN (SELECT stay_id FROM tanimsiz_by) THEN 1 ELSE 0 END) AS yeni_by_tanimsiz_kaydi_da_olan,
    (SELECT count(*) FROM tanimsiz_by WHERE stay_id NOT IN (SELECT stay_id FROM ilk_by)) AS yalnizca_tanimsiz_ile_yeni,
    (SELECT count(DISTINCT b.stay_id) FROM by_ham b JOIN kohort k USING (stay_id)
     WHERE b.evre = 'tanimsiz' AND b.saat < {M}) AS tanimsiz_72_oncesi_kohort_yatis,
    -- Duyarlilik: yalnizca BILINMIYOR evre kaydiyla yeni sayilan yatislar haric
    sum(bilinen_evre_var) AS yeni_by_bilinmiyor_haric
FROM ilk_by
""").df()
sonuc["tanimsiz_evre_kaydi"] = tanimsiz
sayim = [s for s in sonuc.columns if s != "yb_saat_medyan"]
sonuc[sayim] = sonuc[sayim].fillna(0).astype(int)

# Yeni basinc yarasi orani yil gruplarina gore (kohortta)
by_yil = con.execute(f"""
SELECT k.anchor_year_group,
       count(b.stay_id) AS yeni_by_yatis,
       count(*) AS kohort_yatis
FROM kohort k
LEFT JOIN (SELECT DISTINCT b.stay_id FROM by_kayit b JOIN kohort k USING (stay_id)
           WHERE b.saat >= {M} AND b.saat <= {olay_ust}) b USING (stay_id)
GROUP BY 1 ORDER BY 1
""").df()
by_yil["yuzde"] = (100 * by_yil["yeni_by_yatis"] / by_yil["kohort_yatis"]).round(1)

# ---- 3. JH-HLM kaydi yil gruplarina gore (yas >= 18 ve >= 72 saat kalanlar icinde) ----
# Payda uygun_yatis: yas >= 18 ve YB'de >= 72 saat. tum_yatis paydanin nereden geldigini gosterir.
jh_yil = con.execute(f"""
SELECT anchor_year_group, count(*) AS tum_yatis,
       sum(CASE WHEN yas >= 18 AND yb_saat >= {M} THEN 1 ELSE 0 END)::INTEGER AS uygun_yatis,
       sum(CASE WHEN yas >= 18 AND yb_saat >= {M}
                 AND stay_id IN (SELECT stay_id FROM jh WHERE saat >= 0 AND saat < {M})
                THEN 1 ELSE 0 END)::INTEGER AS jh_kayitli
FROM yatis
GROUP BY 1 ORDER BY 1
""").df()
jh_yil["yuzde"] = (100 * jh_yil["jh_kayitli"] / jh_yil["uygun_yatis"]).round(1)

# ---- 4. Braden: 72. saatten once tam (6 alt boyutlu) set ----
br = con.execute(f"""
SELECT e.stay_id, e.charttime, e.itemid, e.value
FROM chartevents e JOIN kohort k USING (stay_id)
WHERE e.itemid IN ({','.join(map(str, BRADEN_ITEMID))})
  AND date_diff('minute', k.intime, e.charttime) / 60.0 < {M}
""").df()
if len(br):
    br["alt"] = br["itemid"].map(BRADEN_ITEMID)
    br["puan"] = [braden_puan(a_, v) for a_, v in zip(br["alt"], br["value"])]
    genis = br.pivot_table(index=["stay_id", "charttime"], columns="alt",
                           values="puan", aggfunc="last").reset_index()
    tam = genis.dropna(subset=list(BRADEN_ITEMID.values()))
    son = tam.sort_values("charttime").groupby("stay_id").tail(1).copy()
    son["toplam"] = son[list(BRADEN_ITEMID.values())].sum(axis=1)
    son["mobilite_disi"] = son[BRADEN_MOBILITE_DISI].sum(axis=1)
    braden = pd.DataFrame([{
        "kohort_yatis": int(sonuc["kohort_yatis"].iloc[0]),
        "tam_setli_yatis": len(son),
        "toplam_medyan": son["toplam"].median(),
        "toplam_q1": son["toplam"].quantile(.25),
        "toplam_q3": son["toplam"].quantile(.75),
        "mobilite_disi_medyan": son["mobilite_disi"].median(),
    }])
else:
    braden = pd.DataFrame([{"kohort_yatis": int(sonuc["kohort_yatis"].iloc[0]), "tam_setli_yatis": 0}])

# ---- 5. Bakim plani gorunurlugu (kohortta, yatis boyunca) ----
ncp = con.execute(f"""
SELECT g.degisken_grubu, count(DISTINCT e.stay_id) AS plan_kayitli_yatis,
       (SELECT count(*) FROM kohort) AS kohort_yatis
FROM chartevents e
JOIN kohort k USING (stay_id)
JOIN (SELECT * FROM (VALUES
        {','.join(f"({i}, '{g}')" for g, i in it.loc[it['degisken_grubu'].str.startswith('ncp_'), ['degisken_grubu', 'itemid']].itertuples(index=False)) or "(-1, 'yok')"}
     ) t(itemid, degisken_grubu)) g USING (itemid)
GROUP BY 1 ORDER BY 1
""").df()
ncp["yuzde"] = (100 * ncp["plan_kayitli_yatis"] / ncp["kohort_yatis"]).round(1)

# ---- 6. Ayni anda ayni gruptan birden fazla itemid (tum yatislarda) ----
cift_parca = []
for grup in ["jh_hlm", "tedavi_edici_yatak", "yardimci_cihaz"]:
    cift_parca.append(con.execute(f"""
    SELECT '{grup}' AS degisken_grubu,
           count(*) AS ayni_an_coklu_itemid,
           coalesce(sum(CASE WHEN n_deger > 1 THEN 1 ELSE 0 END), 0)::INTEGER AS farkli_deger
    FROM (SELECT stay_id, charttime, count(DISTINCT value) AS n_deger
          FROM chartevents WHERE itemid IN ({ids(grup)})
          GROUP BY 1, 2 HAVING count(DISTINCT itemid) > 1)
    """).df())
cift = pd.concat(cift_parca, ignore_index=True)

# ---- 7. Tespit tarihi kontrolu (kohortta, yeni sayilan yaralar; yara_evre ve yara_tarih yukarida) ----
# Tespit tarihi 72. saatten once olanlar kohortta dislandigi icin tespit_72_oncesi_yatis artik 0 olmali.
tespit = con.execute(f"""
WITH yeni AS (SELECT * FROM yara_evre WHERE evre_saat >= {M} AND evre_saat <= {sinir}),
tarih AS (SELECT * FROM yara_tarih)
SELECT 'yeni (Pressure ulcer #N- Stage)' AS sablon, 'yara #N ile' AS eslestirme,
       count(DISTINCT v.stay_id) AS yeni_by_yatis,
       count(DISTINCT CASE WHEN t.tespit_saat IS NOT NULL THEN v.stay_id END) AS tespit_tarihi_dolu_yatis,
       count(DISTINCT CASE WHEN t.tespit_saat < {M} THEN v.stay_id END) AS tespit_72_oncesi_yatis
FROM yeni v LEFT JOIN tarih t USING (stay_id, yara_no)
WHERE v.degisken_grubu = 'by_evre_yeni'
UNION ALL
SELECT 'eski (Pressure Ulcer Stage #N)', 'yok (yatis duzeyi)',
       count(DISTINCT v.stay_id),
       count(DISTINCT CASE WHEN v.stay_id IN (SELECT stay_id FROM tarih WHERE tespit_saat IS NOT NULL)
                           THEN v.stay_id END),
       NULL::BIGINT
FROM yeni v
WHERE v.degisken_grubu = 'by_evre_eski'
""").df()
# Uzun bicim: eski sablonda eslestirme olmadigi icin 72 saat olcusu yok, o satir yazilmaz
tespit = (tespit.melt(id_vars=["sablon", "eslestirme"], var_name="olcu", value_name="yatis").dropna()
          .sort_values("sablon", ascending=False, kind="stable"))
tespit["yatis"] = tespit["yatis"].astype(int)

# ---- 8. Eski sablon ve JH-HLM ayni yatista (tum yatislarda) ----
# by_ham: eski sablonun her kaydi ("Not applicable" dahil); by_kayit: yalnizca yara kaydi
eski_jh = con.execute(f"""
SELECT count(DISTINCT stay_id) AS eski_sablon_kayitli_yatis,
       count(DISTINCT CASE WHEN stay_id IN (SELECT stay_id FROM jh) THEN stay_id END) AS eski_sablon_ve_jhhlm_yatis,
       (SELECT count(DISTINCT stay_id) FROM by_kayit
        WHERE itemid IN ({ids('by_evre_eski')}) AND stay_id IN (SELECT stay_id FROM jh)) AS eski_sablon_yara_ve_jhhlm_yatis
FROM by_ham WHERE itemid IN ({ids('by_evre_eski')})
""").df()

# ---- 9. Tutarlilik: onceki tanimla yeni sayilip eslestirmeli tespit tarihi < 72 olanlar ----
# Onceki tanim: BILINMIYOR yara sayilmaz (dislamada da sonucta da), tespit tarihi adimi yok.
# A: bu yatislar (yeni sablon evre #N ile tespit tarihi #N). B: A'dan yeni kohortta kalan; 0 olmali.
con.execute("""
CREATE TEMP TABLE by_kayit_onceki AS
SELECT * FROM by_ham WHERE evre IS NOT NULL AND evre NOT IN ('tanimsiz', 'BILINMIYOR')
""")
onceki_kosul = " AND ".join(k for _, k in adimlar[:5])  # yas, YB suresi, JH-HLM, kabulde yara
con.execute(f"""
CREATE TEMP TABLE kohort_onceki AS
SELECT stay_id FROM yatis
WHERE {onceki_kosul}
  AND stay_id NOT IN (SELECT stay_id FROM by_kayit_onceki WHERE saat < {M})
""")
tutarlilik = con.execute(f"""
WITH yara_onceki AS (
    SELECT b.stay_id, n.yara_no, min(b.saat) AS evre_saat
    FROM by_kayit_onceki b JOIN yara_no n USING (itemid) JOIN kohort_onceki USING (stay_id)
    WHERE n.degisken_grubu = 'by_evre_yeni'
    GROUP BY 1, 2
),
a AS (
    SELECT DISTINCT v.stay_id
    FROM yara_onceki v JOIN tespit_ham t USING (stay_id, yara_no)
    WHERE v.evre_saat >= {M} AND v.evre_saat <= {sinir} AND t.tespit_saat < {M}
)
SELECT count(*) AS a_onceki_yeni_tespit_72_oncesi,
       count(*) FILTER (WHERE stay_id IN (SELECT stay_id FROM kohort)) AS b_yeni_kohortta_kalan
FROM a
""").df()

# ---- 10. Uzlastirma: onceki tanim ile birincil tanim arasinda yeni BY gecisi ----
# Onceki tanim 9. bolumdeki gibi ("Unknown", "Unable to assess", "Status Changed" o zaman 'tanimsiz'di
# ve yara sayilmiyordu; tespit tarihi adimi yok). Neden, birincil kohort adimlarinin sirasiyla atanir.
gecis = con.execute(f"""
WITH onceki AS (
    SELECT DISTINCT b.stay_id FROM by_kayit_onceki b JOIN kohort_onceki USING (stay_id) JOIN yatis k USING (stay_id)
    WHERE b.saat >= {M} AND b.saat <= {olay_ust}
), simdi AS (
    SELECT DISTINCT b.stay_id FROM by_kayit b JOIN kohort k USING (stay_id)
    WHERE b.saat >= {M} AND b.saat <= {olay_ust}
), sinif AS (
    SELECT CASE
        WHEN o.stay_id IS NOT NULL AND s.stay_id IS NOT NULL THEN 'her iki tanimda yeni|'
        WHEN o.stay_id IS NOT NULL THEN 'yalnizca onceki tanimda yeni|' || CASE
            WHEN o.stay_id IN (SELECT stay_id FROM by_kayit WHERE saat < {M} AND evre = 'BILINMIYOR')
                THEN 'BILINMIYOR 0-72 dislamasi'
            WHEN o.stay_id IN (SELECT stay_id FROM tespit_erken) THEN 'tespit tarihi'
            ELSE 'diger' END
        ELSE 'yalnizca birincil tanimda yeni|' || CASE
            WHEN s.stay_id NOT IN (SELECT b.stay_id FROM by_kayit b JOIN kohort k USING (stay_id)
                                   WHERE b.evre <> 'BILINMIYOR' AND b.saat >= {M} AND b.saat <= {olay_ust})
                THEN 'yalnizca BILINMIYOR kaydi'
            ELSE 'diger' END
    END AS anahtar
    FROM onceki o FULL OUTER JOIN simdi s ON o.stay_id = s.stay_id
)
SELECT anahtar, count(*) AS yatis FROM sinif GROUP BY 1
""").df()
# Tum satirlar (0 olanlar dahil) sabit sirada; Status Changed iki tanimda da yara degil, yapisi geregi 0
satir_sirasi = ["her iki tanimda yeni|",
                "yalnizca onceki tanimda yeni|tespit tarihi",
                "yalnizca onceki tanimda yeni|BILINMIYOR 0-72 dislamasi",
                "yalnizca onceki tanimda yeni|Status Changed",
                "yalnizca onceki tanimda yeni|diger",
                "yalnizca birincil tanimda yeni|yalnizca BILINMIYOR kaydi",
                "yalnizca birincil tanimda yeni|diger"]
gecis = gecis.set_index("anahtar").reindex(satir_sirasi, fill_value=0).reset_index()
gecis[["gecis", "neden"]] = gecis["anahtar"].str.split("|", expand=True)
gecis = gecis[["gecis", "neden", "yatis"]]
n_her_iki = int(gecis.loc[gecis["gecis"] == "her iki tanimda yeni", "yatis"].sum())
toplam_onceki = n_her_iki + int(gecis.loc[gecis["gecis"].str.startswith("yalnizca onceki"), "yatis"].sum())
toplam_birincil = n_her_iki + int(gecis.loc[gecis["gecis"].str.startswith("yalnizca birincil"), "yatis"].sum())
gecis = pd.concat([gecis, pd.DataFrame([
    {"gecis": "toplam", "neden": "onceki tanim", "yatis": toplam_onceki},
    {"gecis": "toplam", "neden": "birincil tanim", "yatis": toplam_birincil}])], ignore_index=True)
gecis["yatis"] = gecis["yatis"].astype(int)

# ---- Birincil kohort ve sonuc zamanlari (05_analiz_seti.py icin; yalnizca ozel) ----
con.execute(f"""
COPY (
    SELECT k.subject_id, k.hadm_id, k.stay_id, k.intime, k.outtime, k.anchor_year_group, k.yas,
           k.yb_saat, k.yb_olum, k.first_careunit,
           min(b.saat) AS ilk_by_saat,
           min(CASE WHEN b.evre NOT IN ('1', 'BILINMIYOR') THEN b.saat END) AS ilk_evre2_saat,
           min(CASE WHEN b.evre <> 'BILINMIYOR' THEN b.saat END) AS ilk_bilinen_by_saat
    FROM kohort k
    LEFT JOIN by_kayit b ON b.stay_id = k.stay_id AND b.saat >= {M} AND b.saat <= {sinir}
    GROUP BY ALL
) TO '{(ozel / "04_kohort.parquet").as_posix()}' (FORMAT PARQUET)
""")

# ---- Kaydet ----
tablolar = {
    "04a_kohort_akisi": (akis, ["yatis", "hasta", "dislanan"]),
    "04b_sonuc_sayilari": (sonuc, ["kohort_yatis", "yeni_by_yb_suresince", "yeni_by_72_168",
                                   "yeni_by_evre2_ve_ustu", "yb_olum", "yeni_by_tanimsiz_kaydi_da_olan",
                                   "yalnizca_tanimsiz_ile_yeni", "tanimsiz_72_oncesi_kohort_yatis",
                                   "yeni_by_bilinmiyor_haric", "tanimsiz_evre_kaydi"]),
    "04b2_yeni_by_yil": (by_yil, ["yeni_by_yatis", "kohort_yatis"]),
    "04c_jhhlm_yil": (jh_yil, ["tum_yatis", "uygun_yatis", "jh_kayitli"]),
    "04d_braden": (braden, ["kohort_yatis", "tam_setli_yatis"]),
    "04e_bakim_plani_gorunurlugu": (ncp, ["plan_kayitli_yatis", "kohort_yatis"]),
    "04f_ayni_an_coklu_itemid": (cift, ["ayni_an_coklu_itemid", "farkli_deger"]),
    "04g_tespit_tarihi_kontrolu": (tespit, ["yatis"]),
    "04h_eski_sablon_jhhlm": (eski_jh, ["eski_sablon_kayitli_yatis", "eski_sablon_ve_jhhlm_yatis",
                                        "eski_sablon_yara_ve_jhhlm_yatis"]),
    "04i_tutarlilik_kontrolu": (tutarlilik, ["a_onceki_yeni_tespit_72_oncesi", "b_yeni_kohortta_kalan"]),
    "04j_uzlastirma": (gecis, ["yatis"]),
}
for ad, (df, sayi_sutunlari) in tablolar.items():
    df.to_csv(ozel / f"{ad}.csv", index=False, encoding="utf-8-sig")
    p = df.copy()
    sayi_sutunlari = [s for s in sayi_sutunlari if s in p.columns]
    # Kucuk hucreye ait yuzdeleri de gizle
    if "yuzde" in p.columns:
        pay = sayi_sutunlari[0] if ad != "04c_jhhlm_yil" else "jh_kayitli"
        p.loc[(p[pay] > 0) & (p[pay] < 5), "yuzde"] = None
    kucuk_hucre_gizle(p, sayi_sutunlari).to_csv(paylas / f"{ad}.csv", index=False, encoding="utf-8-sig")

print("KOHORT AKISI\n" + akis.to_string(index=False))
print("\nSONUC SAYILARI\n" + sonuc.T.to_string(header=False))
print("\nYENI BASINC YARASI YIL GRUPLARINA GORE\n" + by_yil.to_string(index=False))
print("\nJH-HLM YIL GRUPLARINA GORE\n" + jh_yil.to_string(index=False))
print("\nBRADEN\n" + braden.T.to_string(header=False))
print("\nBAKIM PLANI GORUNURLUGU\n" + ncp.to_string(index=False))
print("\nAYNI ANDA BIRDEN FAZLA ITEMID\n" + cift.to_string(index=False))
print("\nTESPIT TARIHI KONTROLU\n" + tespit.to_string(index=False))
print("\nESKI SABLON VE JH-HLM\n" + eski_jh.T.to_string(header=False))
print("\nTUTARLILIK KONTROLU (B = 0 olmali)\n" + tutarlilik.T.to_string(header=False))
print("\nUZLASTIRMA: ONCEKI TANIM -> BIRINCIL TANIM\n" + gecis.to_string(index=False))
esit = toplam_birincil == int(sonuc["yeni_by_yb_suresince"].iloc[0])
print(f"  Birincil toplam 04b'deki yeni BY sayisina esit mi: {'evet' if esit else 'HAYIR'}")

n_yeni = int(sonuc["yeni_by_yb_suresince"].iloc[0] or 0)
print("\nKARAR NOTU:")
if n_yeni < 200:
    print(f"  Yeni basinc yarasi sayisi {n_yeni}. Birincil sonuc icin dusuk olabilir; "
          "sonuc tanimini genisletmeyi hocayla konusun.")
else:
    print(f"  Yeni basinc yarasi sayisi {n_yeni}. Birincil analiz icin yeterli gorunuyor.")
print(f"\nCiktilar: {ozel} ve {paylas}")
