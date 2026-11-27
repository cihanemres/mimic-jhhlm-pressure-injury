"""Adim 10: Ikinci makale icin ek ciktilar. 07 ve 08 degismez; onlarin kayitli ciktilarini okur.

Girdi (hepsi <cikti>/ozel/): analiz_seti.parquet (05), 04_kohort.parquet (04; stay_id, subject_id),
07_modeller/ ve 07_tahminler.parquet (07; birincil modeller, dis katlar ve tahminler), 08_kumeler.parquet (08).
--veri gerekmez. Ciktilar yalnizca paylasilabilir/ altina; 1-4 arasi sayilar "<5", geri hesaplatan sayilar "gizli",
gizli sayinin yuzdesi bos.

Bolumler (--bolumler, varsayilan hepsi):
    a  10a_pencere_bilesimi.csv   tahmin kohortunda (ic dogrulama) ve donemsel test setinde yatislarin 168. saatteki
                                  durumu: yeni BY 72-168 saat | BY'siz YBU'de olum < 168 | BY'siz sag taburculuk < 168 |
                                  168. saatte YBU'de BY'siz (sonradan BY, 168 ve sonrasi cikis dahil)
    b  10b_metrikler.csv, 10b_auroc_farki.csv
                                  duyarlilik: 72-168 saatte BY'siz YBU'de olen yatislar egitimden ve testten cikarilir;
                                  07 ile ayni modeller, arama, dis katlar ve donemsel bolme. Birincil modellerin
                                  (07_tahminler) ayni yatislardaki metrikleri yaninda; DeLong: duyarlilik - birincil
                                  (ayni yatislar) ve 07c karsilastirmalari (modeller - Braden toplam lojistik ve
                                  XGBoost/RF - L2 lojistik) duyarlilik orneginde
    c  10c_metrikler.csv, 10c_auroc_farki.csv, 10c2_sofa_eksiklik.csv
                                  duyarlilik: sofa_24s (eksik bileseni 0 sayan toplam) cikarilir; alti SOFA bileseni
                                  birincil modeldeki gibi eksik birakilir (XGBoost NaN; LR ve RF medyan atama + eksiklik
                                  gostergesi). DeLong: duyarlilik - birincil (ayni yatislar). 10c2: bilesenlerin eksiklik
                                  orani (tum kohort, donemsel egitim, donemsel test)
    d  10d_doldurulan_blok.csv    yatis basina doldurulan blok sayisi (0-5) ve toplam doldurulan blok orani
    e  10e_kume_duyarlilik.csv    en az 4/6 blogu kayitli yatislarla GMM (08 ile ayni k ve ayarlar); 08 cozumuyle
                                  uyum (ARI) ve kume buyuklukleri
    f  10f_model_ayarlari.csv     07 donemsel egitim modellerinin (birincil) secilen hiperparametreleri ve arama
                                  araliklari, ozellik sayilari, LR'de olcekleme ve kategorik kodlama
    g  10g_degisken_zamani.csv    her aday degiskenin penceresi ve ozeti (ilk, en dusuk, en yuksek, ortalama, sayi,
                                  var/yok); koddan (05) uretilir, veri gerekmez
    10z_hatalar.csv

Bootstrap (07 ile ayni, istatistik_ortak.kume_bootstrap): hasta duzeyinde (kume) yuzdelik bootstrap; subject_id'ler
yerine koyarak cekilir, secilen hastalarin tum yatislari alinir.

Kullanim:
    python code/10_makale2_ek.py --cikti outputs_tam
    python code/10_makale2_ek.py --cikti outputs_tam --bolumler adefg   (b ve c model egitir, uzun surer)
"""
import argparse
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from istatistik_ortak import delong, kume_bootstrap  # noqa: E402
from kurallar import (BRADEN_ITEMID, LAB_EN_KOTU, MARUZIYET_SAAT, PENCERE_SAAT, SABIT_PENCERE_BITIS,  # noqa: E402
                      SEYREK_BIRIM, SOFA_SAAT)
from mimic_db import cikti_klasorleri, kucuk_hucre_gizle  # noqa: E402

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402
from scipy.stats import loguniform, randint, uniform  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import adjusted_rand_score, average_precision_score, brier_score_loss, roc_auc_score  # noqa: E402
from sklearn.mixture import GaussianMixture  # noqa: E402
from sklearn.model_selection import GroupKFold, RandomizedSearchCV  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

p = argparse.ArgumentParser(description="Ikinci makale icin ek ciktilar")
p.add_argument("--cikti", default="outputs", help="Ciktilarin klasoru (05, 07 ve 08'in yazdigi yer)")
p.add_argument("--bootstrap", type=int, default=1000, help="Bootstrap tekrar sayisi")
p.add_argument("--deneme", type=int, default=40, help="Model basina RandomizedSearchCV deneme sayisi (07 ile ayni)")
p.add_argument("--tohum", type=int, default=2026, help="Rastgele sayi tohumu (07 ve 08 ile ayni)")
p.add_argument("--bolumler", default="abcdefg", help="Calistirilacak bolumler (a-g), ornek: adefg")
a = p.parse_args()
BOL = set(a.bolumler)
ozel, paylas = cikti_klasorleri(a.cikti)
rng = np.random.default_rng(a.tohum)
model_klasor = ozel / "07_modeller"
for b_ in BOL:  # yalnizca calisan bolumlerin eski ciktilari silinir
    for eski in paylas.glob(f"10{b_}*"):
        eski.unlink()
warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------
# 07 ve 08 ile ayni tanimlar (orada degisirse burada da degismeli)
# ---------------------------------------------------------------
HEDEF = "yeni_by_72_168"
EGITIM_YIL = ["2008 - 2010", "2011 - 2013", "2014 - 2016"]
BRADEN = "braden_toplam_en_dusuk"
CHARLSON = ["charlson", "charlson_yassiz", "diyabet", "periferik_damar", "kalp_yetmezligi"]
HARIC = {"stay_id", "subject_id", "anchor_year_group", "am_pac_ilk", "am_pac_en_dusuk", *CHARLSON}
HARIC_ONEK = ("sure_saat", "olay_tipi", "yeni_by_72_168")
KATEGORIK = ["cinsiyet", "kabul_tipi", "ilk_yb_birimi", "jh_hlm_grup"]
BRADEN_LR = "Braden toplam (lojistik)"
MODELLER = ["L2 lojistik", "Random Forest", "XGBoost"]
KARSILASTIRMA = [(m, BRADEN_LR) for m in MODELLER] + [("XGBoost", "L2 lojistik"), ("Random Forest", "L2 lojistik")]
DONEM = SABIT_PENCERE_BITIS - MARUZIYET_SAAT  # sure_saat 72. saatten sayilir: < 96 = YB'de 168. saatten once
SOFA = ["sofa_solunum", "sofa_koagulasyon", "sofa_karaciger", "sofa_kardiyovaskuler", "sofa_mss", "sofa_bobrek"]
BLOK_SAAT = 12  # 08
N_BLOK = MARUZIYET_SAAT // BLOK_SAAT
BLOKLAR = [f"blok_{i * BLOK_SAAT}_{(i + 1) * BLOK_SAAT}" for i in range(N_BLOK)]
REG_COVAR = 1 / 12  # 08
EN_AZ_KAYITLI = 4  # 10e: en az 4/6 blok kayitli
satir_hata = []


def hata_kaydet(analiz, e):
    print(f"  [HATA] {analiz}: {type(e).__name__}: {e}")
    satir_hata.append({"analiz": analiz, "hata": f"{type(e).__name__}: {e}"})


def yaz(df, ad):
    df.to_csv(paylas / ad, index=False, encoding="utf-8-sig")
    print(f"  {ad} yazildi")


def tek_gizliyi_tamamla(df, sutun, gruplar):
    """Toplami bilinen bir grupta tek gizli hucre kalirsa en kucuk ikinci hucre de 'gizli' (08 ile ayni)."""
    for _, g in df.groupby(gruplar) if gruplar else [(None, df)]:
        gz = g[sutun].isin(["<5", "gizli"])
        if gz.sum() == 1 and len(g) > 1:
            df.loc[pd.to_numeric(g.loc[~gz, sutun]).idxmin(), sutun] = "gizli"
    return df


def gizle(df, sutun, gruplar=None, yuzde="yuzde"):
    """1-4 '<5' (onceden gizlenmis hucre aynen kalir), tamamlayici 'gizli', gizli hucrenin yuzdesi bos."""
    p_ = df.copy()
    p_[sutun] = pd.Series([v if isinstance(v, str) or pd.isna(v) or not 0 < v < 5 else "<5" for v in p_[sutun]],
                          dtype=object, index=p_.index)
    p_ = tek_gizliyi_tamamla(p_, sutun, gruplar)
    if yuzde in p_:
        p_.loc[p_[sutun].isin(["<5", "gizli"]), yuzde] = np.nan
    return p_


# ---- Veri (a, b, c): 07 ile ayni ozellik matrisi ve donemsel bolme ----
ham = None
if BOL & set("abc"):
    try:
        ham = pd.read_parquet(ozel / "analiz_seti.parquet").merge(
            pd.read_parquet(ozel / "04_kohort.parquet", columns=["stay_id", "subject_id"]), on="stay_id", how="left",
            validate="1:1")
        birim_n = ham["ilk_yb_birimi"].value_counts()
        ham["ilk_yb_birimi"] = ham["ilk_yb_birimi"].where(
            ~ham["ilk_yb_birimi"].isin(birim_n[birim_n < SEYREK_BIRIM].index), "diger")
        kaynak = [s for s in ham.columns if s not in HARIC and not s.startswith(HARIC_ONEK)]
        X = pd.get_dummies(ham[kaynak], columns=KATEGORIK, dtype=float).astype(float)
        X.columns = [str(c).replace("[", "(").replace("]", ")").replace("<", "lt") for c in X.columns]
        y = ham[HEDEF].to_numpy().astype(int)
        grup = ham["subject_id"].to_numpy()
        sid = ham["stay_id"].to_numpy()
        egitim = ham["anchor_year_group"].isin(EGITIM_YIL).to_numpy()
        test = ~egitim & ham["anchor_year_group"].notna().to_numpy() & ~np.isin(grup, grup[egitim])
    except Exception as e:
        hata_kaydet("veri", e)
        ham = None

# ---------------------------------------------------------------
# a. 72-168 saat penceresinin bilesimi
# ---------------------------------------------------------------
DURUM = ["yeni BY 72-168 saat", "BY'siz YBU'de olum < 168. saat", "BY'siz sag taburculuk < 168. saat",
         "168. saatte YBU'de, BY'siz"]
if ham is not None:
    sure, ot = ham["sure_saat"].to_numpy(), ham["olay_tipi"].to_numpy()
    durum = np.select([y == 1, (ot == "yb_olum") & (sure < DONEM), (ot == "taburculuk") & (sure < DONEM)],
                      DURUM[:3], DURUM[3])
    KUMELER = [("ic_dogrulama", "tum tahmin kohortu", np.ones(len(y), bool)),
               ("donemsel_dogrulama", "test (anchor_year_group 2017-2022)", test)]
if "a" in BOL:
    try:
        if ham is None:
            raise ValueError("analiz seti yuklenemedi")
        t_ = pd.DataFrame([{"analiz_tipi": tip, "kume": kad, "kume_yatis": int(m.sum()), "durum_168_saat": d_,
                            "yatis": int((durum[m] == d_).sum()),
                            "yuzde": 100 * (durum[m] == d_).mean() if m.any() else np.nan}
                           for tip, kad, m in KUMELER for d_ in DURUM])
        yaz(gizle(t_, "yatis", ["analiz_tipi"]), "10a_pencere_bilesimi.csv")
    except Exception as e:
        hata_kaydet("10a_pencere_bilesimi", e)


# ---------------------------------------------------------------
# b, c. Duyarlilik modelleri (07 ile ayni modeller, arama, bolmeler)
# ---------------------------------------------------------------
def modeller():
    """07 ile ayni: ad -> (model, arama dagilimi)."""
    atama = dict(strategy="median", add_indicator=True)
    return {
        "L2 lojistik": (
            make_pipeline(SimpleImputer(**atama), StandardScaler(), LogisticRegression(max_iter=5000)),
            {"logisticregression__C": loguniform(1e-4, 1e2)}),
        "Random Forest": (
            make_pipeline(SimpleImputer(**atama), RandomForestClassifier(random_state=a.tohum, n_jobs=1)),
            {"randomforestclassifier__n_estimators": randint(200, 801),
             "randomforestclassifier__max_depth": [None, 4, 6, 8, 12, 16],
             "randomforestclassifier__min_samples_leaf": randint(1, 51),
             "randomforestclassifier__max_features": ["sqrt", "log2", 0.2, 0.4]}),
        "XGBoost": (
            XGBClassifier(tree_method="hist", eval_metric="logloss", random_state=a.tohum, n_jobs=1),
            {"n_estimators": randint(100, 801), "max_depth": randint(2, 9), "learning_rate": loguniform(0.01, 0.3),
             "subsample": uniform(0.6, 0.4), "colsample_bytree": uniform(0.5, 0.5),
             "min_child_weight": randint(1, 11), "reg_lambda": loguniform(0.1, 10)}),
    }


def bolmeler(maske):
    """07'nin dis katlari (ozel/07_modeller/ic_katlar.joblib; yoksa 07'deki gibi yeniden) ve donemsel bolme,
    maske disindaki yatislar cikarilarak. Donus: analiz_tipi -> [(egitim indeksleri, test indeksleri)]."""
    yol = model_klasor / "ic_katlar.joblib"
    if yol.exists():
        test_m = [np.isin(sid, ts) for ts in joblib.load(yol)]
    else:
        test_m = [np.isin(np.arange(len(y)), t_) for _, t_ in
                  GroupKFold(n_splits=5, shuffle=True, random_state=a.tohum).split(X, y, grup)]
    return {"ic_dogrulama": [(np.flatnonzero(~tm & maske), np.flatnonzero(tm & maske)) for tm in test_m],
            "donemsel_dogrulama": [(np.flatnonzero(egitim & maske), np.flatnonzero(test & maske))]}


def egit(Xm, e, t, braden):
    if min(y[e].sum(), (1 - y[e]).sum()) < 5 or min(y[t].sum(), (1 - y[t]).sum()) < 1:
        raise ValueError(f"olay yetersiz (egitim {int(y[e].sum())}, test {int(y[t].sum())})")
    tah = {}
    for ad, (model, dagilim) in modeller().items():
        s = RandomizedSearchCV(model, dagilim, n_iter=a.deneme, scoring="roc_auc", n_jobs=-1, refit=True,
                               cv=GroupKFold(n_splits=3, shuffle=True, random_state=a.tohum), random_state=a.tohum,
                               error_score="raise").fit(Xm.iloc[e], y[e], groups=grup[e])
        tah[ad] = s.best_estimator_.predict_proba(Xm.iloc[t])[:, 1]
    if braden:
        bl = make_pipeline(SimpleImputer(strategy="median"), LogisticRegression(C=np.inf, max_iter=1000))
        tah[BRADEN_LR] = bl.fit(X.iloc[e][[BRADEN]], y[e]).predict_proba(X.iloc[t][[BRADEN]])[:, 1]
    return tah


def tahmin_et(etiket, Xm, maske, braden):
    sonuc = {}
    for tip, katlar in bolmeler(maske).items():
        try:
            oof = {}
            for k, (e, t) in enumerate(katlar):
                for ad, pr in egit(Xm, e, t, braden).items():
                    oof.setdefault(ad, np.full(len(y), np.nan))[t] = pr
                print(f"  {etiket} {tip}: kat {k + 1}/{len(katlar)} tamam")
            ind = np.sort(np.concatenate([t for _, t in katlar]))
            sonuc[tip] = (ind, {ad: v[ind] for ad, v in oof.items()})
        except Exception as e:
            hata_kaydet(f"{etiket}_{tip}", e)
    return sonuc


def birincil_tahmin(tip, ind):
    """07'nin birincil tahminleri (07_tahminler.parquet), ayni yatislar ve sirada."""
    t7 = pd.read_parquet(ozel / "07_tahminler.parquet")
    if "analiz_tipi" not in t7:
        raise ValueError("07_tahminler.parquet bos (07 model kuramamis)")
    t7 = t7[t7["analiz_tipi"] == tip].set_index("stay_id").reindex(sid[ind])
    sut = [m for m in MODELLER + [BRADEN_LR] if m in t7]
    if t7[sut].isna().any().any():
        raise ValueError(f"07_tahminler.parquet'te {tip} icin eksik yatis")
    return {m: t7[m].to_numpy() for m in sut}


def logit(pr):
    pr = np.clip(pr, 1e-6, 1 - 1e-6)
    return np.log(pr / (1 - pr))


def olcumler(y_, pr):
    """07 ile ayni AUROC, AUPRC, Brier, kalibrasyon egimi ve kesisimi."""
    lp = logit(pr)
    return {"auroc": roc_auc_score(y_, pr), "auprc": average_precision_score(y_, pr),
            "brier": brier_score_loss(y_, pr),
            "kalibrasyon_egimi": sm.GLM(y_, sm.add_constant(lp), family=sm.families.Binomial()).fit().params[1],
            "kalibrasyon_kesisimi": sm.GLM(y_, np.ones((len(y_), 1)), family=sm.families.Binomial(),
                                           offset=lp).fit().params[0]}


def ga(fonk, n, boot_i):
    nokta = fonk(np.arange(n))
    tekrar = pd.DataFrame([fonk(i) for i in boot_i], columns=list(nokta))
    return [{"metrik": k, "deger": v, "alt_95": tekrar[k].quantile(.025), "ust_95": tekrar[k].quantile(.975)}
            for k, v in nokta.items()]


def degerlendir(on, sonuc, model_karsilastirma):
    """Duyarlilik ve birincil (ayni yatislar) metrikleri ayni bootstrap orneklemleriyle; DeLong farklari."""
    metrik, fark = [], []
    for tip, (ind, tah) in sonuc.items():
        try:
            yt = y[ind]
            bir = birincil_tahmin(tip, ind)
            boot_i = kume_bootstrap(yt, grup[ind], a.bootstrap, rng)
            temel = {"analiz_tipi": tip, "n": len(yt), "olay": int(yt.sum()), "bootstrap_tekrar": len(boot_i)}
            for surum, tahs in [("duyarlilik", tah), ("birincil (ayni yatislar)", {m: bir[m] for m in tah})]:
                for ad, pr in tahs.items():
                    metrik += [{**temel, "surum": surum, "model": ad, **r}
                               for r in ga(lambda i: olcumler(yt[i], pr[i]), len(yt), boot_i)]
            # Braden lojistik tek degiskenli (monoton): AUROC'u birincille hep ayni, DeLong karsilastirmasi yok
            ciftler = [(m, tah[m], f"{m}, birincil (ayni yatislar)", bir[m]) for m in tah if m != BRADEN_LR]
            ciftler += [(m1, tah[m1], m2, tah[m2]) for m1, m2 in model_karsilastirma]
            for m1, p1, m2, p2 in ciftler:
                f_, se, p_d = delong(yt, p1, p2)
                fark.append({"analiz_tipi": tip, "model": m1, "karsilastirma": m2, "auroc_model": roc_auc_score(yt, p1),
                             "auroc_karsilastirma": roc_auc_score(yt, p2), "auroc_farki": f_,
                             "alt_95": f_ - 1.96 * se, "ust_95": f_ + 1.96 * se, "p_delong": p_d,
                             "n": len(yt), "olay": int(yt.sum())})
        except Exception as e:
            hata_kaydet(f"{on}_metrikler_{tip}", e)
    sut = ["analiz_tipi", "surum", "model", "metrik", "deger", "alt_95", "ust_95", "n", "olay", "bootstrap_tekrar"]
    yaz(kucuk_hucre_gizle(pd.DataFrame(metrik, columns=sut), ["n", "olay"]), f"{on}_metrikler.csv")
    sut = ["analiz_tipi", "model", "karsilastirma", "auroc_model", "auroc_karsilastirma", "auroc_farki", "alt_95",
           "ust_95", "p_delong", "n", "olay"]
    yaz(kucuk_hucre_gizle(pd.DataFrame(fark, columns=sut), ["n", "olay"]), f"{on}_auroc_farki.csv")
    if fark:
        print(pd.DataFrame(fark)[["analiz_tipi", "model", "karsilastirma", "auroc_farki", "p_delong"]]
              .to_string(index=False))


if "b" in BOL:
    try:
        if ham is None:
            raise ValueError("analiz seti yuklenemedi")
        kalan = durum != DURUM[1]  # BY'siz YBU'de olum < 168. saat cikarilir
        print(f"10b: {int((~kalan).sum())} yatis cikarildi (BY'siz YBU'de olum < 168. saat)")
        degerlendir("10b", tahmin_et("10b", X, kalan, braden=True), KARSILASTIRMA)
    except Exception as e:
        hata_kaydet("10b", e)

if "c" in BOL:
    try:
        if ham is None:
            raise ValueError("analiz seti yuklenemedi")
        # SOFA eksiklik oranlari; tum kohort ~ egitim + test oldugundan bir gruptaki gizli sayi digerlerinden
        # bulunabilir: bir degiskende herhangi bir hucre gizliyse o satirin diger gruplari da gizlenir
        sofa_eksik = ham[SOFA].isna()
        sat = []
        for kad, m in [("tum kohort", np.ones(len(ham), bool)), ("donemsel egitim (2008-2016)", egitim),
                       ("donemsel test (2017-2022)", test)]:
            for s in SOFA + ["en az bir bilesen", "sofa_24s"]:
                ek = (sofa_eksik.any(axis=1) if s == "en az bir bilesen" else ham[s].isna())[m]
                sat.append({"kume": kad, "kume_yatis": int(m.sum()), "degisken": s, "eksik": int(ek.sum()),
                            "yuzde": 100 * ek.mean() if m.any() else np.nan,
                            "not": "eksik bilesen toplamda 0 sayilir" if s == "sofa_24s" else ""})
        se_ = pd.DataFrame(sat)
        se_p = kucuk_hucre_gizle(se_, ["eksik"]).astype({"eksik": object})
        tumleyen = (se_["kume_yatis"] - se_["eksik"]).between(1, 4) & (se_p["eksik"] != "<5")
        se_p.loc[tumleyen, "eksik"] = "gizli"
        for s in se_p["degisken"].unique():
            m_ = se_p["degisken"] == s
            if se_p.loc[m_, "eksik"].isin(["<5", "gizli"]).any():
                se_p.loc[m_ & ~se_p["eksik"].isin(["<5"]), "eksik"] = "gizli"
        se_p.loc[se_p["eksik"].isin(["<5", "gizli"]), "yuzde"] = np.nan
        yaz(se_p, "10c2_sofa_eksiklik.csv")
    except Exception as e:
        hata_kaydet("10c2_sofa_eksiklik", e)
    try:
        if ham is None:
            raise ValueError("analiz seti yuklenemedi")
        Xs = X.drop(columns="sofa_24s")
        print(f"10c: sofa_24s cikarildi; bilesenler ozellikte: {[s for s in SOFA if s in Xs]}")
        degerlendir("10c", tahmin_et("10c", Xs, np.ones(len(y), bool), braden=False), [])
    except Exception as e:
        hata_kaydet("10c", e)

# ---------------------------------------------------------------
# d, e. Kumeleme: doldurulan bloklar ve en az 4/6 kayitli blokla duyarlilik
# ---------------------------------------------------------------
k8 = None
if BOL & set("de"):
    try:
        k8 = pd.read_parquet(ozel / "08_kumeler.parquet")
    except Exception as e:
        hata_kaydet("08_kumeler", e)

if "d" in BOL and k8 is not None:
    try:
        n_ = len(k8)
        dag = k8["doldurulan_blok"].value_counts().reindex(range(N_BLOK), fill_value=0)
        d_ = pd.DataFrame({"analiz_tipi": "kesfedici", "olcu": "yatis basina doldurulan blok sayisi",
                           "kategori": [str(i) for i in dag.index], "yatis": dag.to_numpy(),
                           "yuzde": 100 * dag.to_numpy() / n_})
        d_ = gizle(d_, "yatis")
        # Toplam doldurulan blok (agirlikli toplam) yatis toplamiyla birlikte gizli hucreleri cozdurebilir:
        # dagilimda gizli hucre varsa toplam da gizlenir
        top = int(k8["doldurulan_blok"].sum())
        gz = d_["yatis"].isin(["<5", "gizli"]).any()
        d_ = pd.concat([d_, pd.DataFrame([{"analiz_tipi": "kesfedici", "olcu": "toplam doldurulan blok",
                                           "kategori": "gizli" if gz else f"{top} / {N_BLOK * n_} blok", "yatis": n_,
                                           "yuzde": np.nan if gz else 100 * top / (N_BLOK * n_)}])],
                       ignore_index=True)
        yaz(d_, "10d_doldurulan_blok.csv")
    except Exception as e:
        hata_kaydet("10d_doldurulan_blok", e)

if "e" in BOL and k8 is not None:
    try:
        alt = k8[k8["doldurulan_blok"] <= N_BLOK - EN_AZ_KAYITLI]
        K = k8["kume"].nunique()
        Ya = alt[BLOKLAR].to_numpy()
        if len(np.unique(Ya, axis=0)) < K:
            raise ValueError(f"farkli yorunge sayisi k'dan ({K}) az")
        gm = GaussianMixture(n_components=K, covariance_type="full", reg_covar=REG_COVAR, n_init=10,
                             random_state=a.tohum).fit(Ya)
        sira = np.argsort(gm.means_.mean(axis=1))  # 08 ile ayni: 1 = ortalama yorungesi en dusuk
        yeni_no = np.empty(K, int)
        yeni_no[sira] = np.arange(1, K + 1)
        yeni = pd.Series(yeni_no[gm.predict(Ya)], index=alt.index).map(lambda c: f"kume_{c}")
        ari = adjusted_rand_score(alt["kume"], yeni)
        kumeler = sorted(k8["kume"].unique(), key=lambda x: int(x.split("_")[1]))
        e_ = pd.DataFrame({"analiz_tipi": "kesfedici", "k": K, "kume": kumeler,
                           "yatis_08_tum": [int((k8["kume"] == c).sum()) for c in kumeler],
                           "yatis_08_alt_kume": [int((alt["kume"] == c).sum()) for c in kumeler],
                           "yatis_yeni_cozum": [int((yeni == c).sum()) for c in kumeler]})
        e_["yuzde_08_alt_kume"] = 100 * e_["yatis_08_alt_kume"] / len(alt)
        e_["yuzde_yeni_cozum"] = 100 * e_["yatis_yeni_cozum"] / len(alt)
        e_["alt_kume_yatis"], e_["dislanan_yatis"], e_["ari"] = len(alt), len(k8) - len(alt), ari
        e_p = kucuk_hucre_gizle(e_, ["yatis_08_tum", "yatis_08_alt_kume", "yatis_yeni_cozum", "dislanan_yatis"])
        e_p = e_p.astype({"yatis_08_alt_kume": object, "alt_kume_yatis": object})
        if 0 < len(k8) - len(alt) < 5:  # kohort - alt kume = dislanan
            e_p["alt_kume_yatis"] = "gizli"
        # 08b'deki tum kume buyuklugu - alt kume = o kumenin dislanan yatislari; 1-4 ise alt kume sayisi gizli
        e_p.loc[(e_["yatis_08_tum"] - e_["yatis_08_alt_kume"]).between(1, 4)
                & (e_p["yatis_08_alt_kume"] != "<5"), "yatis_08_alt_kume"] = "gizli"
        # Bolumleme ayniysa (ARI = 1) yeni cozumun buyuklukleri alt kume sayilarina esittir: onlar da gizlenir
        if np.isclose(ari, 1) and e_p["yatis_08_alt_kume"].isin(["<5", "gizli"]).any():
            e_p = e_p.astype({"yatis_yeni_cozum": object})
            e_p["yatis_yeni_cozum"] = "gizli"
        for s, yz in [("yatis_08_alt_kume", "yuzde_08_alt_kume"), ("yatis_yeni_cozum", "yuzde_yeni_cozum")]:
            e_p = gizle(e_p, s, None, yuzde=yz)
        yaz(e_p, "10e_kume_duyarlilik.csv")
        print(f"10e: {len(alt)} yatis (>= {EN_AZ_KAYITLI}/{N_BLOK} blok kayitli), k = {K}, ARI {ari:.3f}")
    except Exception as e:
        hata_kaydet("10e_kume_duyarlilik", e)


# ---------------------------------------------------------------
# f. 07 donemsel egitim modellerinin ayarlari
# ---------------------------------------------------------------
def aralik(d_):
    """Arama dagilimini okunur yazar (scipy randint ust sinir haric)."""
    if isinstance(d_, list):
        return "secenekler: " + ", ".join(map(str, d_))
    ad, arg, kw = d_.dist.name, d_.args, d_.kwds
    if ad in ("loguniform", "reciprocal"):
        return f"log-duzgun [{arg[0]}, {arg[1]}]"
    if ad == "randint":
        return f"tamsayi [{arg[0]}, {arg[1] - 1}]"
    if ad == "uniform":
        loc, olcek = (arg + (kw.get("loc", 0), kw.get("scale", 1)))[:2]
        return f"duzgun [{loc}, {loc + olcek}]"
    return f"{ad}{arg}"


if "f" in BOL:
    try:
        sat = []

        def ekle(model, bolum, parametre, deger, arama=""):
            sat.append({"model": model, "bolum": bolum, "parametre": parametre, "deger": deger, "arama_araligi": arama})

        dagilim = {ad: d_ for ad, (_, d_) in modeller().items()}
        e7 = paylas / "07e_hiperparametreler.csv"
        e7 = pd.read_csv(e7, encoding="utf-8-sig") if e7.exists() else pd.DataFrame(columns=["analiz_tipi"])
        e7 = e7[(e7["analiz_tipi"] == "donemsel_dogrulama") & (e7.get("ozellik_seti") == "birincil")]
        ANAHTAR = {"L2 lojistik": ["C", "penalty", "l1_ratio", "solver", "max_iter", "class_weight", "fit_intercept"],
                   "Random Forest": ["n_estimators", "max_depth", "min_samples_leaf", "max_features",
                                     "min_samples_split", "criterion", "bootstrap", "class_weight"],
                   "XGBoost": ["n_estimators", "max_depth", "learning_rate", "subsample", "colsample_bytree",
                               "min_child_weight", "reg_lambda", "reg_alpha", "gamma", "tree_method", "eval_metric",
                               "scale_pos_weight", "objective"],
                   BRADEN_LR: ["C", "solver", "max_iter"]}
        for ad in MODELLER + [BRADEN_LR]:
            yol = model_klasor / f"{ad.replace(' ', '_').lower() if ad != BRADEN_LR else 'braden_lojistik'}.joblib"
            if not yol.exists():
                raise FileNotFoundError(f"{yol} yok (07 donemsel model kuramamis ya da calistirilmamis)")
            m = joblib.load(yol)
            adimlar = getattr(m, "steps", [(type(m).__name__.lower(), m)])
            son = adimlar[-1][1]
            prm = son.get_params()
            ara = {k.split("__")[-1]: aralik(v) for k, v in dagilim.get(ad, {}).items()}
            for k in ANAHTAR[ad]:
                if k in prm and str(prm[k]) != "deprecated":  # yeni sklearn'de penalty yerine l1_ratio (0 = L2)
                    v = prm[k]
                    ekle(ad, "hiperparametre", k, "None (xgboost varsayilani)" if v is None and ad == "XGBoost"
                         else str(v), ara.get(k, "sabit"))
            r7 = e7[e7.get("model") == ad] if len(e7) else e7
            if len(r7):
                ekle(ad, "arama", "ic CV AUROC (secilen ayar)", f"{float(r7['ic_cd_auroc'].iloc[0]):.4f}")
            if ad != BRADEN_LR:
                ekle(ad, "arama", "yontem", f"RandomizedSearchCV, 07 --deneme varsayilani 40 deneme, ic GroupKFold(3, "
                     f"hasta), olcut AUROC, egitim seti anchor_year_group 2008-2016")
            # Ozellikler
            adlar = list(getattr(m, "feature_names_in_", getattr(son, "feature_names_in_", [])))
            n_giris = int(getattr(m, "n_features_in_", len(adlar)))
            atay = dict(adimlar).get("simpleimputer")
            gosterge = ([adlar[i] for i in atay.indicator_.features_] if atay is not None
                        and getattr(atay, "indicator_", None) is not None else [])
            ekle(ad, "ozellik", "giris ozellik sayisi", n_giris)
            ekle(ad, "ozellik", "eksiklik gostergesi sayisi", len(gosterge))
            ekle(ad, "ozellik", "modele giren sutun sayisi", n_giris + len(gosterge))
            if gosterge:
                ekle(ad, "ozellik", "eksiklik gostergesi eklenen ozellikler", "; ".join(gosterge))
            if ad != BRADEN_LR:
                for k in KATEGORIK:
                    kk = [c for c in adlar if c.startswith(f"{k}_")]
                    ekle(ad, "kodlama", f"kategorik: {k}", f"one-hot, tum duzeyler (referans dusurulmez), "
                         f"{len(kk)} kukla" + (f"; {SEYREK_BIRIM}'den az yatisli birimler 'diger'"
                                               if k == "ilk_yb_birimi" else ""))
            ekle(ad, "kodlama", "on isleme adimlari", " -> ".join(type(s_).__name__ for _, s_ in adimlar))
            if atay is not None:
                ekle(ad, "kodlama", "eksik veri", f"SimpleImputer(strategy={atay.strategy}, "
                     f"add_indicator={atay.add_indicator}); egitim setinde fit")
            elif ad == "XGBoost":
                ekle(ad, "kodlama", "eksik veri", "atama yok; NaN dogal olarak (her bolmede ogrenilen varsayilan yon)")
            if any(isinstance(s_, StandardScaler) for _, s_ in adimlar):
                ekle(ad, "kodlama", "olcekleme", "StandardScaler: atamadan sonra tum sutunlar (sayisal, kukla, eksiklik "
                     "gostergesi) egitim setinin ortalamasi 0, SD 1")
            else:
                ekle(ad, "kodlama", "olcekleme", "yok")
        yaz(pd.DataFrame(sat), "10f_model_ayarlari.csv")
    except Exception as e:
        hata_kaydet("10f_model_ayarlari", e)

# ---------------------------------------------------------------
# g. Degisken olcum zamani (05'in kurallarindan; veri gerekmez)
# ---------------------------------------------------------------
if "g" in BOL:
    try:
        P24, P72, PH = f"0-{SOFA_SAAT} saat", f"0-{PENCERE_SAAT} saat", f"hastane yatisi basi - {PENCERE_SAAT}. saat"
        ICD = "hastane yatisi (taburculuk ICD kodlari, zaman yok)"
        g_ = [("yas", "demografi", "YB girisi", "tek deger", "anchor_age + (giris yili - anchor_year)"),
              ("cinsiyet", "demografi", "sabit", "tek deger", "patients"),
              ("kabul_tipi", "demografi", "hastane yatisi", "tek deger", "admissions.admission_type"),
              ("ilk_yb_birimi", "demografi", "YB girisi", "tek deger",
               f"first_careunit; modelde {SEYREK_BIRIM}'den az yatisli birimler 'diger'"),
              ("anchor_year_group", "demografi", "sabit", "tek deger", "donemsel bolme degiskeni"),
              ("boy_cm", "antropometri", PH, "ilk", "120-220 cm araligindaki ilk kayit"),
              ("kilo_kg", "antropometri", PH, "ilk", "25-300 kg araligindaki ilk kayit"),
              ("bmi", "antropometri", PH, "ilk", "ilk boy ve ilk kilodan; 12-70 disi bos"),
              ("sofa_24s", "SOFA", P24, "en kotu", "alti bilesen puaninin toplami; eksik bilesen 0"),
              ("sofa_solunum", "SOFA", P24, "en kotu", "en dusuk PaO2/FiO2 (arteriyel; IMV icinde ve disinda)"),
              ("sofa_koagulasyon", "SOFA", P24, "en kotu", "en dusuk trombosit"),
              ("sofa_karaciger", "SOFA", P24, "en kotu", "en yuksek bilirubin"),
              ("sofa_kardiyovaskuler", "SOFA", P24, "en kotu", "en dusuk OAB, en yuksek vazopresor/dobutamin hizi"),
              ("sofa_mss", "SOFA", P24, "en kotu", "en dusuk GKS"),
              ("sofa_bobrek", "SOFA", P24, "en kotu", "en yuksek kreatinin, toplam idrar"),
              ("mekanik_ventilasyon", "tedavi", P72, "var/yok", "invaziv ventilasyon araligi pencereyle ortusen"),
              ("vazopresor", "tedavi", P72, "var/yok", "vazopresor araligi pencereyle ortusen"),
              ("sedatif_propofol", "tedavi", P72, "var/yok", "surekli infuzyon araligi pencereyle ortusen"),
              ("sedatif_midazolam", "tedavi", P72, "var/yok", "surekli infuzyon araligi pencereyle ortusen"),
              ("sedatif_deksmedetomidin", "tedavi", P72, "var/yok", "surekli infuzyon araligi pencereyle ortusen"),
              ("sedatif_herhangi", "tedavi", P72, "var/yok", "uc sedatiften herhangi biri"),
              ("rass_en_dusuk", "tedavi", P72, "en dusuk", "RASS"),
              ("rass_ortalama", "tedavi", P72, "ortalama", "RASS, kayitlarin ortalamasi"),
              ("fiziksel_kisitlama", "tedavi", P72, "var/yok", "'On' kaydi")]
        for g0, yon in LAB_EN_KOTU.items():
            ad = g0.removeprefix("lab_")
            g_ += [(f"{ad}_ilk", "laboratuvar", P72, "ilk", "labevents, ayni hastane yatisi"),
                   (f"{ad}_en_kotu", "laboratuvar", P72, "en dusuk" if yon == "min" else "en yuksek",
                    "labevents, ayni hastane yatisi; en kotu deger")]
        g_ += [("charlson", "komorbidite", ICD, "tek deger", "Charlson indeksi"),
               ("charlson_yassiz", "komorbidite", ICD, "tek deger", "Charlson - yas puani"),
               ("diyabet", "komorbidite", ICD, "var/yok", ""),
               ("periferik_damar", "komorbidite", ICD, "var/yok", ""),
               ("kalp_yetmezligi", "komorbidite", ICD, "var/yok", "")]
        for ozt, son_ek in [("ilk", "_ilk"), ("en dusuk", "_en_dusuk")]:
            for b_ in ["toplam", *BRADEN_ITEMID.values(), "mobilite_disi"]:
                g_.append((f"braden_{b_}{son_ek}", "Braden", P72, ozt, "alti alt boyutun ayni anda kayitli oldugu tam "
                           "setler" + ("; mobilite disi = duyusal algi + nem + beslenme + surtunme"
                                       if b_ == "mobilite_disi" else "")))
        g_ += [("jh_hlm_ilk", "JH-HLM", P72, "ilk", "ayni anda celiskili kayitta en yuksek duzey"),
               ("jh_hlm_en_yuksek", "JH-HLM", P72, "en yuksek", ""),
               ("jh_hlm_ortalama", "JH-HLM", P72, "ortalama", ""),
               ("jh_hlm_kayit_sayisi", "JH-HLM", P72, "sayi", "farkli kayit zamani"),
               ("jh_hlm_grup", "JH-HLM", P72, "en yuksek", "en yuksek duzeyin grubu (1-3, 4-5, 6-8)"),
               ("pozisyon_degistirme_24s", "hemsirelik", P72, "sayi", "farkli kayit zamani / 3 (24 saat basina)"),
               ("tedavi_edici_yatak", "hemsirelik", P72, "var/yok", "'None' disi kayit"),
               ("basinc_azaltici_cihaz", "hemsirelik", P72, "var/yok", "'None' disi kayit"),
               ("yardimci_cihaz", "hemsirelik", P72, "var/yok", "'None' ve 'Independent' disi kayit"),
               ("rn_mobilite_hedefi", "hemsirelik", P72, "var/yok", "bos olmayan kayit"),
               ("am_pac_ilk", "hemsirelik", P72, "ilk", ""),
               ("am_pac_en_dusuk", "hemsirelik", P72, "en dusuk", ""),
               ("ncp_impaired_mobility", "hemsirelik", P72, "var/yok", "bakim plani, bos olmayan kayit"),
               ("ncp_activity_intolerance", "hemsirelik", P72, "var/yok", "bakim plani, bos olmayan kayit"),
               ("ncp_skin_integrity", "hemsirelik", P72, "var/yok", "bakim plani, bos olmayan kayit")]
        gt = pd.DataFrame(g_, columns=["degisken", "grup", "pencere", "ozet", "aciklama"])
        gt["model_07_birincil"] = np.where(gt["degisken"].isin(HARIC), "hayir", "evet")
        gt["model_07_charlsonlu"] = np.where(gt["degisken"].isin(HARIC - set(CHARLSON)), "hayir", "evet")
        gt.loc[gt["degisken"].isin(KATEGORIK), ["model_07_birincil", "model_07_charlsonlu"]] = "evet (one-hot)"
        yaz(gt, "10g_degisken_zamani.csv")
        aset = ozel / "analiz_seti.parquet"
        if aset.exists():  # analiz setiyle karsilastir (yalnizca ad listesi)
            sut = {s for s in pd.read_parquet(aset).columns if s != "stay_id" and not s.startswith(HARIC_ONEK)}
            fark = (sut ^ set(gt["degisken"]))
            if fark:
                hata_kaydet("10g_degisken_zamani", ValueError(f"analiz setiyle uyusmayan degiskenler: {sorted(fark)}"))
    except Exception as e:
        hata_kaydet("10g_degisken_zamani", e)

pd.DataFrame(satir_hata, columns=["analiz", "hata"]).to_csv(paylas / "10z_hatalar.csv", index=False,
                                                           encoding="utf-8-sig")
print(f"\n{len(satir_hata)} analizde hata (10z_hatalar.csv). Ciktilar: {paylas}")
