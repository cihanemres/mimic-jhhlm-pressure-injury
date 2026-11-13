"""Adim 3: On veri denetimi.

Onaylanan her itemid icin:
  - kayit, yatis ve hasta sayisi, ilk/son kayit zamani, valuenum doluluk orani
  - yil gruplarina (anchor_year_group) gore kayit bulunan yatis orani
  - en sik degerler
  - kurallar.py'deki donusume uymayan degerler (JH-HLM, Braden, basinc yarasi evresi)

Itemid kaynagi: config/itemids_onayli.csv (onay=1 olan satirlar).
Bu dosya yoksa 02 adiminin aday listesi kullanilir (yalnizca deneme icin).

Kullanim:
    python code/03_on_denetim.py --veri <MIMIC_DIR>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurallar import BRADEN_ITEMID, braden_puan, by_evre, jh_hlm_sayi  # noqa: E402
from mimic_db import arguman_al, baglan, cikti_klasorleri, kucuk_hucre_gizle  # noqa: E402

import pandas as pd  # noqa: E402

a = arguman_al("On veri denetimi")
con = baglan(a.veri, a.bellek)
ozel, paylas = cikti_klasorleri(a.cikti)

# ---- 1. Onayli itemid listesi ----
onayli = Path("config/itemids_onayli.csv")
if onayli.exists():
    it = pd.read_csv(onayli)
    if {"kayit_sayisi", "yatis_sayisi"} & set(it.columns):
        print("UYARI: config/itemids_onayli.csv kayit_sayisi/yatis_sayisi sutunu iceriyor. Bu sutunlari silin "
              "(depoya girmemeli); onay dosyasini ozel/itemid_onay_sablonu.csv'den uretin.")
    it = it[pd.to_numeric(it["onay"], errors="coerce") == 1]  # bos onay varsa sutun ondalik okunur
    print(f"Onayli liste kullaniliyor: {len(it)} itemid")
else:
    it = pd.read_csv(ozel / "itemid_adaylari.csv")
    it = it[it["kayit_sayisi"] > 0]
    print("UYARI: config/itemids_onayli.csv yok. Aday listesi kullaniliyor (yalnizca deneme icin).")
con.register("it", it[["degisken_grubu", "itemid", "label", "linksto"]])

# ---- 2. Itemid ozeti ----
ozet_parca = []
for tablo in ["chartevents", "datetimeevents"]:
    ids = it.loc[it["linksto"] == tablo, "itemid"].tolist()
    if not ids:
        continue
    num = "avg(CASE WHEN e.valuenum IS NOT NULL THEN 1 ELSE 0 END)" if tablo == "chartevents" else "NULL"
    ozet_parca.append(con.execute(f"""
        SELECT it.degisken_grubu, e.itemid, it.label,
               count(*) AS kayit, count(DISTINCT e.stay_id) AS yatis,
               count(DISTINCT e.subject_id) AS hasta,
               min(e.charttime) AS ilk_kayit, max(e.charttime) AS son_kayit,
               {num} AS valuenum_dolu_orani,
               string_agg(DISTINCT e.valueuom, '; ') AS birim
        FROM {tablo} e JOIN it USING (itemid)
        GROUP BY ALL""").df())
ozet = pd.concat(ozet_parca).sort_values(["degisken_grubu", "kayit"], ascending=[True, False])
ozet.to_csv(ozel / "03a_itemid_ozeti.csv", index=False, encoding="utf-8-sig")
kucuk_hucre_gizle(ozet.drop(columns=["ilk_kayit", "son_kayit"]),
                  ["kayit", "yatis", "hasta"]).to_csv(
    paylas / "03a_itemid_ozeti.csv", index=False, encoding="utf-8-sig")

# ---- 3. Yil gruplarina gore: degisken grubunda kaydi olan yatis orani ----
yil = con.execute("""
    WITH yatis AS (
        SELECT s.stay_id, p.anchor_year_group
        FROM icustays s JOIN patients p USING (subject_id)
    ),
    kayitli AS (
        SELECT DISTINCT it.degisken_grubu, e.stay_id
        FROM chartevents e JOIN it USING (itemid)
        UNION
        SELECT DISTINCT it.degisken_grubu, e.stay_id
        FROM datetimeevents e JOIN it USING (itemid)
    ),
    payda AS (SELECT anchor_year_group, count(*) AS toplam_yatis FROM yatis GROUP BY 1)
    SELECT k.degisken_grubu, y.anchor_year_group,
           count(*) AS kayitli_yatis, pd.toplam_yatis,
           round(100.0 * count(*) / pd.toplam_yatis, 1) AS yuzde
    FROM kayitli k JOIN yatis y USING (stay_id)
    JOIN payda pd USING (anchor_year_group)
    GROUP BY k.degisken_grubu, y.anchor_year_group, pd.toplam_yatis
    ORDER BY 1, 2""").df()
yil.to_csv(ozel / "03b_yil_gruplarina_gore.csv", index=False, encoding="utf-8-sig")
yil_p = yil.copy()
yil_p.loc[(yil_p["kayitli_yatis"] > 0) & (yil_p["kayitli_yatis"] < 5), "yuzde"] = None
kucuk_hucre_gizle(yil_p, ["kayitli_yatis", "toplam_yatis"]).to_csv(
    paylas / "03b_yil_gruplarina_gore.csv", index=False, encoding="utf-8-sig")

# ---- 4. En sik degerler ----
deger = con.execute("""
    SELECT it.degisken_grubu, e.itemid, it.label, e.value, count(*) AS n
    FROM chartevents e JOIN it USING (itemid)
    GROUP BY it.degisken_grubu, e.itemid, it.label, e.value
    QUALIFY row_number() OVER (PARTITION BY e.itemid ORDER BY count(*) DESC) <= 20
    ORDER BY 1, 2, n DESC""").df()
deger.to_csv(ozel / "03c_en_sik_degerler.csv", index=False, encoding="utf-8-sig")
kucuk_hucre_gizle(deger, ["n"]).to_csv(
    paylas / "03c_en_sik_degerler.csv", index=False, encoding="utf-8-sig")

# ---- 5. Donusum kurallarina uymayan degerler ----
tum = con.execute("""
    SELECT it.degisken_grubu, e.itemid, e.value, count(*) AS n
    FROM chartevents e JOIN it USING (itemid)
    WHERE it.degisken_grubu IN ('jh_hlm', 'braden_alt', 'by_evre_eski', 'by_evre_yeni')
    GROUP BY ALL""").df()


def uyuyor_mu(r):
    if r["degisken_grubu"] == "jh_hlm":
        return jh_hlm_sayi(r["value"]) is not None
    if r["degisken_grubu"] == "braden_alt":
        alt = BRADEN_ITEMID.get(int(r["itemid"]))
        return alt is not None and braden_puan(alt, r["value"]) is not None
    return by_evre(r["value"]) != "tanimsiz"


tum["kurala_uygun"] = tum.apply(uyuyor_mu, axis=1)
uymayan = tum[~tum["kurala_uygun"]].sort_values("n", ascending=False)
uymayan.to_csv(ozel / "03d_kurala_uymayan_degerler.csv", index=False, encoding="utf-8-sig")
# Paylasilabilir kopya: serbest metin riskine karsi n < 5 satirlar tamamen atilir
uymayan.loc[uymayan["n"] >= 5, ["degisken_grubu", "itemid", "value", "n"]].to_csv(
    paylas / "03d_kurala_uymayan_degerler.csv", index=False, encoding="utf-8-sig")

# Evre donusumunun ozeti
evre = tum[tum["degisken_grubu"].str.startswith("by_evre")].copy()
evre["evre"] = evre["value"].map(by_evre).fillna("yara_degil")
evre_ozet = evre.groupby(["degisken_grubu", "evre"], as_index=False)["n"].sum()
evre_ozet.to_csv(ozel / "03e_evre_donusumu.csv", index=False, encoding="utf-8-sig")
kucuk_hucre_gizle(evre_ozet, ["n"]).to_csv(
    paylas / "03e_evre_donusumu.csv", index=False, encoding="utf-8-sig")

print("\nDegisken gruplarina gore kayitli yatis sayisi:")
print(ozet.groupby("degisken_grubu")["yatis"].max().to_string())
print("\nEvre donusumu:")
print(evre_ozet.to_string(index=False))
print(f"\nKurala uymayan farkli deger sayisi: {len(uymayan)}")
if len(uymayan):
    print(uymayan.head(15).to_string(index=False))
print(f"\nCiktilar: {ozel} ve {paylas}")
