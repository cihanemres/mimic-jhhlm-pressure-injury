"""Adim 8 (Faz 4): Kesfedici kumeleme. 0-72 saat JH-HLM yorungelerinin Gaussian Mixture ile kumelenmesi.

Girdi: --veri (chartevents, JH-HLM kayitlari), <cikti>/ozel/04_kohort.parquet (04), <cikti>/ozel/analiz_seti.parquet
(05), <cikti>/ozel/06_atanmis_veri.csv.gz (06; kume -> yeni BY Cox modeli icin).
Tum ciktilarda analiz_tipi = kesfedici. Paylasilabilir ciktilarda kucuk hucre gizli ve tamamlayici gizleme var.

Yorunge: 0-72 saat 6 adet 12 saatlik blok; her blokta JH-HLM en yuksek duzey (ayni anda celiskili kayitta en
yuksek). Kayitsiz blok bir onceki blogun degerini alir (ileri tasima); bastaki bos bloklar ilk dolu blogun degerini.

Ciktilar (paylasilabilir):
    08a_yorunge_doldurma.csv     blok bazinda kayitli / doldurulan yatis; yatis basina doldurulan blok sayisi
    08b_k_secimi.csv             k = 2-6: BIC, kume buyuklukleri, kume bazinda ortalama bootstrap Jaccard, secilen k
    08c_kume_yorunge.csv/.png/.svg  secilen k icin kume bazinda ortalama yorunge ve %95 GA (tek tek yatis yok);
                                 ad_onerisi (kurala dayali oneri) ve ad_onayli (config/kume_adlari.csv) sutunlari
    08d_tablo1_kume.csv          kumelere gore Tablo 1 (06a bicimi)
    08d2_kume_sonuc_ozeti.csv    kumelere gore yeni BY (28 gun), 72-168 saat yeni BY, bakim plani gorulme orani
                                 (0-72 saat ve YB suresince, ayri sutunlar)
    08e_kume_cox.csv             kume -> yeni BY: birincil Cox ile ayni karistiricilar ve strata, 06'nin MICE
                                 atamalari, Rubin; referans kume_1 (ortalama yorungesi en dusuk kume)
    08f_kumulatif_insidans.csv/.png/.svg  kumelere gore Aalen-Johansen (06c ile ayni olay tanimi)
    08g_k3_duyarlilik.csv        duyarlilik, k = 3: kume buyuklukleri, ortalama yorunge, kume Cox HR
    08h_kume_donem_hr.csv        kume Cox, takip 72-168 saat ve >168 saat; donem x kume etkilesimi
    08z_hatalar.csv
Tablolar arasi gizleme (istatistik_ortak): Tablo 1'de gizlenen sonuc hucresini geri hesaplatan sayilar 08e, 08f
ve 08h'de de gizlenir; o kumenin kumulatif insidans egrisi cizilmez.
Yalnizca ozel: 08_kumeler.parquet (yatis duzeyinde yorunge ve kume).

Kullanim:
    python code/08_kumeleme.py --veri <MIMIC_DIR> --cikti outputs_tam
    python code/08_kumeleme.py --veri <MIMIC_DIR> --cikti outputs_tam --k 4   (k elle secilirse)
"""
import sys
import warnings
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from istatistik_ortak import (SONUC_KORUNAN, aalen_johansen, capraz_gizle, cif_noktada,  # noqa: E402
                              kumulatif_insidans_capraz, rubin, sonuc_gizli_gruplar, tablo1, tablo1_fark_gizle)
from kurallar import IDARI_SANSUR_GUN, MARUZIYET_SAAT, SEYREK_BIRIM, jh_hlm_sayi  # noqa: E402
from mimic_db import arguman_al, baglan, cikti_klasorleri, kucuk_hucre_gizle  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from lifelines import CoxPHFitter  # noqa: E402
from scipy import stats  # noqa: E402
from sklearn.mixture import GaussianMixture  # noqa: E402


def ek_arguman(p):
    p.add_argument("--k", type=int, default=None, help="Kume sayisini elle sec (varsayilan: kurala gore)")
    p.add_argument("--bootstrap-kume", type=int, default=200, help="Kume kararliligi icin bootstrap tekrar sayisi")
    p.add_argument("--bootstrap", type=int, default=1000, help="Kumulatif insidans GA icin bootstrap tekrar sayisi")
    p.add_argument("--tohum", type=int, default=2026, help="Rastgele sayi tohumu")


a = arguman_al("Kesfedici kumeleme", ek_arguman)
con = baglan(a.veri, a.bellek)
ozel, paylas = cikti_klasorleri(a.cikti)
rng = np.random.default_rng(a.tohum)
for eski in [*paylas.glob("08*"), *ozel.glob("08*")]:
    eski.unlink(missing_ok=True)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", module="lifelines")  # yakinsama uyarilari; hata olursa 08z'ye yazilir

try:
    from duckdb.sqltypes import INTEGER, VARCHAR
except ImportError:
    from duckdb.typing import INTEGER, VARCHAR
con.create_function("jh_hlm", jh_hlm_sayi, [VARCHAR], INTEGER, null_handling="special")

# ---------------------------------------------------------------
# Tanimlar (README "Kesfedici kumeleme (08)" bolumunde raporlanir)
# ---------------------------------------------------------------
TIP = "kesfedici"
BLOK_SAAT = 12
N_BLOK = MARUZIYET_SAAT // BLOK_SAAT  # 6
BLOKLAR = [f"blok_{i * BLOK_SAAT}_{(i + 1) * BLOK_SAAT}" for i in range(N_BLOK)]
K_ARALIK = range(2, 7)
EN_KUCUK_KUME = 0.05
# JH-HLM 1-8 tamsayi; her kume tek bir noktaya cokup varyansi sifira inmesin diye kovaryansa 1/12 eklenir
# (tamsayiya yuvarlanmis surekli degiskenin yuvarlama varyansi)
REG_COVAR = 1 / 12
STRATA = "ilk_yb_birimi"
GUN = np.array([1, 3, 7, 14, 21, 25])  # 72. saatten sonraki gun (06c ile ayni; 25. gun = 28. gun)
DONEM = 96  # 72. saatten sonraki 96. saat = YB'deki 168. saat (06j ile ayni bolme)
NCP = ["ncp_impaired_mobility", "ncp_activity_intolerance", "ncp_skin_integrity"]
# Arastirmacilarin verdigi kume adlari (config/kume_adlari.csv; 09 da ayni dosyayi okur). Yalnizca k ve tum kume
# buyuklukleri dosyadaki yatis sayilariyla ayniysa kullanilir; cozum degisirse ad_onayli bos kalir ve adlar
# yeniden verilmelidir.
_ka = Path("config/kume_adlari.csv")
KUME_ADLARI = (pd.read_csv(_ka, encoding="utf-8-sig") if _ka.exists()
               else pd.DataFrame(columns=["k", "kume", "yatis", "ad_tr"]))
satir_hata = []


def hata_kaydet(analiz, e):
    print(f"  [HATA] {analiz}: {type(e).__name__}: {e}")
    satir_hata.append({"analiz": analiz, "hata": f"{type(e).__name__}: {e}"})


def tek_gizliyi_tamamla(df, sutun, gruplar):
    """Toplami bilinen bir grupta tek gizli hucre kalirsa en kucuk ikinci hucreyi de 'gizli' yapar."""
    for _, g in df.groupby(gruplar) if gruplar else [(None, df)]:
        gz = g[sutun].isin(["<5", "gizli"])
        if gz.sum() == 1 and len(g) > 1:
            df.loc[pd.to_numeric(g.loc[~gz, sutun]).idxmin(), sutun] = "gizli"
    return df


def tamsayi(df, sutunlar):
    """Gizlemeden sonra sayi sutunlarini 11.0 yerine 11 yazar ("<5", "gizli" ve bos aynen kalir)."""
    for s_ in sutunlar:
        df[s_] = pd.Series([v if isinstance(v, str) or pd.isna(v) else int(v) for v in df[s_]], dtype=object,
                           index=df.index)
    return df


# ---- Onayli itemid'ler ve kohort ----
it = pd.read_csv("config/itemids_onayli.csv")
it = it[pd.to_numeric(it["onay"], errors="coerce") == 1]
jh_ids = ",".join(map(str, it.loc[it["degisken_grubu"] == "jh_hlm", "itemid"].astype(int))) or "-1"
for yol in [ozel / "04_kohort.parquet", ozel / "analiz_seti.parquet"]:
    if not yol.exists():
        raise SystemExit(f"{yol} yok. Once 04 ve 05 betiklerini calistirin.")
con.execute(f"CREATE TEMP TABLE kohort AS SELECT stay_id, intime, outtime "
            f"FROM read_parquet('{(ozel / '04_kohort.parquet').as_posix()}')")

# ---------------------------------------------------------------
# 1. Yorunge
# ---------------------------------------------------------------
blok = con.execute(f"""
WITH an AS (
    SELECT e.stay_id, e.charttime, max(jh_hlm(e.value)) AS duzey,
           date_diff('minute', k.intime, e.charttime) / 60.0 AS saat
    FROM chartevents e JOIN kohort k USING (stay_id)
    WHERE e.itemid IN ({jh_ids}) AND jh_hlm(e.value) IS NOT NULL
      AND e.charttime >= k.intime AND e.charttime < k.intime + INTERVAL {MARUZIYET_SAAT} HOUR
    GROUP BY 1, 2, 4
)
SELECT stay_id, floor(saat / {BLOK_SAAT})::INTEGER AS blok, max(duzey) AS duzey FROM an GROUP BY 1, 2
""").df()
kohort = con.execute("SELECT stay_id FROM kohort").df()
ham_y = (blok.pivot(index="stay_id", columns="blok", values="duzey")
         .reindex(index=kohort["stay_id"], columns=range(N_BLOK)).astype(float))
kayitli = ham_y.notna()
kayitsiz_yatis = int((~kayitli.any(axis=1)).sum())  # kohort tanimi geregi 0 olmali
ham_y = ham_y[kayitli.any(axis=1)]
kayitli = kayitli.loc[ham_y.index]
ileri = ham_y.ffill(axis=1)
yorunge = ileri.bfill(axis=1)
yorunge.columns = BLOKLAR

dold = []
for j, b in enumerate(BLOKLAR):
    dold.append({"analiz_tipi": TIP, "olcu": "blok", "kategori": b, "kayitli_yatis": int(kayitli[j].sum()),
                 "ileri_tasima_ile_doldurulan": int((~kayitli[j] & ileri[j].notna()).sum()),
                 "ilk_dolu_blokla_doldurulan": int(ileri[j].isna().sum())})
doldurulan_n = (~kayitli).sum(axis=1)
for n_ in range(N_BLOK):
    dold.append({"analiz_tipi": TIP, "olcu": "yatis basina doldurulan blok sayisi", "kategori": str(n_),
                 "yatis": int((doldurulan_n == n_).sum())})
dold.append({"analiz_tipi": TIP, "olcu": "0-72 saatte JH-HLM kaydi olmayan (disarida)", "kategori": "",
             "yatis": kayitsiz_yatis})
dold = pd.DataFrame(dold, columns=["analiz_tipi", "olcu", "kategori", "kayitli_yatis",
                                   "ileri_tasima_ile_doldurulan", "ilk_dolu_blokla_doldurulan", "yatis"])
d_sayi = ["kayitli_yatis", "ileri_tasima_ile_doldurulan", "ilk_dolu_blokla_doldurulan", "yatis"]
dold_p = tamsayi(kucuk_hucre_gizle(dold, d_sayi), d_sayi)
# Blok satirinda uc sutunun toplami kohort (bilinir): doldurulan toplami (kohort - kayitli) 1-4 ise kayitli da
# gizlenir; tek gizli hucre kalirsa en kucuk ikinci de gizlenir
n_y = len(yorunge)
for i in dold_p.index[dold_p["olcu"] == "blok"]:
    if 0 < n_y - dold.loc[i, "kayitli_yatis"] < 5:
        dold_p.loc[i, "kayitli_yatis"] = "gizli"
    satir = dold_p.loc[i, d_sayi[:3]]
    gz = satir.isin(["<5", "gizli"])
    if gz.sum() == 1:
        dold_p.loc[i, pd.to_numeric(satir[~gz]).astype(float).idxmin()] = "gizli"
dag = dold_p["olcu"] == "yatis basina doldurulan blok sayisi"
dold_p.loc[dag] = tek_gizliyi_tamamla(dold_p.loc[dag].copy(), "yatis", None)
tamsayi(dold_p, d_sayi).to_csv(paylas / "08a_yorunge_doldurma.csv", index=False, encoding="utf-8-sig")
print(f"Yorunge: {len(yorunge)} yatis, ortalama doldurulan blok {doldurulan_n.mean():.2f}")

# ---------------------------------------------------------------
# 2. Kumeleme: Gaussian Mixture, k = 2-6
# ---------------------------------------------------------------
Y = yorunge.to_numpy()


def gmm(k, veri, tohum, n_init=10):
    return GaussianMixture(n_components=k, covariance_type="full", reg_covar=REG_COVAR, n_init=n_init,
                           random_state=tohum).fit(veri)


def sirala(model, veri):
    """Etiketler ortalama yorunge duzeyine gore 1..k (1 = en dusuk). Donus: etiket dizisi, ortalamalar."""
    sira = np.argsort(model.means_.mean(axis=1))
    yeni = np.empty(len(sira), int)
    yeni[sira] = np.arange(1, len(sira) + 1)
    return yeni[model.predict(veri)]


def jaccard_kararlilik(k, etiket):
    """Hennig (2007) clusterboot: bootstrap ornekte yeniden kumele; ozgun her kume icin ornekteki en iyi
    eslesen kumeyle Jaccard benzerligi; tekrarlar boyunca ortalama."""
    j = np.full((a.bootstrap_kume, k), np.nan)
    for b in range(a.bootstrap_kume):
        i = rng.integers(0, len(Y), len(Y))
        u = np.unique(i)  # Jaccard ornekteki (tekrarsiz) yatislarda
        lb = gmm(k, Y[i], a.tohum + b, n_init=3).predict(Y[u])
        for c in range(1, k + 1):
            A = etiket[u] == c
            if A.any():
                j[b, c - 1] = max((A & (lb == m)).sum() / (A | (lb == m)).sum() for m in range(k))
    return np.nanmean(j, axis=0)


k_satir, modeller = [], {}
for k in K_ARALIK:
    try:
        if len(np.unique(Y, axis=0)) < k:
            raise ValueError(f"farkli yorunge sayisi ({len(np.unique(Y, axis=0))}) k'dan az")
        m = gmm(k, Y, a.tohum)
        et = sirala(m, Y)
        modeller[k] = et
        jac = jaccard_kararlilik(k, et)
        for c in range(1, k + 1):
            k_satir.append({"analiz_tipi": TIP, "k": k, "bic": m.bic(Y), "kume": f"kume_{c}",
                            "yatis": int((et == c).sum()), "yuzde": 100 * (et == c).mean(),
                            "jaccard_ortalama": jac[c - 1], "bootstrap_tekrar": a.bootstrap_kume})
        print(f"  k = {k}: BIC {m.bic(Y):.1f}, en kucuk kume %{100 * np.bincount(et)[1:].min() / len(et):.1f}")
    except Exception as e:
        hata_kaydet(f"gmm_k{k}", e)
kb = pd.DataFrame(k_satir, columns=["analiz_tipi", "k", "bic", "kume", "yatis", "yuzde", "jaccard_ortalama",
                                    "bootstrap_tekrar"])
# Secim: en kucuk kume >= %5 olan k'lar icinde en dusuk BIC (--k ile elle degistirilebilir; klinik yorum elle)
uygun = kb.groupby("k").agg(bic=("bic", "first"), en_kucuk=("yuzde", "min"))
uygun = uygun[uygun["en_kucuk"] >= 100 * EN_KUCUK_KUME]
k_kural = int(uygun["bic"].idxmin()) if len(uygun) else None
K = a.k if a.k else k_kural
kb["kurala_gore_secilen"] = kb["k"] == k_kural
kb["kullanilan_k"] = kb["k"] == K
kb_p = kucuk_hucre_gizle(kb, ["yatis"]).astype({"yatis": object})
kb_p.loc[kb_p["yatis"] == "<5", "yuzde"] = None
kb_p = tek_gizliyi_tamamla(kb_p, "yatis", ["k"])  # her k'da kume toplami kohort
kb_p.loc[kb_p["yatis"] == "gizli", "yuzde"] = None
tamsayi(kb_p, ["yatis"]).to_csv(paylas / "08b_k_secimi.csv", index=False, encoding="utf-8-sig")
print(f"Kurala gore k = {k_kural}; kullanilan k = {K}")

# ---------------------------------------------------------------
# 3. Kume tanimi: ortalama yorunge, ad onerisi ve onayli ad
# ---------------------------------------------------------------


def ad_oner(m_):
    """Kurala dayali klinik ad onerisi (JH-HLM: 1-3 yatakta/yatak kenari, 4-5 sandalye/ayakta, 6-8 yurume).
    Kesin ad config/kume_adlari.csv'de verilir."""
    erken, gec, ort = m_[:2].mean(), m_[-2:].mean(), m_.mean()
    if ort <= 2.5 and gec - erken < 1.5:
        return "yatakta kalan"
    if erken >= 6:
        return "erken yuruyen"
    if erken >= 4.5:
        return "erken mobilize olan"
    if gec - erken >= 1.5:
        return "gec mobilize olan"
    if erken - gec >= 1.5:
        return "mobilitesi azalan"
    return f"orta duzeyde sabit (JH-HLM ~{ort:.0f})"


def etiket_serisi(k):
    return pd.Series(modeller[k], index=yorunge.index, name="kume").map(lambda c: f"kume_{c}")


def kume_sirali(etiket):
    return sorted(etiket.unique(), key=lambda x: int(x.split("_")[1]))


def yorunge_tablosu(etiket, k, adlar):
    """Kume bazinda blok ortalamasi ve %95 GA (t). 5'ten az yatisli kumenin ortalamasi yazilmaz."""
    satir = []
    for c in kume_sirali(etiket):
        alt = yorunge[etiket == c].to_numpy()
        n_ = len(alt)
        ort = alt.mean(axis=0)
        se = alt.std(axis=0, ddof=1) / np.sqrt(n_) if n_ > 1 else np.full(N_BLOK, np.nan)
        tq = stats.t.ppf(.975, n_ - 1) if n_ > 1 else np.nan
        for j, b in enumerate(BLOKLAR):
            satir.append({"analiz_tipi": TIP, "k": k, "kume": c, "ad_onerisi": ad_oner(ort), "ad_onayli": adlar.get(c, ""),
                          "blok": b, "blok_bas_saat": j * BLOK_SAAT, "yatis": n_, "ortalama_jh_hlm": ort[j],
                          "alt_95": ort[j] - tq * se[j], "ust_95": ort[j] + tq * se[j]})
    yor_ = pd.DataFrame(satir)
    yor_.loc[yor_["yatis"] < 5, ["ortalama_jh_hlm", "alt_95", "ust_95"]] = np.nan
    return yor_


kume, adlar = None, {}
if K in modeller:
    kume = etiket_serisi(K)
    boyut = {c: int((kume == c).sum()) for c in kume_sirali(kume)}
    ka = KUME_ADLARI[KUME_ADLARI["k"].astype(int) == K]
    if len(ka) and dict(zip(ka["kume"], ka["yatis"].astype(int))) == boyut:
        adlar = dict(zip(ka["kume"], ka["ad_tr"]))
    elif len(ka):
        print(f"  UYARI: k = {K} kume buyuklukleri config/kume_adlari.csv ile ayni degil; ad_onayli bos birakildi")
    yor = yorunge_tablosu(kume, K, adlar)
    tamsayi(kucuk_hucre_gizle(yor, ["yatis"]), ["yatis"]).to_csv(paylas / "08c_kume_yorunge.csv", index=False,
                                                                  encoding="utf-8-sig")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = np.arange(N_BLOK) * BLOK_SAAT + BLOK_SAAT / 2
    for c, g in yor.groupby("kume", sort=False):
        if g["yatis"].iloc[0] < 5:
            continue
        ad = g["ad_onayli"].iloc[0] or g["ad_onerisi"].iloc[0]
        cizgi, = ax.plot(x, g["ortalama_jh_hlm"], "o-", label=f"{c}: {ad} (n = {g['yatis'].iloc[0]})")
        ax.fill_between(x, g["alt_95"], g["ust_95"], color=cizgi.get_color(), alpha=0.2, lw=0)
    ax.set(xlabel="YB girisinden sonraki saat (12 saatlik blok ortasi)", ylabel="JH-HLM (ortalama, %95 GA)",
           xticks=np.arange(0, MARUZIYET_SAAT + 1, BLOK_SAAT), ylim=(1, 8), title=f"JH-HLM yorunge kumeleri, k = {K}")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    for uz in ("png", "svg"):
        fig.savefig(paylas / f"08c_kume_yorunge.{uz}", dpi=300)
    plt.close(fig)
    pd.concat([yorunge, kume, doldurulan_n.rename("doldurulan_blok")], axis=1).reset_index().to_parquet(
        ozel / "08_kumeler.parquet", index=False)
else:
    hata_kaydet("kume_secimi", ValueError(f"kullanilabilir k yok (kurala gore {k_kural}, istenen {a.k})"))


def ad_bul(c):
    return adlar.get(c, "")


# ---------------------------------------------------------------
# 4. Kumelere gore Tablo 1, sonuc ve bakim plani ozeti, kumulatif insidans
# ---------------------------------------------------------------
sonuc_gizli = {}  # Tablo 1'de sonuc hucresi gizli kumeler -> diger tablolarda capraz gizleme
if kume is not None:
    ham = pd.read_parquet(ozel / "analiz_seti.parquet")
    d = ham.copy()
    for s in d.columns:  # nullable Int -> float
        if str(d[s].dtype) in ("Int32", "Int64"):
            d[s] = d[s].astype(float)
    birim_n = d[STRATA].value_counts()
    d[STRATA] = d[STRATA].where(~d[STRATA].isin(birim_n[birim_n < SEYREK_BIRIM].index), "diger")  # 06 ile ayni
    d = d.merge(kume, left_on="stay_id", right_index=True, how="inner")
    try:
        t1 = tablo1(d, "kume", "kume_1", [c for c in ham.columns if c != "stay_id"], SONUC_KORUNAN)
        t1 = tablo1_fark_gizle(t1, d, "kume", SONUC_KORUNAN)
        sonuc_gizli = sonuc_gizli_gruplar(t1, kume_sirali(kume))
        t1.insert(0, "analiz_tipi", TIP)
        t1.insert(4, "ad_onayli", t1["grup"].map(ad_bul))
        t1.to_csv(paylas / "08d_tablo1_kume.csv", index=False, encoding="utf-8-sig")

        # Bakim plani: 0-72 saat (05, analiz seti; Tablo 1) ve YB suresince (intime-outtime, bos olmayan deger).
        # 04e ise pencere ve deger filtresi olmadan yatisa bagli her kaydi sayar.
        ncp_ids = it.loc[it["degisken_grubu"].isin(NCP), ["degisken_grubu", "itemid"]]
        con.register("ncp_it", ncp_ids)
        yb_ncp = con.execute(f"""
        SELECT e.stay_id, n.degisken_grubu
        FROM chartevents e JOIN kohort k USING (stay_id) JOIN ncp_it n USING (itemid)
        WHERE e.charttime >= k.intime AND e.charttime <= k.outtime AND trim(e.value) <> ''
        GROUP BY 1, 2
        """).df()
        ozet_sec = (((t1["degisken"] == "olay_tipi") & (t1["kategori"] == "yeni_by"))
                    | (t1["degisken"].isin(["yeni_by_72_168"] + NCP) & (t1["kategori"].astype(str).isin(["1", "1.0"]))))
        ozet = t1.loc[ozet_sec, ["analiz_tipi", "degisken", "grup", "ad_onayli", "n_grup", "sayi", "yuzde"]].copy()
        ozet.insert(1, "sonuc", ozet["degisken"].map({
            "olay_tipi": f"yeni BY (72. saat - {IDARI_SANSUR_GUN}. gun, YB suresince)",
            "yeni_by_72_168": "yeni BY 72-168 saat", "ncp_impaired_mobility": "bakim plani: Impaired Mobility",
            "ncp_activity_intolerance": "bakim plani: Activity Intolerance",
            "ncp_skin_integrity": "bakim plani: Altered Skin Integrity"}))
        ozet.insert(2, "pencere", np.where(ozet["degisken"].isin(NCP), "0-72 saat", "sonuc tanimi"))
        # YB suresince: kume buyuklugu bilindigi icin sayi ve (n - sayi) 1-4 ise "<5" / "gizli";
        # kumeler arasi toplam (kohort, 04e'ye yakin) bilindigi icin tek gizli kalirsa en kucuk ikinci de gizli
        yb = []
        for plan in NCP:
            for c in kume_sirali(kume):
                n_c = int((kume == c).sum())
                sayi = int(yb_ncp.loc[yb_ncp["degisken_grubu"] == plan, "stay_id"].isin(kume.index[kume == c]).sum())
                yb.append({"degisken": plan, "grup": c, "sayi_yb_suresince": sayi, "n_": n_c})
        yb = pd.DataFrame(yb)
        yb["yuzde_yb_suresince"] = 100 * yb["sayi_yb_suresince"] / yb["n_"]
        yb_p = kucuk_hucre_gizle(yb, ["sayi_yb_suresince"]).astype({"sayi_yb_suresince": object})
        tumleyen = (yb["n_"] - yb["sayi_yb_suresince"]).between(1, 4) & (yb_p["sayi_yb_suresince"] != "<5")
        yb_p.loc[tumleyen, "sayi_yb_suresince"] = "gizli"
        for plan in NCP:
            m_ = yb_p["degisken"] == plan
            yb_p.loc[m_] = tek_gizliyi_tamamla(yb_p.loc[m_].copy(), "sayi_yb_suresince", None)
        yb_p.loc[yb_p["sayi_yb_suresince"].isin(["<5", "gizli"]), "yuzde_yb_suresince"] = np.nan
        ozet = ozet.merge(yb_p.drop(columns="n_"), on=["degisken", "grup"], how="left")
        tamsayi(ozet, ["sayi_yb_suresince"]).to_csv(paylas / "08d2_kume_sonuc_ozeti.csv", index=False,
                                                    encoding="utf-8-sig")
    except Exception as e:
        hata_kaydet("tablo1_kume", e)

    try:  # Aalen-Johansen: 1 yeni BY, 2 YB olumu, 3 canli taburculuk (yarisan), 0 idari sansur (06c ile ayni)
        d["olay_kod"] = d["olay_tipi"].map({"yeni_by": 1, "yb_olum": 2, "taburculuk": 3}).fillna(0).astype(int)
        ki_satir, egriler = [], {}
        for c in kume_sirali(kume):
            alt = d[d["kume"] == c]
            t, kod = (alt["sure_saat"] / 24).to_numpy(), alt["olay_kod"].to_numpy()
            zaman, cif = aalen_johansen(t, kod)
            boot = np.empty((a.bootstrap, len(GUN)))
            for b in range(a.bootstrap):
                i = rng.integers(0, len(t), len(t))
                boot[b] = cif_noktada(*aalen_johansen(t[i], kod[i]), GUN)
            nokta = cif_noktada(zaman, cif, GUN)
            # Egri gizli olay sayisini verir: Tablo 1'de yeni BY hucresi gizli kume cizilmez
            if len(t) >= 5 and not sonuc_gizli.get(c, set()) & {"yeni_by", "yeni_by_72_168"}:
                egriler[c] = (zaman, cif)
            for j, gun in enumerate(GUN):
                ki_satir.append({"analiz_tipi": TIP, "kume": c, "ad_onayli": ad_bul(c), "yatis": len(t),
                                 "gun_72s_sonrasi": gun, "kumulatif_insidans": nokta[j],
                                 "alt_95": np.quantile(boot[:, j], .025), "ust_95": np.quantile(boot[:, j], .975),
                                 "risk_altinda": int((t >= gun).sum()),
                                 "kumulatif_olay": int(((kod == 1) & (t <= gun)).sum())})
        ki = pd.DataFrame(ki_satir)
        ki.loc[ki["yatis"] < 5, ["kumulatif_insidans", "alt_95", "ust_95"]] = np.nan
        ki_p = kumulatif_insidans_capraz(kucuk_hucre_gizle(ki, ["yatis", "risk_altinda", "kumulatif_olay"]), "kume",
                                         sonuc_gizli, d, "kume", "sure_saat", "olay_tipi", "yeni_by_72_168")
        tamsayi(ki_p, ["yatis", "risk_altinda", "kumulatif_olay"]).to_csv(
            paylas / "08f_kumulatif_insidans.csv", index=False, encoding="utf-8-sig")
        fig, ax = plt.subplots(figsize=(6, 4.5))
        for c, (zaman, cif) in egriler.items():
            ax.step(np.concatenate([[0], zaman]), np.concatenate([[0], cif]) * 100, where="post",
                    label=f"{c}: {ad_bul(c)}" if ad_bul(c) else c)
        gizli_egri = [c for c in kume_sirali(kume) if c not in egriler]
        ax.set(xlabel="72. saatten sonraki gun", ylabel="Kumulatif insidans (%)", xlim=(0, 25),
               title="Yeni basinc yarasi, kumelere gore (Aalen-Johansen)"
                     + (f"\n(cizilmeyen, kucuk hucre: {', '.join(gizli_egri)})" if gizli_egri else ""))
        ax.legend(frameon=False, fontsize=8)
        fig.tight_layout()
        for uz in ("png", "svg"):
            fig.savefig(paylas / f"08f_kumulatif_insidans.{uz}", dpi=300)
        plt.close(fig)
    except Exception as e:
        hata_kaydet("kumulatif_insidans", e)

# ---------------------------------------------------------------
# 5. Kume -> yeni BY: cause-specific Cox, 06'nin atanmis verisi (ayni karistiricilar, strata, MICE)
#    08e: tum takip; 08h: donemlere gore (72-168 saat, >168 saat) ve donem x kume etkilesimi;
#    08g: duyarlilik, k = 3
# ---------------------------------------------------------------
at, karistirici = None, []
try:
    if kume is None:
        raise ValueError("kume yok")
    yol = ozel / "06_atanmis_veri.csv.gz"
    if not yol.exists():
        raise FileNotFoundError(f"{yol} yok; once 06_istatistik.py calistirin")
    at = pd.read_csv(yol)
    sabit_sut = ["atama", "stay_id", "subject_id", STRATA, "anchor_year_group", "sure_saat", "olay_kod_yeni_by"]
    karistirici = [c for c in at.columns if c not in sabit_sut and c not in ("jh_4_5", "jh_6_8")]
    eksik_kume = int((~at["stay_id"].isin(kume.index)).sum() / at["atama"].nunique())
    if eksik_kume:
        raise ValueError(f"atanmis verideki {eksik_kume} yatisin kumesi yok")
    at["olay"] = (at["olay_kod_yeni_by"] == 1).astype(int)
    # Donem: 72-168 saat = sure < 96 (05'teki yeni_by_72_168 ile ayni); sayma sureci baslangic < bitis ister
    at["sure_saat"] = at["sure_saat"].clip(lower=1 / 60)
except Exception as e:
    hata_kaydet("kume_cox_veri", e)
    at = None


def rubin_tablo(kats, vars_, naifler):
    """Rubin: robust (hasta kumesi) varyansla se/GA/p, naif varyansla *_naif sutunlari."""
    ortak = [t for t in kats[0].index if all(t in k_.index for k_ in kats)]
    sonuc = {"terim": ortak}
    for ek, varyans in [("", vars_), ("_naif", naifler)]:
        q, se, df = rubin([k_[ortak].to_numpy() for k_ in kats], [v_[ortak].to_numpy() for v_ in varyans])
        df = np.where(np.isfinite(df), df, 1e6)
        tq = stats.t.ppf(.975, df)
        if not ek:
            sonuc.update({"katsayi": q, "etki": np.exp(q)})
        sonuc.update({f"se{ek}": se, f"alt_95{ek}": np.exp(q - tq * se), f"ust_95{ek}": np.exp(q + tq * se),
                      f"p{ek}": 2 * stats.t.sf(np.abs(q / se), df)})
    return pd.DataFrame(sonuc)


def cox_kumeli(veri, terimler, sure, olay, strata):
    """Cox, hasta duzeyinde kumelenmis robust SE (lifelines cluster_col). Donus: katsayi, robust varyans (kosegen),
    naif varyans (kosegen). lifelines robust kovaryans matrisini saklamaz; geç giris (entry_col) ile robust SE
    dogru degildir, bu yuzden geç giris kullanilmaz."""
    cph = CoxPHFitter().fit(veri[terimler + [sure, olay, "subject_id"] + strata], duration_col=sure, event_col=olay,
                            strata=strata, cluster_col="subject_id")
    return (cph.params_, cph.standard_errors_ ** 2,
            pd.Series(np.diag(cph.variance_matrix_), index=cph.params_.index))


def kume_cox(etiket, k):
    """Tum takip. Donus: terim tablosu (kume kuklalari ve karistiricilar)."""
    kukla = [f"kume_{c}" for c in range(2, k + 1)]
    kats, vars_, naif = [], [], []
    for _, v in at.groupby("atama"):
        v = v.assign(**{c: (v["stay_id"].map(etiket) == c).astype(float) for c in kukla})
        t_ = [s for s in kukla + karistirici if v[s].nunique() > 1]
        b, u, un = cox_kumeli(v, t_, "sure_saat", "olay", [STRATA])
        kats.append(b)
        vars_.append(u)
        naif.append(un)
    r_ = rubin_tablo(kats, vars_, naif)
    r_["kume_terimi"] = r_["terim"].isin(kukla)
    return r_


def kume_sayilari(etiket):
    """Ilk atamada kume bazinda yatis ve olay; donemlere gore risk altindaki yatis ve olay."""
    v1 = at[at["atama"] == at["atama"].min()].assign(kume=lambda x: x["stay_id"].map(etiket))
    d1 = v1["sure_saat"] < DONEM
    return pd.DataFrame({
        "kume_yatis": v1.groupby("kume").size(), "kume_olay": v1.groupby("kume")["olay"].sum(),
        "d1_yatis": v1.groupby("kume").size(), "d1_olay": v1[d1].groupby("kume")["olay"].sum(),
        "d2_yatis": v1[~d1].groupby("kume").size(), "d2_olay": v1[~d1].groupby("kume")["olay"].sum(),
    }).fillna(0).astype(int)


def kume_cox_donem(etiket, k):
    """Takip 96. saatte (YB'de 168. saat) bolunur; karistiricilar iki donemde ortak. Donem 2'de zaman 96. saatten
    sayilir ve donem strataya eklenir: iki donemin zaman araliklari ayrik oldugundan risk kumeleri gec girisli bolunmus
    modelle (06j, R survSplit) aynidir; gec giris gerekmedigi icin robust SE dogru hesaplanir.
    Iki parametrelestirme: (A) kume x donem kuklalari -> donem bazinda HR; (B) kume + kume x donem 2 ->
    etkilesim (donem 2 HR / donem 1 HR) tek katsayi, robust SE dogrudan."""
    kukla = [f"kume_{c}" for c in range(2, k + 1)]
    kats, vars_, naif = [], [], []
    for _, v in at.groupby("atama"):
        v = v.assign(kume=v["stay_id"].map(etiket))
        t = v["sure_saat"]
        p1 = v.assign(sure_d=np.minimum(t, DONEM), olay_d=((t < DONEM) & (v["olay"] == 1)).astype(int), donem=1)
        v2 = v[t >= DONEM]
        p2 = v2.assign(sure_d=np.maximum(v2["sure_saat"] - DONEM, 1 / 60), olay_d=v2["olay"], donem=2)
        s_ = pd.concat([p1, p2], ignore_index=True)
        a_, b_ = [], []
        for c in kukla:
            ana = (s_["kume"] == c).astype(float)
            s_[f"{c}_d1"], s_[f"{c}_d2"] = ana * (s_["donem"] == 1), ana * (s_["donem"] == 2)
            s_[c], s_[f"{c}_etkilesim"] = ana, ana * (s_["donem"] == 2)
            a_ += [f"{c}_d1", f"{c}_d2"]
            b_ += [c, f"{c}_etkilesim"]
        q_, u_, un_ = [], [], []
        for terim in (a_, b_):
            t_ = [x for x in terim + karistirici if s_[x].nunique() > 1]
            b, u, un = cox_kumeli(s_, t_, "sure_d", "olay_d", [STRATA, "donem"])
            sec = [x for x in b.index if x.endswith(("_d1", "_d2", "_etkilesim"))]
            q_.append(b[sec])
            u_.append(u[sec])
            un_.append(un[sec])
        kats.append(pd.concat(q_))
        vars_.append(pd.concat(u_))
        naif.append(pd.concat(un_))
    r_ = rubin_tablo(kats, vars_, naif)
    r_ = r_[r_["terim"].str.match(r"kume_\d+_(d1|d2|etkilesim)$")].copy()
    r_["donem"] = r_["terim"].str.extract(r"_(d1|d2|etkilesim)$")[0].map(
        {"d1": "72-168 saat", "d2": ">168 saat", "etkilesim": "etkilesim (>168 HR / 72-168 HR)"})
    r_["kume"] = r_["terim"].str.replace(r"_(d1|d2|etkilesim)$", "", regex=True)
    return r_


def fark_riski(et_a, et_b):
    """et_a'daki kumelerden, et_b kumelerinin bir birlesimiyle 1-4 yatis farki olanlar (simetrik fark).
    Bu kumelerin olay sayisi ve ortalama yorungesi, iki cozum birlikte okununca birkac yatisin degerini verir."""
    kb_ = sorted(set(et_b))
    riskli = set()
    for c in set(et_a):
        A = et_a == c
        for r_ in range(1, len(kb_) + 1):
            for S in combinations(kb_, r_):
                if 0 < int((A ^ np.isin(et_b, S)).sum()) < 5:
                    riskli.add(c)
    return riskli


if at is not None:
    try:
        cox = kume_cox(kume, K)
        say = kume_sayilari(kume)
        n_tum, olay_tum = int(say["kume_yatis"].sum()), int(say["kume_olay"].sum())
        cox = pd.concat([pd.DataFrame({"terim": ["kume_1"], "katsayi": [0.0], "etki": [1.0], "kume_terimi": [True]}),
                         cox], ignore_index=True)
        cox = cox.merge(say[["kume_yatis", "kume_olay"]], left_on="terim", right_index=True, how="left")
        cox.insert(0, "analiz_tipi", TIP)
        cox.insert(1, "analiz_kodu", "kume_cox")
        cox.insert(2, "model", "cause-specific Cox, strata first_careunit, MICE, robust SE (hasta kumesi)")
        cox.insert(3, "sonuc", "yeni_by")
        cox.insert(4, "etki_olcusu", "HR")
        cox.insert(6, "ad_onayli", cox["terim"].map(ad_bul))
        cox["referans"] = "kume_1"
        cox["n"], cox["olay"], cox["atama_sayisi"] = n_tum, olay_tum, at["atama"].nunique()
        sayi = ["n", "olay", "kume_yatis", "kume_olay"]
        cox_p = kucuk_hucre_gizle(cox, sayi).astype({s_: object for s_ in sayi})
        kt = cox_p["kume_terimi"].astype(bool)

        don = kume_cox_donem(kume, K)
        don = don.merge(say, left_on="kume", right_index=True, how="left")
        don["yatis"] = np.select([don["donem"] == "72-168 saat", don["donem"] == ">168 saat"],
                                 [don["d1_yatis"], don["d2_yatis"]], don["kume_yatis"])
        don["olay_sayisi"] = np.select([don["donem"] == "72-168 saat", don["donem"] == ">168 saat"],
                                       [don["d1_olay"], don["d2_olay"]], don["kume_olay"])
        don = don.drop(columns=list(say.columns))
        don_p = kucuk_hucre_gizle(don, ["yatis", "olay_sayisi"]).astype({"yatis": object, "olay_sayisi": object})

        # Capraz gizleme (istatistik_ortak): Tablo 1'de sonuc hucresi gizli kumenin olay sayilari hicbir tabloda
        # yazilmaz; bir kumenin bir donem olay sayisi gizliyse diger donemi ve toplami da gizlenir (toplam =
        # d1 + d2); kumeler arasi toplamlar bilindigi icin tek gizli kalirsa en kucuk ikinci de gizlenir.
        degisti = True
        while degisti:
            onceki = (cox_p["kume_olay"].astype(str).tolist(), don_p["olay_sayisi"].astype(str).tolist())
            for c in kume_sirali(kume):
                don_c = don_p["kume"] == c
                gz_don = don_p.loc[don_c, "olay_sayisi"].isin(["<5", "gizli"]).any()
                gz_cox = cox_p.loc[kt & (cox_p["terim"] == c), "kume_olay"].isin(["<5", "gizli"]).any()
                if c in sonuc_gizli or gz_don or gz_cox:
                    don_p = capraz_gizle(don_p, don_c, ["olay_sayisi"])
                    cox_p = capraz_gizle(cox_p, kt & (cox_p["terim"] == c), ["kume_olay"])
            cox_p.loc[kt] = tek_gizliyi_tamamla(cox_p.loc[kt].copy(), "kume_olay", None)
            for dn in ["72-168 saat", ">168 saat"]:
                m_ = don_p["donem"] == dn
                # donem toplami (06j) ve kume_1'in 72-168 saat sayisi (08d) bilindiginden diger kumelerin toplami da
                # bilinir: tek gizli kalirsa en kucuk ikinci de gizlenir
                don_p.loc[m_] = tek_gizliyi_tamamla(don_p.loc[m_].copy(), "olay_sayisi", None)
            degisti = onceki != (cox_p["kume_olay"].astype(str).tolist(), don_p["olay_sayisi"].astype(str).tolist())
        cox_p.loc[kt] = tek_gizliyi_tamamla(cox_p.loc[kt].copy(), "kume_yatis", None)
        tamsayi(cox_p, sayi).to_csv(paylas / "08e_kume_cox.csv", index=False, encoding="utf-8-sig")

        don_p.insert(0, "analiz_tipi", TIP)
        don_p.insert(1, "analiz_kodu", "kume_cox_donem")
        don_p.insert(2, "model", "cause-specific Cox, takip 168. saatte bolunmus, strata first_careunit x donem, MICE, "
                       "robust SE (hasta kumesi)")
        don_p["ad_onayli"] = don_p["kume"].map(ad_bul)
        don_p["referans"] = "kume_1"
        don_p["atama_sayisi"] = at["atama"].nunique()
        don_p = don_p[["analiz_tipi", "analiz_kodu", "model", "kume", "ad_onayli", "donem", "katsayi", "se", "etki",
                       "alt_95", "ust_95", "p", "yatis", "olay_sayisi", "referans", "atama_sayisi", "se_naif",
                       "alt_95_naif", "ust_95_naif", "p_naif"]]
        tamsayi(don_p, ["yatis", "olay_sayisi"]).to_csv(paylas / "08h_kume_donem_hr.csv", index=False,
                                                        encoding="utf-8-sig")
        print(cox.loc[cox["kume_terimi"].astype(bool), ["terim", "etki", "alt_95", "ust_95", "p"]].to_string(index=False))
        print(don[["kume", "donem", "etki", "alt_95", "ust_95", "p"]].to_string(index=False))
    except Exception as e:
        hata_kaydet("kume_cox", e)

# ---- Duyarlilik: k = 3 (kume buyuklukleri, ortalama yorunge, kume Cox) ----
try:
    if 3 not in modeller:
        raise ValueError("k = 3 cozumu yok")
    et3 = etiket_serisi(3)
    # Ana cozumle birlikte okununca birkac yatisi ayiran kumeler: olay sayisi ve ortalama yorunge yazilmaz
    riskli = fark_riski(et3.to_numpy(), kume.to_numpy()) if kume is not None and K != 3 else set()
    y3 = yorunge_tablosu(et3, 3, {})
    y3.loc[y3["kume"].isin(riskli), ["ortalama_jh_hlm", "alt_95", "ust_95"]] = np.nan
    y3 = y3.assign(bolum="yorunge")
    parca = [y3]
    c3 = None
    try:  # Cox hata verse de buyukluk ve yorunge yazilir
        c3 = kume_cox(et3, 3) if at is not None else None
    except Exception as e:
        hata_kaydet("k3_duyarlilik_cox", e)
    if c3 is not None:
        c3 = pd.concat([pd.DataFrame({"terim": ["kume_1"], "katsayi": [0.0], "etki": [1.0], "kume_terimi": [True]}),
                        c3[c3["kume_terimi"]]], ignore_index=True)
        say3 = kume_sayilari(et3)
        c3 = c3.merge(say3[["kume_yatis", "kume_olay"]], left_on="terim", right_index=True, how="left")
        c3 = kucuk_hucre_gizle(c3, ["kume_yatis", "kume_olay"]).astype({"kume_olay": object, "kume_yatis": object})
        c3 = capraz_gizle(c3, c3["terim"].isin(riskli), ["kume_olay"])
        c3 = tek_gizliyi_tamamla(c3, "kume_olay", None)
        c3 = tek_gizliyi_tamamla(c3, "kume_yatis", None)
        parca.append(c3.rename(columns={"terim": "kume"}).assign(
            bolum="cox_hr", analiz_tipi=TIP, k=3, referans="kume_1",
            model="cause-specific Cox, strata first_careunit, MICE, robust SE (hasta kumesi)", atama_sayisi=at["atama"].nunique()))
    k3 = pd.concat(parca, ignore_index=True)
    k3["fark_riski_nedeniyle_gizli"] = k3["kume"].isin(riskli)
    on = ["analiz_tipi", "bolum", "k", "kume", "ad_onerisi", "blok", "blok_bas_saat", "yatis", "ortalama_jh_hlm",
          "katsayi", "etki", "alt_95", "ust_95", "p", "alt_95_naif", "ust_95_naif", "p_naif", "kume_yatis",
          "kume_olay", "referans", "model", "atama_sayisi",
          "fark_riski_nedeniyle_gizli"]
    k3 = k3[[c for c in on if c in k3.columns]]
    tamsayi(kucuk_hucre_gizle(k3, ["yatis"]), [c for c in ["yatis", "kume_yatis", "kume_olay"] if c in k3]).to_csv(
        paylas / "08g_k3_duyarlilik.csv", index=False, encoding="utf-8-sig")
except Exception as e:
    hata_kaydet("k3_duyarlilik", e)

pd.DataFrame(satir_hata, columns=["analiz", "hata"]).assign(analiz_tipi=TIP)[["analiz_tipi", "analiz", "hata"]].to_csv(
    paylas / "08z_hatalar.csv", index=False, encoding="utf-8-sig")
print(f"\n{len(satir_hata)} analizde hata (08z_hatalar.csv). Ciktilar: {paylas}")
