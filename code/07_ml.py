"""Adim 7 (Faz 3): Makine ogrenmesi. 0-72 saat verileriyle 72-168 saatte yeni basinc yarasi (0/1).

Girdi: <cikti>/ozel/analiz_seti.parquet (05) ve subject_id icin <cikti>/ozel/04_kohort.parquet (04).
Iki dogrulama; her ciktida analiz_tipi:
    ic_dogrulama:       ic ice capraz dogrulama. Dis dongu GroupKFold(5, subject_id); ic dongu GroupKFold(3)
                        ile hiperparametre. Metrikler dis katlarin birlestirilmis kat disi tahminlerinde.
    donemsel_dogrulama: donemsel (anchor_year_group) bolme: 2008-2016 grubu egitim (ic dongu GroupKFold(3)
                        hiperparametre), 2017-2022 grubu test. anchor_year_group takvim yili degil, hastanin
                        kaydirilmis yillarinin dustugu donemdir (README). Iki tarafta da olan hasta test tarafindan
                        cikarilir (07g'de sayisi).
Ozellikler: Charlson ve bilesenleri (CHARLSON) taburculukta kodlanan ICD tanilarindan gelir, 72. saatte
bilinmez; birincil modellere girmez (bilgi sizintisi). Charlson'li surum yalnizca duyarlilik (07b/07c_*_charlsonlu).
SHAP, karar egrisi, Braden kesimleri ve alt gruplar birincil (Charlson'siz) modelden.
Modeller: L2 lojistik, Random Forest, XGBoost. Taban: Braden toplam (lojistik, 0-72 saatteki en dusuk) ve
Braden kesim noktalari: <= 18 onceden belirlenmis; <= 12 ve <= 14 sonradan eklenen. Dengesizlik duzeltmesi yok (agirlik, SMOTE yok; kalibrasyon korunur). Eksik veri: XGBoost
dogal; LR ve RF icin egitim katinda fit edilen medyan atama + eksiklik gostergesi (pipeline icinde).

Ciktilar (paylasilabilir, kucuk hucre gizli):
    07a_ozellikler.csv          ozellik listesi ve eksik yuzdesi
    07b_metrikler.csv           AUROC, AUPRC, Brier, kalibrasyon egimi/kesisimi, her Braden kesim noktasinin
                                duyarliliginda ozgulluk; kesim noktalari icin duyarlilik, ozgulluk, PPD, NPD;
                                1000 hasta duzeyinde bootstrap %95 GA; belirleme: onceden_belirlenmis / sonradan_eklenen
    07c_auroc_farki.csv         AUROC farki (DeLong): modeller - Braden toplam lojistik; XGBoost ve RF - L2 lojistik
    07d_alt_gruplar.csv         cinsiyet, yas grubu, birlestirilmis birim icin AUROC
    07e_hiperparametreler.csv   secilen hiperparametreler (dis kat / donemsel)
    07f_shap_ozet.csv           ortalama |SHAP| (en iyi agac modeli, donemsel test seti)
    07g_bolme.csv               egitim/test yatis, hasta ve olay sayilari
    07b_metrikler_charlsonlu.csv  duyarlilik: Charlson ve bilesenleri eklenmis uc model (ayni bolmeler, ayni bootstrap
                                orneklemleri); 07b ile ayni sutunlar
    07c_auroc_farki_charlsonlu.csv  AUROC farki (DeLong): Charlson'li - birincil (ayni model)
    07h_egri_noktalari.csv      grafiklerin toplu noktalari (09 makale sekilleri icin; tek tek tahmin ya da her esikteki
                                ham ROC noktasi yok): ROC (0-1 arasi 100 noktalik sabit 1 - ozgulluk izgarasinda
                                dogrusal enterpole duyarlilik), kalibrasyon ondaliklari (5'ten az olayli dilim gizli),
                                karar egrisi net faydasi (0,02-0,30, 0,01 adim; herkese, hic kimseye, Braden kesimleri)
    07_<grafik>_<analiz_tipi>.png/.svg  ROC, PR, kalibrasyon, karar egrisi; 07_shap_*.png/.svg
    07z_hatalar.csv
Yalnizca ozel: 07_modeller/ (egitilmis modeller: ic_kat<k>_<model>.joblib ve ic_katlar.joblib ic dogrulamanin
dis katlari, <model>.joblib donemsel egitim seti; Charlson'li surum charlsonlu_ onekiyle), 07_tahminler.parquet, 07_shap_beeswarm.png.

--yalnizca-degerlendirme: hiperparametre aramasi ve egitim yapilmaz; 07_modeller/ altindaki kayitli modeller
yuklenir, metrikler, grafikler, SHAP ve alt gruplar yeniden uretilir (07e korunur). Kayitli model yoksa durur;
bir dogrulamanin modeli eksikse o dogrulama 07z'ye hata olarak yazilir.

Kullanim:
    python code/07_ml.py --cikti outputs_tam
    python code/07_ml.py --cikti outputs_tam --yalnizca-degerlendirme
"""
import argparse
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from istatistik_ortak import delong, kume_bootstrap  # noqa: E402
from kurallar import SEYREK_BIRIM  # noqa: E402
from mimic_db import cikti_klasorleri, kucuk_hucre_gizle  # noqa: E402

import joblib  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shap  # noqa: E402
import statsmodels.api as sm  # noqa: E402
from scipy.stats import loguniform, randint, uniform  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (average_precision_score, brier_score_loss, precision_recall_curve,  # noqa: E402
                             roc_auc_score, roc_curve)
from sklearn.model_selection import GroupKFold, RandomizedSearchCV  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

p = argparse.ArgumentParser(description="Makine ogrenmesi")
p.add_argument("--cikti", default="outputs", help="Ciktilarin klasoru (05'in yazdigi yer)")
p.add_argument("--bootstrap", type=int, default=1000, help="Bootstrap tekrar sayisi")
p.add_argument("--deneme", type=int, default=40, help="Model basina RandomizedSearchCV deneme sayisi")
p.add_argument("--tohum", type=int, default=2026, help="Rastgele sayi tohumu")
p.add_argument("--yalnizca-degerlendirme", action="store_true",
               help="Egitim yok: ozel/07_modeller/ altindaki kayitli modellerle yalnizca degerlendirme")
a = p.parse_args()
ozel, paylas = cikti_klasorleri(a.cikti)
rng = np.random.default_rng(a.tohum)
model_klasor = ozel / "07_modeller"
model_klasor.mkdir(exist_ok=True)
DEGERLENDIRME = a.yalnizca_degerlendirme
if DEGERLENDIRME and not any(model_klasor.glob("*.joblib")):
    raise SystemExit(f"{model_klasor} altinda kayitli model yok. Once --yalnizca-degerlendirme olmadan calistirin.")
# Onceki calistirmanin ciktilarini sil: hata veren bir analizin eski dosyasi kalmasin.
# Yalnizca degerlendirmede modeller ve hiperparametre tablosu (07e) korunur.
eskiler = [*paylas.glob("07*"), *ozel.glob("07*.*")] + ([] if DEGERLENDIRME else [*model_klasor.glob("*")])
for eski in eskiler:
    if not (DEGERLENDIRME and eski.name == "07e_hiperparametreler.csv"):
        eski.unlink(missing_ok=True)
warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------
# Tanimlar (README "Makine ogrenmesi (07)" bolumunde raporlanir)
# ---------------------------------------------------------------
HEDEF = "yeni_by_72_168"
EGITIM_YIL = ["2008 - 2010", "2011 - 2013", "2014 - 2016"]  # donemsel egitim; digerleri (2017-2022) test
BRADEN = "braden_toplam_en_dusuk"
# Braden kesim noktalari (<= k risk var). 18 protokolde onceden belirlenmis; 12 ve 14 tam veri sonuclarindan sonra
# eklendi (kohortta neredeyse herkes <= 18). Ciktida "belirleme" sutunu.
BRADEN_KESIMLER = {18: "onceden_belirlenmis", 12: "sonradan_eklenen", 14: "sonradan_eklenen"}
# Disarida: kimlik, yil grubu (donemsel bolmenin degiskeni), AM-PAC (dolu %6), sonuc ve zaman degiskenleri,
# Charlson ve bilesenleri (taburculuk ICD kodlari, 72. saatte bilinmez; yalnizca duyarlilik modelinde).
# Basinc yarasi tani kodlari (ICD-9 707.0x, ICD-10 L89) 05'te hicbir degiskene girmez.
CHARLSON = ["charlson", "charlson_yassiz", "diyabet", "periferik_damar", "kalp_yetmezligi"]
HARIC = {"stay_id", "subject_id", "anchor_year_group", "am_pac_ilk", "am_pac_en_dusuk", *CHARLSON}
HARIC_ONEK = ("sure_saat", "olay_tipi", "yeni_by_72_168")
KATEGORIK = ["cinsiyet", "kabul_tipi", "ilk_yb_birimi", "jh_hlm_grup"]
AGAC = ["Random Forest", "XGBoost"]
BRADEN_LR = "Braden toplam (lojistik)"
KESIM_AD = {k: f"Braden <= {k}" for k in BRADEN_KESIMLER}
# AUROC farki (DeLong): (model, karsilastirilan)
KARSILASTIRMA = ([(m, BRADEN_LR) for m in ["L2 lojistik", "Random Forest", "XGBoost"]]
                 + [("XGBoost", "L2 lojistik"), ("Random Forest", "L2 lojistik")])
satir_hata = []


def hata_kaydet(analiz, e):
    print(f"  [HATA] {analiz}: {type(e).__name__}: {e}")
    satir_hata.append({"analiz": analiz, "hata": f"{type(e).__name__}: {e}"})


# ---- Veri ----
yol = ozel / "analiz_seti.parquet"
if not yol.exists():
    raise SystemExit(f"{yol} yok. Once 05_analiz_seti.py calistirin.")
ham = pd.read_parquet(yol).merge(pd.read_parquet(ozel / "04_kohort.parquet", columns=["stay_id", "subject_id"]),
                                 on="stay_id", how="left", validate="1:1")
birim_n = ham["ilk_yb_birimi"].value_counts()
ham["ilk_yb_birimi"] = ham["ilk_yb_birimi"].where(~ham["ilk_yb_birimi"].isin(birim_n[birim_n < SEYREK_BIRIM].index),
                                                  "diger")
kaynak = [s for s in ham.columns if s not in HARIC and not s.startswith(HARIC_ONEK)]
X = pd.get_dummies(ham[kaynak], columns=KATEGORIK, dtype=float).astype(float)
X.columns = [str(c).replace("[", "(").replace("]", ")").replace("<", "lt") for c in X.columns]  # XGBoost adlari
X_ch = pd.concat([X, ham[CHARLSON].astype(float)], axis=1)  # duyarlilik: Charlson'li ozellik seti
y = ham[HEDEF].to_numpy().astype(int)
grup = ham["subject_id"].to_numpy()
# Braden yoksa risk yok sayilir (07g'de sayisi)
kesim = {k: (ham[BRADEN] <= k).to_numpy().astype(int) for k in BRADEN_KESIMLER}
alt_grup = pd.DataFrame({
    "cinsiyet": ham["cinsiyet"],
    "yas_grubu": pd.cut(ham["yas"], [-np.inf, 64, 79, np.inf], labels=["<65", "65-79", "80+"]).astype(str),
    "ilk_yb_birimi": ham["ilk_yb_birimi"]})

ozellik = pd.DataFrame({"ozellik": X.columns, "eksik_yuzde": 100 * X.isna().mean().to_numpy()})
ozellik["kaynak_degisken"] = ozellik["ozellik"]
ozellik["tip"] = "sayisal"
for k in KATEGORIK:
    kukla = ozellik["ozellik"].str.startswith(f"{k}_")
    ozellik.loc[kukla, ["kaynak_degisken", "tip"]] = [k, "kukla"]
ozellik[["ozellik", "kaynak_degisken", "tip", "eksik_yuzde"]].to_csv(paylas / "07a_ozellikler.csv", index=False,
                                                                    encoding="utf-8-sig")


# ---------------------------------------------------------------
# Modeller ve hiperparametre arama
# ---------------------------------------------------------------
def modeller():
    """Ad -> (model, arama dagilimi). Agirliksiz: dengesizlik duzeltmesi kalibrasyonu bozar (README)."""
    atama = dict(strategy="median", add_indicator=True)
    return {
        "L2 lojistik": (
            make_pipeline(SimpleImputer(**atama), StandardScaler(),
                          LogisticRegression(max_iter=5000)),
            {"logisticregression__C": loguniform(1e-4, 1e2)}),
        "Random Forest": (
            make_pipeline(SimpleImputer(**atama),
                          RandomForestClassifier(random_state=a.tohum, n_jobs=1)),
            {"randomforestclassifier__n_estimators": randint(200, 801),
             "randomforestclassifier__max_depth": [None, 4, 6, 8, 12, 16],
             "randomforestclassifier__min_samples_leaf": randint(1, 51),
             "randomforestclassifier__max_features": ["sqrt", "log2", 0.2, 0.4]}),
        "XGBoost": (
            XGBClassifier(tree_method="hist", eval_metric="logloss", random_state=a.tohum,
                          n_jobs=1),
            {"n_estimators": randint(100, 801), "max_depth": randint(2, 9), "learning_rate": loguniform(0.01, 0.3),
             "subsample": uniform(0.6, 0.4), "colsample_bytree": uniform(0.5, 0.5),
             "min_child_weight": randint(1, 11), "reg_lambda": loguniform(0.1, 10)}),
    }


def braden_lr():
    return make_pipeline(SimpleImputer(strategy="median"), LogisticRegression(C=np.inf, max_iter=1000))


def ayarla(model, dagilim, Xe, ye, ge):
    s = RandomizedSearchCV(model, dagilim, n_iter=a.deneme, scoring="roc_auc", n_jobs=-1, refit=True,
                           cv=GroupKFold(n_splits=3, shuffle=True, random_state=a.tohum), random_state=a.tohum,
                           error_score="raise")
    return s.fit(Xe, ye, groups=ge)


def model_yolu(ad, onek):
    return model_klasor / f"{onek}{ad.replace(' ', '_').lower()}.joblib"


def egit_tahmin(e, t, analiz_tipi, kat, onek, charlsonlu=False):
    """e ile egit (yalnizca degerlendirmede kayitli modeli yukle), t'ye tahmin. Donus: model adi -> tahmin.
    Modeller onek ile kaydedilir; hiperparametreler listeye, birincil modeller 'egitilmis' sozlugune.
    charlsonlu: X_ch ile uc model (Braden lojistik yok; Braden toplam iki sette ayni)."""
    Xm = X_ch if charlsonlu else X
    tah = {}
    for ad, (model, dagilim) in modeller().items():
        if DEGERLENDIRME:
            m = joblib.load(model_yolu(ad, onek))
        else:
            s = ayarla(model, dagilim, Xm.iloc[e], y[e], grup[e])
            m = s.best_estimator_
            hiper.append({"analiz_tipi": analiz_tipi, "ozellik_seti": "charlsonlu" if charlsonlu else "birincil",
                          "kat": kat, "model": ad, "ic_cd_auroc": s.best_score_,
                          "parametreler": str({k: getattr(v, "item", lambda: v)() for k, v in s.best_params_.items()})})
            joblib.dump(m, model_yolu(ad, onek))
        tah[ad] = m.predict_proba(Xm.iloc[t])[:, 1]
        if not charlsonlu:
            egitilmis[(analiz_tipi, ad)] = m
    if charlsonlu:
        return tah
    if DEGERLENDIRME:
        bl = joblib.load(model_yolu("braden_lojistik", onek))
    else:
        bl = braden_lr().fit(X.iloc[e][[BRADEN]], y[e])
        joblib.dump(bl, model_yolu("braden_lojistik", onek))
    tah[BRADEN_LR] = bl.predict_proba(X.iloc[t][[BRADEN]])[:, 1]
    return tah


hiper, bolme, egitilmis, tahminler = [], [], {}, {}  # tahminler: analiz_tipi -> (indeks, model -> tahmin)

# (a) Ic dogrulama: ic ice capraz dogrulama
try:
    if min(y.sum(), (1 - y).sum()) < 5:
        raise ValueError(f"72-168 saat olay sayisi ic ice capraz dogrulama icin yetersiz ({int(y.sum())})")
    oof = {}
    if DEGERLENDIRME:  # kayitli dis katlar (test stay_id'leri); kat egitim seti = digerleri
        sid = ham["stay_id"].to_numpy()
        katlar = [(np.flatnonzero(~np.isin(sid, ts)), np.flatnonzero(np.isin(sid, ts)))
                  for ts in joblib.load(model_klasor / "ic_katlar.joblib")]
    else:
        katlar = list(GroupKFold(n_splits=5, shuffle=True, random_state=a.tohum).split(X, y, grup))
        joblib.dump([ham["stay_id"].to_numpy()[t] for _, t in katlar], model_klasor / "ic_katlar.joblib")
    for k, (e, t) in enumerate(katlar):
        for ad, pr in egit_tahmin(e, t, "ic_dogrulama", k + 1, f"ic_kat{k + 1}_").items():
            oof.setdefault(ad, np.full(len(y), np.nan))[t] = pr
        print(f"  ic dogrulama: dis kat {k + 1}/{len(katlar)} tamam")
    tahminler["ic_dogrulama"] = (np.arange(len(y)), oof)
    bolme.append({"analiz_tipi": "ic_dogrulama", "kume": "tum kohort (5 dis kat)", "yatis": len(y),
                  "hasta": len(set(grup)), "olay": int(y.sum())})
except Exception as e:
    hata_kaydet("ic_dogrulama", e)

# (b) Donemsel (anchor_year_group) dogrulama
try:
    egitim = ham["anchor_year_group"].isin(EGITIM_YIL).to_numpy()
    test = ~egitim & ham["anchor_year_group"].notna().to_numpy()
    cikan = test & np.isin(grup, grup[egitim])
    test &= ~cikan
    for kume, m in [("egitim (anchor_year_group 2008-2016)", egitim), ("test (anchor_year_group 2017-2022)", test),
                    ("testten cikarilan (egitimde de olan hasta)", cikan)]:
        bolme.append({"analiz_tipi": "donemsel_dogrulama", "kume": kume, "yatis": int(m.sum()),
                      "hasta": len(set(grup[m])), "olay": int(y[m].sum())})
    if min(y[egitim].sum(), (1 - y[egitim]).sum()) < 5 or min(y[test].sum(), (1 - y[test]).sum()) < 1:
        raise ValueError(f"donemsel bolmede olay yetersiz (egitim {int(y[egitim].sum())}, test {int(y[test].sum())})")
    e, t = np.flatnonzero(egitim), np.flatnonzero(test)
    tahminler["donemsel_dogrulama"] = (t, egit_tahmin(e, t, "donemsel_dogrulama", "egitim 2008-2016", ""))
    print("  donemsel dogrulama tamam")
except Exception as e:
    hata_kaydet("donemsel_dogrulama", e)

# (c) Duyarlilik: Charlson'li ozellik seti; birincil modelle ayni dis katlar ve donemsel bolme
tahminler_ch = {}
for tip, (ind, _) in list(tahminler.items()):
    try:
        if tip == "ic_dogrulama":
            oof = {}
            for k, (e, t) in enumerate(katlar):
                for ad, pr in egit_tahmin(e, t, tip, k + 1, f"charlsonlu_ic_kat{k + 1}_", charlsonlu=True).items():
                    oof.setdefault(ad, np.full(len(y), np.nan))[t] = pr
            tahminler_ch[tip] = (ind, oof)
        else:
            tahminler_ch[tip] = (ind, egit_tahmin(np.flatnonzero(egitim), ind, tip, "egitim 2008-2016", "charlsonlu_",
                                                  charlsonlu=True))
        print(f"  {tip} (Charlson'li duyarlilik) tamam")
    except Exception as e:
        hata_kaydet(f"charlsonlu_{tip}", e)
bolme.append({"analiz_tipi": "her ikisi", "kume": "Braden toplam yok (Braden kesim noktalarinda risk yok sayildi)",
              "yatis": int(ham[BRADEN].isna().sum()), "hasta": len(set(grup[ham[BRADEN].isna()])),
              "olay": int(y[ham[BRADEN].isna()].sum())})
kucuk_hucre_gizle(pd.DataFrame(bolme, columns=["analiz_tipi", "kume", "yatis", "hasta", "olay"]),
                  ["yatis", "hasta", "olay"]).to_csv(paylas / "07g_bolme.csv", index=False, encoding="utf-8-sig")
if not DEGERLENDIRME:
    pd.DataFrame(hiper, columns=["analiz_tipi", "ozellik_seti", "kat", "model", "ic_cd_auroc", "parametreler"]).to_csv(
        paylas / "07e_hiperparametreler.csv", index=False, encoding="utf-8-sig")


# ---------------------------------------------------------------
# Metrikler
# ---------------------------------------------------------------

def logit(pr):
    pr = np.clip(pr, 1e-6, 1 - 1e-6)
    return np.log(pr / (1 - pr))


def olcumler(y_, pr, kesimler):
    """Olasilik tahmini icin metrikler. kesimler: kesim noktasi -> ayni satirlarda Braden <= k (0/1)."""
    lp = logit(pr)
    fpr, tpr, _ = roc_curve(y_, pr)
    # Kesim noktasinin duyarliliginda modelin ozgullugu (ROC'de duyarlilik ilk kez o degere ulastigi nokta)
    ozg = {f"ozgulluk_braden{k}_duyarliliginda": 1 - fpr[np.argmax(tpr >= kb[y_ == 1].mean())]
           for k, kb in kesimler.items()}
    return {"auroc": roc_auc_score(y_, pr), "auprc": average_precision_score(y_, pr),
            "brier": brier_score_loss(y_, pr),
            "kalibrasyon_egimi": sm.GLM(y_, sm.add_constant(lp), family=sm.families.Binomial()).fit().params[1],
            "kalibrasyon_kesisimi": sm.GLM(y_, np.ones((len(y_), 1)), family=sm.families.Binomial(),
                                           offset=lp).fit().params[0], **ozg}


def kesim_olcumleri(y_, kb):
    """Kesim noktasi (0/1): duyarlilik, ozgulluk, pozitif ve negatif kestirim degeri (PPD, NPD)."""
    return {"auroc": roc_auc_score(y_, kb), "duyarlilik": kb[y_ == 1].mean(), "ozgulluk": 1 - kb[y_ == 0].mean(),
            "ppd": y_[kb == 1].mean() if kb.any() else np.nan,
            "npd": 1 - y_[kb == 0].mean() if (kb == 0).any() else np.nan}


def ga(fonk, n, boot_i):
    """Nokta tahmini ve hasta duzeyinde (kume) yuzdelik bootstrap %95 GA (her metrik icin)."""
    nokta = fonk(np.arange(n))
    tekrar = pd.DataFrame([fonk(i) for i in boot_i], columns=list(nokta))
    return [{"metrik": k, "deger": v, "alt_95": tekrar[k].quantile(.025), "ust_95": tekrar[k].quantile(.975)}
            for k, v in nokta.items()]


metrik, farklar, altlar, metrik_ch, farklar_ch = [], [], [], [], []
for tip, (ind, tah) in tahminler.items():
    try:
        yt, kt = y[ind], {k: kb[ind] for k, kb in kesim.items()}
        boot_i = kume_bootstrap(yt, grup[ind], a.bootstrap, rng)
        temel = {"analiz_tipi": tip, "n": len(yt), "olay": int(yt.sum()), "bootstrap_tekrar": len(boot_i)}
        for ad, pr in tah.items():
            metrik += [{**temel, "model": ad, **r}
                       for r in ga(lambda i: olcumler(yt[i], pr[i], {k: kb[i] for k, kb in kt.items()}), len(yt),
                                   boot_i)]
        for m1, m2 in KARSILASTIRMA:
            fark, se, p_d = delong(yt, tah[m1], tah[m2])
            farklar.append({"analiz_tipi": tip, "model": m1, "karsilastirma": m2, "auroc_farki": fark,
                            "alt_95": fark - 1.96 * se, "ust_95": fark + 1.96 * se, "p_delong": p_d})
        for k, kb in kt.items():
            metrik += [{**temel, "model": KESIM_AD[k], **r}
                       for r in ga(lambda i: kesim_olcumleri(yt[i], kb[i]), len(yt), boot_i)]
        # Duyarlilik: Charlson'li modeller, ayni bootstrap orneklemleri; DeLong Charlson'li - birincil
        try:
            for ad, pr in tahminler_ch.get(tip, (None, {}))[1].items():
                metrik_ch += [{**temel, "model": ad, **r}
                              for r in ga(lambda i: olcumler(yt[i], pr[i], {k: kb[i] for k, kb in kt.items()}),
                                          len(yt), boot_i)]
                fark, se, p_d = delong(yt, pr, tah[ad])
                farklar_ch.append({"analiz_tipi": tip, "model": ad, "auroc_charlsonlu": roc_auc_score(yt, pr),
                                   "auroc_birincil": roc_auc_score(yt, tah[ad]), "auroc_farki": fark,
                                   "alt_95": fark - 1.96 * se, "ust_95": fark + 1.96 * se, "p_delong": p_d})
        except Exception as e:
            hata_kaydet(f"metrikler_charlsonlu_{tip}", e)
        # Alt gruplar: olay ve olaysiz en az 5 ise AUROC
        for deg in alt_grup.columns:
            for ag, m in alt_grup.iloc[ind].groupby(deg, observed=True).indices.items():
                ya = yt[m]
                yeter = min(ya.sum(), (1 - ya).sum()) >= 5
                bi = kume_bootstrap(ya, grup[ind][m], a.bootstrap, rng) if yeter else []
                for ad, pr in tah.items():
                    au = [roc_auc_score(ya[i], pr[m][i]) for i in bi]
                    altlar.append({"analiz_tipi": tip, "alt_grup_degiskeni": deg, "alt_grup": ag, "model": ad,
                                   "n": len(ya), "olay": int(ya.sum()),
                                   "auroc": roc_auc_score(ya, pr[m]) if yeter else np.nan,
                                   "alt_95": np.quantile(au, .025) if au else np.nan,
                                   "ust_95": np.quantile(au, .975) if au else np.nan})
    except Exception as e:
        hata_kaydet(f"metrikler_{tip}", e)

sutun = ["analiz_tipi", "model", "metrik", "deger", "alt_95", "ust_95", "n", "olay", "bootstrap_tekrar", "belirleme"]
for liste, dosya in [(metrik_ch, "07b_metrikler_charlsonlu.csv"), (metrik, "07b_metrikler.csv")]:  # mt: birincil kalir
    mt = pd.DataFrame(liste, columns=sutun)
    mt["belirleme"] = "onceden_belirlenmis"
    for k, b in BRADEN_KESIMLER.items():
        mt.loc[(mt["model"] == KESIM_AD[k]) | (mt["metrik"] == f"ozgulluk_braden{k}_duyarliliginda"), "belirleme"] = b
    kucuk_hucre_gizle(mt, ["n", "olay"]).to_csv(paylas / dosya, index=False, encoding="utf-8-sig")
pd.DataFrame(farklar, columns=["analiz_tipi", "model", "karsilastirma", "auroc_farki", "alt_95", "ust_95",
                               "p_delong"]).to_csv(paylas / "07c_auroc_farki.csv", index=False, encoding="utf-8-sig")
pd.DataFrame(farklar_ch, columns=["analiz_tipi", "model", "auroc_charlsonlu", "auroc_birincil", "auroc_farki", "alt_95",
                                  "ust_95", "p_delong"]).to_csv(paylas / "07c_auroc_farki_charlsonlu.csv", index=False,
                                                                encoding="utf-8-sig")
ag = pd.DataFrame(altlar, columns=["analiz_tipi", "alt_grup_degiskeni", "alt_grup", "model", "n", "olay", "auroc",
                                   "alt_95", "ust_95"])
# Kucuk hucre: 1-4 "<5"; bir alt grup degiskeninde tek gizli kalirsa (toplam bilindiginden) en kucuk ikinci "gizli"
ag_p = kucuk_hucre_gizle(ag, ["n", "olay"]).astype({"n": object, "olay": object})
for s in ["n", "olay"]:
    olaysiz_kucuk = (ag["n"] - ag["olay"]).between(1, 4) if s == "olay" else False
    ag_p.loc[olaysiz_kucuk & (ag_p[s] != "<5"), s] = "gizli"  # n ile olay, olaysiz kucuk hucreyi verir
    for _, g in ag_p.groupby(["analiz_tipi", "alt_grup_degiskeni", "model"]):
        gz = g[s].isin(["<5", "gizli"])
        if gz.sum() == 1 and len(g) > 1:
            ag_p.loc[pd.to_numeric(g.loc[~gz, s]).idxmin(), s] = "gizli"
ag_p.to_csv(paylas / "07d_alt_gruplar.csv", index=False, encoding="utf-8-sig")


# ---------------------------------------------------------------
# Grafikler (PNG + SVG)
# ---------------------------------------------------------------
def kaydet(fig, ad, klasor=paylas):
    for uz in ("png", "svg"):
        fig.savefig(klasor / f"{ad}.{uz}", dpi=150, bbox_inches="tight")
    plt.close(fig)


ESIK = np.round(np.arange(0.02, 0.3001, 0.01), 2)


def net_fayda(y_, karar, esik):
    n = len(y_)
    return ((karar & (y_ == 1)).sum() / n) - ((karar & (y_ == 0)).sum() / n) * esik / (1 - esik)


FPR_IZGARA = np.linspace(0, 1, 100)  # ROC: sabit 1 - ozgulluk izgarasi


def kalibrasyon_dilimleri(yt_, pr_):
    """Tahmin ondaliklari: ortalama tahmin, gozlenen oran, n, olay. 5'ten az olayli (0 dahil) ya da olaysiz sayisi
    1-4 olan dilim gizlenir (gozlenen oran x n kucuk sayiyi verir); 5'ten az yatisli dilim de."""
    g = pd.DataFrame({"y": yt_, "p": pr_})
    g["dilim"] = pd.qcut(g["p"].rank(method="first"), 10, labels=False)
    o = g.groupby("dilim").agg(p=("p", "mean"), y=("y", "mean"), n=("y", "size"), olay=("y", "sum"))
    o["gizli"] = (o["n"] < 5) | (o["olay"] < 5) | (o["n"] - o["olay"]).between(1, 4)
    return o


egri = []  # 07h: grafiklerin toplu noktalari
for tip, (ind, tah) in tahminler.items():
    try:
        yt, kt = y[ind], {k: kb[ind] for k, kb in kesim.items()}
        isaret = {18: "ks", 14: "kD", 12: "k^"}
        for ad, pr in tah.items():
            fpr, tpr, _ = roc_curve(yt, pr)
            egri += [{"analiz_tipi": tip, "egri": "roc", "model": ad, "x": x_, "y": y_}  # dogrusal enterpolasyon
                     for x_, y_ in zip(FPR_IZGARA, np.interp(FPR_IZGARA, fpr, tpr))]
            o = kalibrasyon_dilimleri(yt, pr)
            egri += [{"analiz_tipi": tip, "egri": "kalibrasyon", "model": ad, "x": r_.p,
                      "y": np.nan if r_.gizli else r_.y, "n": r_.n, "olay": "gizli" if r_.gizli else r_.olay}
                     for r_ in o.itertuples()]
            egri += [{"analiz_tipi": tip, "egri": "karar", "model": ad, "x": e_, "y": net_fayda(yt, pr >= e_, e_)}
                     for e_ in ESIK]
        for k, kb in kt.items():
            egri.append({"analiz_tipi": tip, "egri": "roc_kesim", "model": KESIM_AD[k], "x": kb[yt == 0].mean(),
                         "y": kb[yt == 1].mean(), "belirleme": BRADEN_KESIMLER[k]})
            egri += [{"analiz_tipi": tip, "egri": "karar", "model": KESIM_AD[k], "x": e_,
                      "y": net_fayda(yt, kb == 1, e_), "belirleme": BRADEN_KESIMLER[k]} for e_ in ESIK]
        egri += [{"analiz_tipi": tip, "egri": "karar", "model": "herkese", "x": e_,
                  "y": net_fayda(yt, np.ones(len(yt), bool), e_)} for e_ in ESIK]
        egri += [{"analiz_tipi": tip, "egri": "karar", "model": "hic kimseye", "x": e_, "y": 0.0} for e_ in ESIK]
        fig, ax = plt.subplots(figsize=(6, 6))
        for ad, pr in tah.items():
            fpr, tpr, _ = roc_curve(yt, pr)
            ax.plot(fpr, tpr, label=f"{ad} (AUROC {roc_auc_score(yt, pr):.3f})")
        for k, kb in kt.items():
            ax.plot(kb[yt == 0].mean(), kb[yt == 1].mean(), isaret[k], label=KESIM_AD[k])
        ax.plot([0, 1], [0, 1], ":", color="grey")
        ax.set(xlabel="1 - ozgulluk", ylabel="Duyarlilik", title=f"ROC, {tip}")
        ax.legend(loc="lower right", fontsize=8)
        kaydet(fig, f"07_roc_{tip}")

        fig, ax = plt.subplots(figsize=(6, 6))
        for ad, pr in tah.items():
            kesinlik, duyarlilik, _ = precision_recall_curve(yt, pr)
            ax.plot(duyarlilik, kesinlik, label=f"{ad} (AUPRC {average_precision_score(yt, pr):.3f})")
        for k, kb in kt.items():
            if kb.any():
                ax.plot(kb[yt == 1].mean(), yt[kb == 1].mean(), isaret[k], label=KESIM_AD[k])
        ax.axhline(yt.mean(), ls=":", color="grey", label=f"Prevalans {yt.mean():.3f}")
        ax.set(xlabel="Duyarlilik", ylabel="Pozitif kestirim degeri", title=f"PR, {tip}")
        ax.legend(loc="upper right", fontsize=8)
        kaydet(fig, f"07_pr_{tip}")

        # Kalibrasyon: tahmin ondaliklarina gore gruplanmis (kucuk hucreli dilim cizilmez)
        fig, ax = plt.subplots(figsize=(6, 6))
        ust = 0
        for ad, pr in tah.items():
            o = kalibrasyon_dilimleri(yt, pr)
            o = o[~o["gizli"]]
            ax.plot(o["p"], o["y"], "o-", label=ad, ms=4)
            ust = max(ust, o["p"].max(), o["y"].max())
        ax.plot([0, ust], [0, ust], ":", color="grey")
        ax.set(xlabel="Ortalama tahmin (ondalik)", ylabel="Gozlenen oran", title=f"Kalibrasyon, {tip}")
        ax.legend(fontsize=8)
        kaydet(fig, f"07_kalibrasyon_{tip}")

        fig, ax = plt.subplots(figsize=(7, 5))
        for ad, pr in tah.items():
            ax.plot(ESIK, [net_fayda(yt, pr >= e, e) for e in ESIK], label=ad)
        ax.plot(ESIK, [net_fayda(yt, kt[18] == 1, e) for e in ESIK], "k--", label=KESIM_AD[18])
        ax.plot(ESIK, [net_fayda(yt, kt[12] == 1, e) for e in ESIK], "k-.", label=f"{KESIM_AD[12]} (sonradan)")
        herkes = [net_fayda(yt, np.ones(len(yt), bool), e) for e in ESIK]
        ax.plot(ESIK, herkes, color="grey", label="Herkese")
        ax.axhline(0, color="black", lw=0.8, label="Hic kimseye")
        ax.set(xlabel="Esik olasilik", ylabel="Net fayda", title=f"Karar egrisi, {tip}",
               ylim=(min(-0.01, -0.1 * yt.mean()), yt.mean() * 1.1))
        ax.legend(fontsize=8)
        kaydet(fig, f"07_karar_egrisi_{tip}")
    except Exception as e:
        hata_kaydet(f"grafikler_{tip}", e)

pd.DataFrame(egri, columns=["analiz_tipi", "egri", "model", "x", "y", "n", "olay", "belirleme"]).to_csv(
    paylas / "07h_egri_noktalari.csv", index=False, encoding="utf-8-sig")

# ---------------------------------------------------------------
# SHAP: en iyi agac modeli, donemsel test seti
# ---------------------------------------------------------------
try:
    if "donemsel_dogrulama" not in tahminler:
        raise ValueError("donemsel dogrulama yok")
    ind, tah = tahminler["donemsel_dogrulama"]
    en_iyi = max(AGAC, key=lambda ad: roc_auc_score(y[ind], tah[ad]))
    secim = np.sort(rng.choice(ind, min(len(ind), 2000), replace=False))  # RF SHAP suresi icin en fazla 2000
    Xs = X.iloc[secim]
    model = egitilmis[("donemsel_dogrulama", en_iyi)]
    if en_iyi == "Random Forest":
        on_islem, agac = model[:-1], model[-1]
        Xs = pd.DataFrame(on_islem.transform(Xs), columns=on_islem.get_feature_names_out(), index=Xs.index)
    else:
        agac = model
    sv = shap.TreeExplainer(agac).shap_values(Xs)
    sv = np.asarray(sv[1] if isinstance(sv, list) else sv)
    if sv.ndim == 3:  # (n, ozellik, sinif)
        sv = sv[..., 1]
    ort = pd.DataFrame({"analiz_tipi": "donemsel_dogrulama", "model": en_iyi, "ozellik": Xs.columns,
                        "ortalama_abs_shap": np.abs(sv).mean(axis=0), "n": len(Xs)})
    ort = ort.sort_values("ortalama_abs_shap", ascending=False).reset_index(drop=True)
    ort["sira"] = ort.index + 1
    kucuk_hucre_gizle(ort, ["n"]).to_csv(paylas / "07f_shap_ozet.csv", index=False, encoding="utf-8-sig")

    ilk = ort.head(20).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.barh(ilk["ozellik"], ilk["ortalama_abs_shap"], color="steelblue")
    ax.set(xlabel="Ortalama |SHAP|", title=f"{en_iyi}, donemsel test seti (ilk 20)")
    kaydet(fig, "07_shap_ortalama")

    # Gruplanmis bagimlilik: ozellik degeri ondaliklarina (10'dan az farkli degerde degerin kendisine) gore
    # ortalama SHAP; 5'ten az yatisli grup cizilmez, tek tek nokta yok
    fig, eksen = plt.subplots(2, 5, figsize=(18, 7))
    for ax, oz in zip(eksen.ravel(), ort["ozellik"].head(10)):
        g = pd.DataFrame({"x": Xs[oz].to_numpy(), "s": sv[:, list(Xs.columns).index(oz)]}).dropna()
        g["dilim"] = g["x"] if g["x"].nunique() <= 10 else pd.qcut(g["x"], 10, labels=False, duplicates="drop")
        o = g.groupby("dilim").agg(x=("x", "mean"), s=("s", "mean"), n=("s", "size"))
        o = o[o["n"] >= 5]
        ax.plot(o["x"], o["s"], "o-", color="darkred", ms=4)
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_title(oz, fontsize=9)
        ax.set_xlabel("Ozellik degeri (grup ortalamasi)", fontsize=8)
        ax.set_ylabel("Ortalama SHAP", fontsize=8)
    fig.tight_layout()
    kaydet(fig, "07_shap_bagimlilik")

    # Beeswarm: tek tek hasta noktalari -> yalnizca ozel
    shap.summary_plot(sv, Xs, show=False, max_display=20)
    plt.gcf().savefig(ozel / "07_shap_beeswarm.png", dpi=150, bbox_inches="tight")
    plt.close("all")
except Exception as e:
    hata_kaydet("shap", e)

# ---- Tahminler (yalnizca ozel) ve hatalar ----
pd.concat([pd.DataFrame({"analiz_tipi": tip, "stay_id": ham["stay_id"].to_numpy()[ind], "y": y[ind],
                         **{f"braden_{k}": kb[ind] for k, kb in kesim.items()}, **tah}) for tip, (ind, tah) in tahminler.items()]
          or [pd.DataFrame()]).to_parquet(ozel / "07_tahminler.parquet", index=False)
pd.DataFrame(satir_hata, columns=["analiz", "hata"]).to_csv(paylas / "07z_hatalar.csv", index=False,
                                                           encoding="utf-8-sig")
if len(mt):
    print(mt[mt["metrik"].isin(["auroc", "auprc"])][["analiz_tipi", "model", "metrik", "deger", "alt_95", "ust_95"]]
          .to_string(index=False))
if farklar_ch:
    print("\nDuyarlilik, Charlson'li - birincil AUROC:")
    print(pd.DataFrame(farklar_ch)[["analiz_tipi", "model", "auroc_charlsonlu", "auroc_birincil", "auroc_farki",
                                    "p_delong"]].to_string(index=False))
print(f"\n{len(satir_hata)} analizde hata (07z_hatalar.csv). Ciktilar: {paylas}")
