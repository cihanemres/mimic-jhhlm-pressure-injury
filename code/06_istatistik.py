"""Adim 6 (Faz 2): Istatistik. Girdi <cikti>/ozel/analiz_seti.parquet (once 05 calistirilmali).

Tum tablolar <cikti>/paylasilabilir/ altina yazilir (kucuk hucreler gizli). Sayilar yuvarlanmadan,
nokta ondalikli ham deger olarak yazilir; makale tablosu bicimlendirmesi sonra yapilir.
Her model satirinda analiz_tipi: birincil / duyarlilik / ikincil.

Fine-Gray (duyarlilik a) R'da: code/06b_fine_gray.R. Orantili hazard (cox.zph, 06e2), donem bazinda HR (06j),
tt duyarliligi ve Schoenfeld grafigi R'da: code/06c_ph.R (06d'ye satir ekler). Bu betik R icin atanmis veri setlerini
<cikti>/ozel/06_atanmis_veri.csv.gz olarak yazar (hasta duzeyi, yalnizca ozel).

Kullanim:
    python code/06_istatistik.py --cikti outputs_tam
"""
import argparse
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurallar import BMI_ARALIK, SEYREK_BIRIM  # noqa: E402
from istatistik_ortak import (SONUC_KORUNAN, aalen_johansen, capraz_gizle, cif_noktada, delong,  # noqa: E402
                              kumulatif_insidans_capraz, rubin, sonuc_gizli_gruplar, tablo1, tablo1_fark_gizle,
                              tablo1_gizli_mi, tablo1_tamamlayici)
from mimic_db import cikti_klasorleri, kucuk_hucre_gizle  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402
from lifelines import CoxPHFitter, NelsonAalenFitter  # noqa: E402
from scipy import stats  # noqa: E402
from sklearn.experimental import enable_iterative_imputer  # noqa: E402,F401
from sklearn.impute import IterativeImputer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_predict  # noqa: E402
from statsmodels.stats.outliers_influence import variance_inflation_factor  # noqa: E402

p = argparse.ArgumentParser(description="Istatistik")
p.add_argument("--cikti", default="outputs", help="Ciktilarin klasoru (05'in yazdigi yer)")
p.add_argument("--m", type=int, default=20, help="Coklu atama sayisi")
p.add_argument("--bootstrap", type=int, default=1000, help="Bootstrap tekrar sayisi")
p.add_argument("--tohum", type=int, default=2026, help="Rastgele sayi tohumu")
a = p.parse_args()
ozel, paylas = cikti_klasorleri(a.cikti)
rng = np.random.default_rng(a.tohum)
# Onceki calistirmanin ciktilarini sil: bu calistirmada hata veren bir analizin eski dosyasi kalmasin
# (06i, 06e2, 06e3, 06j ve 06d'deki R satirlari R betikleriyle yeniden uretilir)
for eski in list(paylas.glob("06*")) + [ozel / "06_atanmis_veri.csv.gz"]:
    eski.unlink(missing_ok=True)

# ---------------------------------------------------------------
# Model tanimi (README "Istatistik (06)" bolumunde raporlanir)
# ---------------------------------------------------------------
JH_REF, JH_DIGER = "1-3", ["4-5", "6-8"]
MARUZIYET = ["jh_4_5", "jh_6_8"]
KARISTIRICI = ["yas", "kadin", "bmi", "sofa_24s", "mekanik_ventilasyon", "vazopresor", "sedatif_herhangi",
               "rass_en_dusuk", "fiziksel_kisitlama", "braden_mobilite_disi_en_dusuk", "charlson_yassiz"]
EK_ALBUMIN = ["albumin_en_kotu"]
EK_ONLEYICI = ["tedavi_edici_yatak", "basinc_azaltici_cihaz", "pozisyon_degistirme_24s"]
STRATA = "ilk_yb_birimi"
SONUCLAR = {  # sonuc kodu: (sure, olay tipi, 72-168 ikili)
    "yeni_by": ("sure_saat", "olay_tipi", "yeni_by_72_168"),
    "evre2": ("sure_saat_evre2", "olay_tipi_evre2", "yeni_by_72_168_evre2"),
    "bilinen": ("sure_saat_bilinen", "olay_tipi_bilinen", "yeni_by_72_168_bilinen"),
}
warnings.filterwarnings("ignore", category=FutureWarning)

# ---- Veri ----
yol = ozel / "analiz_seti.parquet"
if not yol.exists():
    raise SystemExit(f"{yol} yok. Once 05_analiz_seti.py calistirin.")
ham = pd.read_parquet(yol)
d = ham.copy()
# Cox standart hatalari hasta duzeyinde kumelenmis (ayni hastanin birden fazla yatisi): subject_id 04'ten
d["subject_id"] = d["stay_id"].map(pd.read_parquet(ozel / "04_kohort.parquet", columns=["stay_id", "subject_id"])
                                   .set_index("stay_id")["subject_id"])
KUME = "subject_id"
for s in d.columns:  # nullable Int -> float (lifelines/sklearn icin)
    if str(d[s].dtype) in ("Int32", "Int64"):
        d[s] = d[s].astype(float)
d["kadin"] = (d["cinsiyet"] == "F").astype(float)
d["jh_4_5"] = (d["jh_hlm_grup"] == "4-5").astype(float)
d["jh_6_8"] = (d["jh_hlm_grup"] == "6-8").astype(float)
yillar = sorted(d["anchor_year_group"].dropna().unique())
YIL = [f"yil_{y[:4]}" for y in yillar[1:]]  # referans en eski yil grubu
for y, ad in zip(yillar[1:], YIL):
    d[ad] = (d["anchor_year_group"] == y).astype(float)
birim_n = d[STRATA].value_counts()
seyrek = birim_n[birim_n < SEYREK_BIRIM].sort_index()
d[STRATA] = d[STRATA].where(~d[STRATA].isin(seyrek.index), "diger")
birimler = sorted(d[STRATA].dropna().unique())
BIRIM = [f"birim_{i}" for i in range(1, len(birimler))]  # lojistik modelde strata yerine
for b, ad in zip(birimler[1:], BIRIM):
    d[ad] = (d[STRATA] == b).astype(float)
for kod, (sure, tip, _) in SONUCLAR.items():
    d[f"olay_{kod}"] = (d[tip] == "yeni_by").astype(float)          # cause-specific
    # Aalen-Johansen ve Fine-Gray: 1 yeni BY, 2 YB olumu, 3 canli taburculuk (2 ve 3 yarisan), 0 idari sansur
    d[f"olay_kod_{kod}"] = d[tip].map({"yeni_by": 1, "yb_olum": 2, "taburculuk": 3}).fillna(0).astype(int)
    d[f"na_{kod}"] = NelsonAalenFitter().fit(d[sure], d[f"olay_{kod}"]).cumulative_hazard_at_times(
        d[sure]).to_numpy()
TEMEL = MARUZIYET + KARISTIRICI + YIL
satir_model, satir_hata = [], []


def hata_kaydet(analiz, e):
    print(f"  [HATA] {analiz}: {type(e).__name__}: {e}")
    satir_hata.append({"analiz": analiz, "hata": f"{type(e).__name__}: {e}"})


# ---------------------------------------------------------------
# 1. Tablo 1
# ---------------------------------------------------------------
TABLO1_DISI = {"stay_id"}

# Birimler modeldeki gibi birlesik ("diger") gosterilir
TABLO1_DEG = [c for c in ham.columns if c not in TABLO1_DISI]
t1 = tablo1(d.assign(jh_hlm_grup=ham["jh_hlm_grup"]), "jh_hlm_grup", JH_REF, TABLO1_DEG, SONUC_KORUNAN)
t1 = tablo1_fark_gizle(t1, d.assign(jh_hlm_grup=ham["jh_hlm_grup"]), "jh_hlm_grup", SONUC_KORUNAN)
t1b = tablo1(d.assign(yeni_by=np.where(d["olay_yeni_by"] == 1, "var", "yok")), "yeni_by", "yok", TABLO1_DEG)
# Tablolar arasi: 06b'deki jh_hlm_grup x "var" hucresi, 06a'daki o grubun olay_tipi = yeni_by hucresidir
# ("yok" = grup buyuklugu - "var"). Biri gizliyse digeri de gizlenir; tamamlayici gizleme yeniden yapilir.
degisti = True
while degisti:
    degisti = False
    for g in [JH_REF] + JH_DIGER:
        a_gizli = tablo1_gizli_mi(t1, "olay_tipi", ["yeni_by"], g)
        b_m = (t1b["degisken"] == "jh_hlm_grup") & (t1b["kategori"] == g)
        b_gizli = bool(t1b.loc[b_m, "sayi"].isin(["<5", "gizli"]).any())
        if a_gizli and not t1b.loc[b_m, "sayi"].isin(["<5", "gizli"]).all():
            t1b = tablo1_tamamlayici(capraz_gizle(t1b, b_m, ["sayi"]))
            degisti = True
        if b_gizli and not a_gizli:
            a_m = (t1["degisken"] == "olay_tipi") & (t1["kategori"] == "yeni_by") & (t1["grup"] == g)
            t1 = tablo1_tamamlayici(capraz_gizle(t1, a_m, ["sayi"]), SONUC_KORUNAN)
            degisti = True
# Not: "diger"e giren birimler ve yatis sayilari. Tek kucuk hucre "diger" toplamindan geri hesaplanmasin
birim_not = kucuk_hucre_gizle(pd.DataFrame({
    "degisken": f"not: 'diger' olarak birlestirilen {STRATA} (yatis < {SEYREK_BIRIM})", "tip": "not",
    "kategori": seyrek.index, "grup": "tum kohort", "sayi": seyrek.to_numpy()}), ["sayi"])
if (birim_not["sayi"] == "<5").sum() == 1 and len(birim_not) > 1:
    birim_not.loc[pd.to_numeric(birim_not["sayi"], errors="coerce").idxmin(), "sayi"] = "gizli"
pd.concat([t1, birim_not], ignore_index=True).to_csv(paylas / "06a_tablo1_jhhlm.csv", index=False,
                                                     encoding="utf-8-sig")
t1b.to_csv(paylas / "06b_tablo1_yeni_by.csv", index=False, encoding="utf-8-sig")

# ---------------------------------------------------------------
# 2. Kumulatif insidans: Aalen-Johansen (olum ve canli taburculuk yarisan olay, idari sansur sansur)
# ---------------------------------------------------------------
GUN = np.array([1, 3, 7, 14, 21, 25])  # 72. saatten sonraki gun (28. gun sansuru = 25. gun)

ki_satir, egriler = [], {}
for g in [JH_REF] + JH_DIGER:
    alt = d[ham["jh_hlm_grup"] == g]
    if len(alt) == 0:
        continue
    t, kod = (alt["sure_saat"] / 24).to_numpy(), alt["olay_kod_yeni_by"].to_numpy()
    zaman, cif = aalen_johansen(t, kod)
    egriler[g] = (zaman, cif)
    boot = np.empty((a.bootstrap, len(GUN)))
    for b in range(a.bootstrap):
        i = rng.integers(0, len(t), len(t))
        boot[b] = cif_noktada(*aalen_johansen(t[i], kod[i]), GUN)
    nokta = cif_noktada(zaman, cif, GUN)
    for j, gun in enumerate(GUN):
        ki_satir.append({"analiz_tipi": "birincil", "grup": g, "gun_72s_sonrasi": gun,
                         "kumulatif_insidans": nokta[j], "alt_95": np.quantile(boot[:, j], .025),
                         "ust_95": np.quantile(boot[:, j], .975), "risk_altinda": int((t >= gun).sum()),
                         "kumulatif_olay": int(((kod == 1) & (t <= gun)).sum())})
ki = pd.DataFrame(ki_satir)
# Tablolar arasi: 06a'da gizlenen sonuc hucrelerini geri hesaplatan hucreler gizlenir (istatistik_ortak)
sonuc_gizli = sonuc_gizli_gruplar(t1, [JH_REF] + JH_DIGER)
kumulatif_insidans_capraz(kucuk_hucre_gizle(ki, ["risk_altinda", "kumulatif_olay"]), "grup", sonuc_gizli,
                          d.assign(jh_hlm_grup=ham["jh_hlm_grup"]), "jh_hlm_grup", "sure_saat", "olay_tipi",
                          "yeni_by_72_168").to_csv(paylas / "06c_kumulatif_insidans.csv", index=False,
                                                   encoding="utf-8-sig")
fig, ax = plt.subplots(figsize=(6, 4.5))
for g, (zaman, cif) in egriler.items():
    if sonuc_gizli.get(g, set()) & {"yeni_by", "yeni_by_72_168"}:  # egri gizli olay sayisini verir
        continue
    ax.step(np.concatenate([[0], zaman]), np.concatenate([[0], cif]) * 100, where="post", label=f"JH-HLM {g}")
ax.set_xlabel("72. saatten sonraki gün / Days after hour 72")
ax.set_ylabel("Kümülatif insidans (%) / Cumulative incidence (%)")
ax.set_xlim(0, 25)
ax.legend(frameon=False)
fig.tight_layout()
for uzanti in ["png", "svg"]:
    fig.savefig(paylas / f"06c_kumulatif_insidans.{uzanti}", dpi=300)
plt.close(fig)

# ---------------------------------------------------------------
# 3. Coklu atama (MICE): atama modeline olay gostergeleri ve Nelson-Aalen kumulatif hazard eklenir
# ---------------------------------------------------------------
ATANACAK = sorted(set(TEMEL + EK_ALBUMIN + EK_ONLEYICI + ["jh_hlm_en_yuksek"]))
YARDIMCI = ([f"olay_{k}" for k in SONUCLAR] + [f"na_{k}" for k in SONUCLAR]
            + [v[2] for v in SONUCLAR.values()] + BIRIM)
LOG_ATAMA = ["bmi"]  # carpik dagilim: log olceginde atanir, sonra geri donusturulur
X = d[ATANACAK + YARDIMCI].astype(float)
X[LOG_ATAMA] = np.log(X[LOG_ATAMA])
sabit =[s for s in X.columns if X[s].nunique(dropna=True) <= 1]  # atanamaz; tek degeriyle doldurulur
X_deg = X.drop(columns=sabit)
ikili = [s for s in ATANACAK if s in X_deg and d[s].dropna().isin([0, 1]).all()]
atanmis = []
for i in range(a.m):
    imp = IterativeImputer(sample_posterior=True, max_iter=10, random_state=a.tohum + i,
                           min_value=X_deg.min().to_numpy(), max_value=X_deg.max().to_numpy())
    Xi = pd.DataFrame(imp.fit_transform(X_deg), columns=X_deg.columns, index=X.index)
    for s in sabit:
        Xi[s] = X[s].dropna().iloc[0] if X[s].notna().any() else np.nan
    Xi[ikili] = Xi[ikili].round()
    Xi[LOG_ATAMA] = np.exp(Xi[LOG_ATAMA])
    Xi["bmi"] = Xi["bmi"].clip(*BMI_ARALIK)
    atanmis.append(pd.concat([d.drop(columns=ATANACAK), Xi[ATANACAK]], axis=1))
eksik = d[ATANACAK].isna().mean().rename("eksik_orani").reset_index().rename(columns={"index": "degisken"})
# Atanan (gozlenmemis) BMI degerleri, tum atamalar birlikte
bmi_atanan = pd.concat([x.loc[d["bmi"].isna(), "bmi"] for x in atanmis])
if len(bmi_atanan):
    eksik = pd.concat([eksik, pd.DataFrame({
        "degisken": "bmi (atanan degerler, tum atamalar)", "olcu": ["min", "max", "medyan"],
        "deger": [bmi_atanan.min(), bmi_atanan.max(), bmi_atanan.median()]})], ignore_index=True)
eksik.to_csv(paylas / "06d2_atama_eksik_oranlari.csv", index=False, encoding="utf-8-sig")
# R (Fine-Gray) icin: ayni atanmis veri setleri, hasta duzeyi (yalnizca ozel)
pd.concat([x.assign(atama=i + 1)[["atama", "stay_id", KUME, STRATA, "anchor_year_group", "sure_saat",
                                  "olay_kod_yeni_by"] + TEMEL]
           for i, x in enumerate(atanmis)]).to_csv(ozel / "06_atanmis_veri.csv.gz", index=False)


# ---------------------------------------------------------------
# 4. Model yardimcilari (Rubin kurallari: istatistik_ortak.rubin)
# ---------------------------------------------------------------
def sabit_disi(veri, terimler):
    return [s for s in terimler if veri[s].nunique(dropna=True) > 1]


def cox_fit(veri, sure, olay, terimler):
    """cluster_col ile: standard_errors_ robust (hasta duzeyinde kumelenmis sandwich), variance_matrix_ naif
    (lifelines robust kovaryans matrisini saklamaz; yalnizca kosegen kullanilir)."""
    terimler = sabit_disi(veri, terimler)
    cph = CoxPHFitter().fit(veri[terimler + [sure, olay, STRATA, KUME]], duration_col=sure, event_col=olay,
                            strata=[STRATA], cluster_col=KUME)
    return cph, terimler


def logit_fit(veri, y, terimler):
    """Robust (hasta duzeyinde kumelenmis, cov_type="cluster") ve naif kovaryans; katsayilar aynidir."""
    terimler = sabit_disi(veri, terimler + BIRIM)
    model = sm.Logit(veri[y], sm.add_constant(veri[terimler]))
    m_ = model.fit(disp=0, maxiter=200, cov_type="cluster", cov_kwds={"groups": veri[KUME].to_numpy()})
    naif = model.fit(disp=0, maxiter=200)
    return (m_.params.drop("const"), m_.cov_params().drop(index="const", columns="const"), terimler,
            naif.cov_params().drop(index="const", columns="const"))


def model_satirlari(analiz_tipi, kod, aciklama, model, sonuc, olcu, veri_listesi, fit, n, olay, m):
    """Her veri setinde fit(v) -> (katsayilar, kovaryans, terimler[, naif kovaryans]); Rubin ile birlestirip satir
    ekler. Naif kovaryans verilirse (Cox) se/GA/p robust, *_naif sutunlari kumelenmemis standart hatayla."""
    kats, vars_, naifler = [], [], []
    for v in veri_listesi:
        params, cov, terimler, *naif = fit(v)
        kats.append(pd.Series(np.asarray(params), index=terimler))
        vars_.append(pd.Series(np.diag(cov), index=terimler))
        if naif:
            naifler.append(pd.Series(np.diag(naif[0]), index=terimler))
    ortak = [t for t in kats[0].index if all(t in k.index for k in kats)]  # bir atamada sabit kalan terim duser

    def birlestir(varyans):
        q, se, df = rubin([k[ortak].to_numpy() for k in kats], [v[ortak].to_numpy() for v in varyans])
        df = np.where(np.isfinite(df), df, 1e6)  # atamasiz analizde normal dagilim
        tdeg = stats.t.ppf(.975, df)
        return q, se, np.exp(q - tdeg * se), np.exp(q + tdeg * se), 2 * stats.t.sf(np.abs(q / se), df)
    q, se, alt, ust, pdeg = birlestir(vars_)
    nf = birlestir(naifler) if naifler else None
    for j, t in enumerate(ortak):
        satir_model.append({"analiz_tipi": analiz_tipi, "analiz_kodu": kod, "analiz": aciklama, "model": model,
                            "sonuc": sonuc, "etki_olcusu": olcu, "terim": t,
                            "maruziyet": t in MARUZIYET + ["jh_hlm_en_yuksek"], "katsayi": q[j], "se": se[j],
                            "etki": np.exp(q[j]), "alt_95": alt[j], "ust_95": ust[j], "p": pdeg[j], "n": n, "olay": olay,
                            "atama_sayisi": m, "se_naif": nf[1][j] if nf else np.nan,
                            "alt_95_naif": nf[2][j] if nf else np.nan, "ust_95_naif": nf[3][j] if nf else np.nan,
                            "p_naif": nf[4][j] if nf else np.nan})


def cox_analizi(analiz_tipi, kod, aciklama, sonuc, terimler, veri_listesi):
    sure, tip, _ = SONUCLAR[sonuc]
    olay = f"olay_{sonuc}"

    def fit(v):
        cph, t = cox_fit(v, sure, olay, terimler)
        return (cph.params_[t], np.diag(cph.standard_errors_[t].to_numpy() ** 2), t,
                cph.variance_matrix_.loc[t, t].to_numpy())
    try:
        model_satirlari(analiz_tipi, kod, aciklama,
                        "cause-specific Cox, strata first_careunit, robust SE (hasta kumesi)", sonuc, "HR",
                        veri_listesi, fit, len(veri_listesi[0]), int(veri_listesi[0][olay].sum()),
                        len(veri_listesi) if len(veri_listesi) > 1 else 0)
    except Exception as e:  # demoda modeller yakinsamayabilir; akis surer, hata dosyaya yazilir
        hata_kaydet(kod, e)


def logit_analizi(analiz_tipi, kod, aciklama, sonuc, terimler, veri_listesi):
    y = SONUCLAR[sonuc][2]

    def fit(v):
        params, cov, t, naif = logit_fit(v, y, terimler)
        return params, cov.to_numpy(), t, naif.to_numpy()
    try:
        model_satirlari(analiz_tipi, kod, aciklama, "lojistik regresyon, first_careunit kukla, robust SE (hasta kumesi)",
                        sonuc, "OR",
                        veri_listesi, fit, len(veri_listesi[0]), int(veri_listesi[0][y].sum()),
                        len(veri_listesi) if len(veri_listesi) > 1 else 0)
    except Exception as e:
        hata_kaydet(kod, e)


# ---------------------------------------------------------------
# 5. Birincil ve duyarlilik analizleri
# ---------------------------------------------------------------
print("Modeller...")
cox_analizi("birincil", "birincil", "Cause-specific Cox, MICE", "yeni_by", TEMEL, atanmis)


def e_degeri(hr, sik_sonuc):
    """VanderWeele-Ding E-degeri. sik_sonuc ise HR once RR'ye cevrilir (VanderWeele 2017), degilse HR~RR."""
    if sik_sonuc:
        hr = (1 - 0.5 ** np.sqrt(hr)) / (1 - 0.5 ** np.sqrt(1 / hr))
    rr = max(hr, 1 / hr)
    return rr + np.sqrt(rr * (rr - 1))


for s in [s for s in satir_model if s["analiz_kodu"] == "birincil" and s["terim"] in MARUZIYET]:
    sinir = s["ust_95"] if s["etki"] < 1 else s["alt_95"]  # GA'nin 1'e yakin siniri
    for sik, kod, model in [(False, "birincil_e_degeri_hr", "VanderWeele-Ding E-degeri, HR dogrudan (seyrek sonuc)"),
                            (True, "birincil_e_degeri_sik", "VanderWeele-Ding E-degeri, sik sonuc HR->RR donusumu")]:
        for olcu, deger in [("E-degeri (nokta tahmini)", e_degeri(s["etki"], sik)),
                            ("E-degeri (GA'nin 1'e yakin siniri)",
                             1.0 if (sinir - 1) * (s["etki"] - 1) <= 0 else e_degeri(sinir, sik))]:
            satir_model.append({"analiz_tipi": "birincil", "analiz_kodu": kod, "analiz": "E-degeri, birincil HR",
                                "model": model, "sonuc": s["sonuc"], "etki_olcusu": olcu, "terim": s["terim"],
                                "maruziyet": False, "etki": deger, "n": s["n"], "olay": s["olay"],
                                "atama_sayisi": s["atama_sayisi"]})
cox_analizi("duyarlilik", "b_evre2", "Sonuc evre 2 ve ustu", "evre2", TEMEL, atanmis)
logit_analizi("duyarlilik", "c_72_168", "72-168 saat penceresi, lojistik", "yeni_by", TEMEL, atanmis)
cox_analizi("duyarlilik", "d_bilinmiyor_haric", "BILINMIYOR haric sonuc", "bilinen", TEMEL, atanmis)
cox_analizi("duyarlilik", "e_albumin", "Albumin eklenmis", "yeni_by", TEMEL + EK_ALBUMIN, atanmis)
cox_analizi("duyarlilik", "f_onleyici", "Onleyici girisimler eklenmis", "yeni_by", TEMEL + EK_ONLEYICI, atanmis)
tam_kayit = d.dropna(subset=TEMEL)
cox_analizi("duyarlilik", "g_tam_kayit", "Tam kayitli analiz (atamasiz)", "yeni_by", TEMEL, [tam_kayit])
cox_analizi("duyarlilik", "h_jh_surekli", "JH-HLM surekli (en yuksek duzey, 1 birim)", "yeni_by",
            ["jh_hlm_en_yuksek"] + KARISTIRICI + YIL, atanmis)
# Charlson taburculukta kodlanan ICD tanilarindan gelir (72. saatte bilinmez); (i) ve (j) R'da (06c_ph.R)
cox_analizi("duyarlilik", "k_charlsonsuz", "Charlson cikarilmis (taburculuk kodlari)", "yeni_by",
            [s for s in TEMEL if s != "charlson_yassiz"], atanmis)
satir_model.append({"analiz_tipi": "duyarlilik", "analiz_kodu": "a_fine_gray",
                    "analiz": "Fine-Gray: code/06b_fine_gray.R -> 06i_fine_gray.csv"})

# VIF: birincil model, ilk atanmis veri seti (orantili hazard testi R'da: 06c_ph.R -> 06e2)
try:
    t = sabit_disi(atanmis[0], TEMEL)
    tasarim = sm.add_constant(atanmis[0][t].astype(float))
    pd.DataFrame({"analiz_tipi": "birincil", "terim": t,
                  "vif": [variance_inflation_factor(tasarim.to_numpy(), i + 1) for i in range(len(t))]}).to_csv(
        paylas / "06f_vif.csv", index=False, encoding="utf-8-sig")
except Exception as e:
    hata_kaydet("vif", e)


# ---------------------------------------------------------------
# 6. Model 1-4 karsilastirmasi (ikincil; 72-168 saat, lojistik, 10 katli capraz dogrulama tahminleri)
# ---------------------------------------------------------------

MODELLER = {
    "Model 1: Braden toplam": ["braden_toplam_en_dusuk"],
    "Model 2: JH-HLM": MARUZIYET,
    "Model 3: Braden toplam + JH-HLM": ["braden_toplam_en_dusuk"] + MARUZIYET,
    "Model 4: mobilite disi Braden + JH-HLM": ["braden_mobilite_disi_en_dusuk"] + MARUZIYET,
}
y_sut = "yeni_by_72_168"
ortak = d.dropna(subset=sorted({s for v in MODELLER.values() for s in v}) + [y_sut])
y = ortak[y_sut].to_numpy().astype(int)
karsilastirma, ciftler, tahmin = [], [], {}
try:
    katman = int(min(10, y.sum(), (1 - y).sum()))
    if katman < 2:
        raise ValueError(f"72-168 saat olay sayisi capraz dogrulama icin yetersiz ({int(y.sum())})")
    cv = StratifiedKFold(n_splits=katman, shuffle=True, random_state=a.tohum)
    for ad, terimler in MODELLER.items():
        tahmin[ad] = cross_val_predict(LogisticRegression(C=np.inf, max_iter=1000), ortak[terimler], y,
                                       cv=cv, method="predict_proba")[:, 1]
    boot_i = [rng.integers(0, len(y), len(y)) for _ in range(a.bootstrap)]
    boot_i = [i for i in boot_i if 0 < y[i].sum() < len(i)]
    for ad, pr in tahmin.items():
        lp = np.log(np.clip(pr, 1e-12, 1 - 1e-12) / (1 - np.clip(pr, 1e-12, 1 - 1e-12)))
        egim = sm.GLM(y, sm.add_constant(lp), family=sm.families.Binomial()).fit().params[1]
        kesisim = sm.GLM(y, np.ones((len(y), 1)), family=sm.families.Binomial(), offset=lp).fit().params[0]
        boot = [roc_auc_score(y[i], pr[i]) for i in boot_i]
        karsilastirma.append({"analiz_tipi": "ikincil", "model": ad, "n": len(y), "olay": int(y.sum()),
                              "auroc": roc_auc_score(y, pr), "auroc_alt_95": np.quantile(boot, .025),
                              "auroc_ust_95": np.quantile(boot, .975), "kalibrasyon_egimi": egim,
                              "kalibrasyon_kesisimi": kesisim, "brier": brier_score_loss(y, pr),
                              "bootstrap_tekrar": len(boot_i), "capraz_dogrulama_katman": katman})
    adlar = list(tahmin)
    for i1 in range(len(adlar)):
        for i2 in range(i1 + 1, len(adlar)):
            p1, p2 = tahmin[adlar[i1]], tahmin[adlar[i2]]
            fark, _, p_d = delong(y, p1, p2)
            boot = [roc_auc_score(y[i], p1[i]) - roc_auc_score(y[i], p2[i]) for i in boot_i]
            ciftler.append({"analiz_tipi": "ikincil", "model_a": adlar[i1], "model_b": adlar[i2],
                            "auroc_farki": fark, "alt_95": np.quantile(boot, .025), "ust_95": np.quantile(boot, .975),
                            "p_delong": p_d})
except Exception as e:
    hata_kaydet("model_karsilastirma", e)
kk = pd.DataFrame(karsilastirma, columns=["analiz_tipi", "model", "n", "olay", "auroc", "auroc_alt_95",
                                         "auroc_ust_95", "kalibrasyon_egimi", "kalibrasyon_kesisimi", "brier",
                                         "bootstrap_tekrar", "capraz_dogrulama_katman"])
kucuk_hucre_gizle(kk, ["n", "olay"]).to_csv(paylas / "06g_model_karsilastirma.csv", index=False,
                                             encoding="utf-8-sig")
pd.DataFrame(ciftler, columns=["analiz_tipi", "model_a", "model_b", "auroc_farki", "alt_95", "ust_95",
                               "p_delong"]).to_csv(paylas / "06h_auroc_farki.csv", index=False, encoding="utf-8-sig")

# ---- Model tablosu ve hatalar ----
md = pd.DataFrame(satir_model, columns=["analiz_tipi", "analiz_kodu", "analiz", "model", "sonuc", "etki_olcusu",
                                        "terim", "maruziyet", "katsayi", "se", "etki", "alt_95", "ust_95", "p",
                                        "n", "olay", "atama_sayisi", "se_naif", "alt_95_naif", "ust_95_naif", "p_naif"])
kucuk_hucre_gizle(md, ["n", "olay"]).to_csv(paylas / "06d_modeller.csv", index=False, encoding="utf-8-sig")
pd.DataFrame(satir_hata, columns=["analiz", "hata"]).to_csv(paylas / "06z_hatalar.csv", index=False,
                                                           encoding="utf-8-sig")

print(md[md["maruziyet"] == True][["analiz_kodu", "terim", "etki", "alt_95", "ust_95", "p"]].to_string(index=False))  # noqa: E712
print(md[md["analiz_kodu"].str.startswith("birincil_e_degeri", na=False)][
    ["analiz_kodu", "terim", "etki_olcusu", "etki"]].to_string(index=False))
print(f"\n{len(satir_hata)} analizde hata (06z_hatalar.csv). Ciktilar: {paylas}")
