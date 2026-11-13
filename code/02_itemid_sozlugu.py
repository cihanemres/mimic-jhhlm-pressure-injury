"""Adim 2: Calismada kullanilacak degiskenlerin itemid adaylarini bulur.

d_items (ve laboratuvar icin d_labitems) tablosunda anahtar kelimelerle arama yapar
ve her adayin bagli oldugu tablodaki kayit sayisini ekler.
Laboratuvar satirlarinda 'abbreviation' sutununda fluid, 'yatis_sayisi' sutununda
hastane yatisi (hadm_id) sayisi vardir.

Cikti: <cikti>/ozel/itemid_adaylari.csv (kayit ve yatis sayilariyla; incelerken bakmak icin)
       <cikti>/ozel/itemid_onay_sablonu.csv (degisken_grubu, itemid, label, linksto, onay, gerekce;
       sayi sutunu yok)
       <cikti>/paylasilabilir/itemid_adaylari.csv (kucuk hucreler gizli)
       <cikti>/paylasilabilir/yeni_itemid_adaylari.csv (onay dosyasi varsa;
       config/itemids_onayli.csv'de hic yer almayan adaylar)
Onay dosyasi SABLONDAN uretilir: itemid_onay_sablonu.csv'yi acin, her satiri
(gerekirse itemid_adaylari.csv'deki sayilara bakarak) elle kontrol edin,
kullanilacak satirlarin 'onay' sutununa 1 yazin, 'gerekce'yi doldurun ve dosyayi
config/itemids_onayli.csv olarak kaydedin. itemid_adaylari.csv'yi onay dosyasi
olarak kaydetmeyin: kayit/yatis sayilari depoya ve makalenin ekine girmemeli.
Bu tablo makalenin ekine girecek.

Kullanim:
    python code/02_itemid_sozlugu.py --veri <MIMIC_DIR>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurallar import ARAMA_KALIPLARI, ARAMA_KALIPLARI_LAB  # noqa: E402
from mimic_db import arguman_al, baglan, cikti_klasorleri, kucuk_hucre_gizle  # noqa: E402

import pandas as pd  # noqa: E402

a = arguman_al("itemid aday sozlugu")
con = baglan(a.veri, a.bellek)
ozel, paylas = cikti_klasorleri(a.cikti)

d = con.execute(
    "SELECT itemid, label, abbreviation, category, param_type, linksto FROM d_items"
).df()

parcalar = []
for grup, kalip in ARAMA_KALIPLARI.items():
    eslesen = d[d["label"].str.contains(kalip, case=False, regex=True, na=False)].copy()
    eslesen.insert(0, "degisken_grubu", grup)
    parcalar.append(eslesen)
# Laboratuvar: d_labitems, yalnizca kan (fluid = 'Blood')
dl = con.execute("SELECT itemid, label, fluid, category FROM d_labitems WHERE fluid = 'Blood'").df()
for grup, kalip in ARAMA_KALIPLARI_LAB.items():
    eslesen = dl[dl["label"].str.contains(kalip, case=False, regex=True, na=False)].copy()
    eslesen = eslesen.rename(columns={"fluid": "abbreviation"}).assign(param_type=None, linksto="labevents")
    eslesen.insert(0, "degisken_grubu", grup)
    parcalar.append(eslesen[["degisken_grubu"] + list(d.columns)])
aday = pd.concat(parcalar, ignore_index=True)

# Kayit sayilari. labevents'te stay_id yok: yatis_sayisi orada hastane yatisi (hadm_id) sayisidir.
sayimlar = []
for tablo in ["chartevents", "datetimeevents", "inputevents", "procedureevents", "outputevents", "labevents"]:
    ids = aday.loc[aday["linksto"] == tablo, "itemid"].unique().tolist()
    yatis = "hadm_id" if tablo == "labevents" else "stay_id"
    if ids:
        sayimlar.append(con.execute(
            f"""SELECT itemid, count(*) AS kayit_sayisi, count(DISTINCT {yatis}) AS yatis_sayisi
                FROM {tablo} WHERE itemid IN ({','.join(map(str, ids))})
                GROUP BY itemid"""
        ).df())
if sayimlar:
    aday = aday.merge(pd.concat(sayimlar), on="itemid", how="left")
else:
    aday["kayit_sayisi"] = 0
    aday["yatis_sayisi"] = 0
aday[["kayit_sayisi", "yatis_sayisi"]] = aday[["kayit_sayisi", "yatis_sayisi"]].fillna(0).astype(int)
aday["onay"] = ""

aday = aday.sort_values(["degisken_grubu", "kayit_sayisi"], ascending=[True, False])
yol = ozel / "itemid_adaylari.csv"
aday.to_csv(yol, index=False, encoding="utf-8-sig")
sablon = aday[["degisken_grubu", "itemid", "label", "linksto", "onay"]].assign(gerekce="")
sablon.to_csv(ozel / "itemid_onay_sablonu.csv", index=False, encoding="utf-8-sig")
aday_p =kucuk_hucre_gizle(aday, ["kayit_sayisi", "yatis_sayisi"])
aday_p.to_csv(paylas / "itemid_adaylari.csv", index=False, encoding="utf-8-sig")

print(f"{len(aday)} aday itemid bulundu -> {yol}")

# Onay dosyasinda hic yer almayan (henuz incelenmemis) adaylar
onayli = Path("config/itemids_onayli.csv")
if onayli.exists():
    gorulen = pd.read_csv(onayli)[["degisken_grubu", "itemid"]].drop_duplicates()
    yeni = aday_p.merge(gorulen, on=["degisken_grubu", "itemid"], how="left", indicator=True)
    yeni = yeni[yeni["_merge"] == "left_only"].drop(columns="_merge")
    yeni.to_csv(paylas / "yeni_itemid_adaylari.csv", index=False, encoding="utf-8-sig")
    print(f"Onay dosyasinda olmayan {len(yeni)} yeni aday -> {paylas / 'yeni_itemid_adaylari.csv'}")
print(aday.groupby("degisken_grubu").agg(itemid=("itemid", "count"),
                                          kayit=("kayit_sayisi", "sum")).to_string())
