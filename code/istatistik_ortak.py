"""06, 07 ve 08'in ortak istatistik fonksiyonlari."""
import numpy as np
import pandas as pd
from scipy import stats

from kurallar import ANALIZ_IKILI, ANALIZ_KATEGORIK
from mimic_db import kucuk_hucre_gizle, ozet_tablosu_gizle


def delong(y, p1, p2):
    """Iki iliskili AUROC farki icin DeLong testi (Sun ve Xu 2014 hizli algoritma). Donus: fark, se, p."""
    def midrank(x):
        sira = np.argsort(x)
        z = x[sira]
        r = np.zeros(len(x))
        i = 0
        while i < len(x):
            j = i
            while j < len(x) and z[j] == z[i]:
                j += 1
            r[i:j] = 0.5 * (i + j - 1) + 1
            i = j
        out = np.empty(len(x))
        out[sira] = r
        return out
    pos, neg = y == 1, y == 0
    m_, n_ = pos.sum(), neg.sum()
    v10, v01, auc = [], [], []
    for pr in (p1, p2):
        tx, ty, tz = midrank(pr[pos]), midrank(pr[neg]), midrank(pr)
        auc.append((tz[pos].sum() - m_ * (m_ + 1) / 2) / (m_ * n_))
        v10.append((tz[pos] - tx) / n_)
        v01.append(1 - (tz[neg] - ty) / m_)
    s = np.cov(np.array(v10)) / m_ + np.cov(np.array(v01)) / n_
    fark = auc[0] - auc[1]
    se = np.sqrt(s[0, 0] + s[1, 1] - 2 * s[0, 1])
    return fark, se, 2 * stats.norm.sf(abs(fark) / se) if se > 0 else np.nan


def smd_degeri(pay, payda):
    """Standartlastirilmis fark; payda 0 ise (iki grupta da varyans yok) tanimsiz -> bos."""
    return pay / payda if payda > 0 else np.nan


# Tamamlayici gizlemede mumkunse secilmeyen hucreler: baska tablolarda (kumulatif insidans, Cox olay sayilari)
# ayni sayi acik yazildigi icin bu hucreyi gizlemek bir sey korumaz, diger tablolardan geri hesaplanir.
SONUC_KORUNAN = {"olay_tipi": ["yeni_by"], "olay_tipi_evre2": ["yeni_by"], "olay_tipi_bilinen": ["yeni_by"]}


def tablo1(veri, grup_sut, ref, degiskenler, korunan=None):
    """Gruplara gore Tablo 1 (06a bicimi): kategorik/ikili icin sayi ve yuzde, sayisal icin medyan ve IQR,
    referans gruba gore SMD. Kucuk hucre gizli; tamamlayici gizleme satir (kategori) ve sutun (grup) yonunde
    (tablo1_tamamlayici). korunan: degisken -> tamamlayici gizlemede mumkunse secilmeyecek kategoriler."""
    gruplar = [g for g in veri[grup_sut].dropna().unique()]
    gruplar = [ref] + sorted(g for g in gruplar if g != ref)
    satirlar = []
    for s in [c for c in degiskenler if c != grup_sut]:
        kategorik = s in ANALIZ_KATEGORIK or s in ANALIZ_IKILI
        ref_x = veri.loc[veri[grup_sut] == ref, s]
        for g in gruplar:
            x = veri.loc[veri[grup_sut] == g, s]
            temel = {"degisken": s, "grup": g, "n_grup": len(x), "dolu": int(x.notna().sum()),
                     "bos": int(x.isna().sum()), "eksik_yuzde": 100 * x.isna().mean() if len(x) else None}
            if kategorik:
                for k in sorted(veri[s].dropna().unique(), key=str):
                    sayi = int((x == k).sum())
                    p1 = sayi / temel["dolu"] if temel["dolu"] else np.nan
                    p0 = (ref_x == k).sum() / ref_x.notna().sum() if ref_x.notna().sum() else np.nan
                    smd = (smd_degeri(p1 - p0, np.sqrt((p1 * (1 - p1) + p0 * (1 - p0)) / 2))
                           if g != ref and temel["dolu"] and ref_x.notna().sum() else np.nan)
                    satirlar.append({**temel, "tip": "kategorik", "kategori": k, "sayi": sayi,
                                     "yuzde": 100 * p1, "smd_ref": smd})
            else:
                x = pd.to_numeric(x, errors="coerce").astype(float)
                r = pd.to_numeric(ref_x, errors="coerce").astype(float)
                smd = (smd_degeri(x.mean() - r.mean(), np.sqrt((x.var() + r.var()) / 2))
                       if g != ref and x.notna().sum() > 1 and r.notna().sum() > 1 else np.nan)
                satirlar.append({**temel, "tip": "sayisal", "medyan": x.median(), "q1": x.quantile(.25),
                                 "q3": x.quantile(.75), "smd_ref": smd})
    t = pd.DataFrame(satirlar, columns=["degisken", "tip", "kategori", "grup", "n_grup", "dolu", "bos",
                                        "eksik_yuzde", "sayi", "yuzde", "medyan", "q1", "q3", "smd_ref"])
    t["referans_grup"] = ref
    p_ = ozet_tablosu_gizle(t, ["degisken", "grup"], "eksik_yuzde", ek_gizle=["smd_ref"], korunan=korunan)
    p_ = tablo1_tamamlayici(p_, korunan)
    p_["n_grup"] = kucuk_hucre_gizle(p_, ["n_grup"])["n_grup"]
    return p_


def tablo1_tamamlayici(p_, korunan=None):
    """Tamamlayici gizleme: kategorinin gruplar arasi toplami (or. 05a) ve grubun dolu sayisi bilindiginden,
    bir kategoride (satir) veya bir grupta (sutun) tek gizli hucre kalirsa en kucuk ikinci hucre de gizlenir;
    korunan kategoriler ancak baska aday yoksa secilir. Degisiklik kalmayana kadar tekrarlanir; capraz
    gizlemeden (capraz_gizle) sonra yeniden cagrilir. Gizli hucrenin yuzdesi ve kategorinin SMD'si bos."""
    korunan = korunan or {}
    kat = p_["tip"] == "kategorik"
    degisti = True
    while degisti:
        degisti = False
        for anahtar_ in (["degisken", "kategori"], ["degisken", "grup"]):
            for _, g_ in p_[kat].groupby(anahtar_):
                gz = g_["sayi"].isin(["<5", "gizli"])
                if gz.sum() == 1 and len(g_) > 1:
                    aday = g_[~gz]
                    serbest = ~aday["kategori"].astype(str).isin(
                        [str(k) for k in korunan.get(aday["degisken"].iloc[0], [])])
                    if serbest.any():
                        aday = aday[serbest]
                    p_.loc[pd.to_numeric(aday["sayi"]).idxmin(), ["sayi", "yuzde"]] = ["gizli", None]
                    degisti = True
    p_.loc[p_["sayi"].isin(["<5", "gizli"]), "yuzde"] = None
    # Bir grupta gizlenen kategorinin SMD'si referans grubun sayisini da ele verebilir: ayni kategoride hepsini gizle
    gizli = p_["sayi"].isin(["<5", "gizli"])
    anahtar = p_["degisken"].astype(str) + "|" + p_["kategori"].astype(str)
    p_.loc[anahtar.isin(anahtar[gizli]), "smd_ref"] = None
    return p_


def tablo1_gizli_mi(t1, degisken, kategoriler, grup):
    """Tablo 1'de degisken x kategori x grup hucresi gizli mi (kategori 1 ile 1.0 ayni sayilir)."""
    kat = t1["kategori"].map(lambda k: str(int(k)) if isinstance(k, float) and float(k).is_integer() else str(k))
    m = (t1["degisken"] == degisken) & kat.isin([str(k) for k in kategoriler]) & (t1["grup"] == grup)
    return bool(t1.loc[m, "sayi"].isin(["<5", "gizli"]).any())


def capraz_gizle(df, maske, sutunlar):
    """Tablolar arasi gizleme: baska bir tabloda gizlenen bir hucreyle ayni (ya da onu geri hesaplatan) sayilar.
    maske satirlarinda sutunlar 'gizli' olur ("<5" aynen kalir). Donus: object sutunlu kopya."""
    df = df.copy()
    for s_ in sutunlar:
        df[s_] = df[s_].astype(object)
        df.loc[maske & ~df[s_].isin(["<5"]) & df[s_].notna(), s_] = "gizli"
    return df


# Ayni grupta (28 gun yeni BY) - (72-168 saat yeni BY) = 168. saatten sonraki yeni BY. Iki hucre de aciksa fark
# kucuk olabilir; donem tablolari (06j, 08h) bu farki ayrica yazar.
FARK_CIFTLERI = [("olay_tipi", "yeni_by_72_168"), ("olay_tipi_evre2", "yeni_by_72_168_evre2"),
                 ("olay_tipi_bilinen", "yeni_by_72_168_bilinen")]


def tablo1_fark_gizle(t1, veri, grup_sut, korunan=None):
    """Bir grupta yeni BY (28 gun) - yeni BY (72-168 saat) 1-4 ise o grubun 72-168 saat hucreleri (0 ve 1) gizlenir,
    sonra tamamlayici gizleme yeniden yapilir. Gercek degerler yalnizca karar icin kullanilir."""
    for g, x in veri.groupby(grup_sut):
        for tip, ikili in FARK_CIFTLERI:
            if tip in x and ikili in x and 0 < int((x[tip] == "yeni_by").sum() - x[ikili].sum()) < 5:
                t1 = capraz_gizle(t1, (t1["degisken"] == ikili) & (t1["grup"] == g), ["sayi"])
    return tablo1_tamamlayici(t1, korunan)


def sonuc_gizli_gruplar(t1, gruplar):
    """Tablo 1'de bir sonuc hucresi gizli olan gruplar ve gizli hucrelerin turu. Donus: grup -> kume
    {"yeni_by", "yeni_by_72_168", "sansur"}. Bu gruplarin olay sayilari, kumulatif insidansi ve risk altindaki
    sayilari diger tablolarda capraz_gizle / kumulatif_insidans_capraz ile gizlenir."""
    sonuc = {}
    for g in gruplar:
        tur = set()
        if tablo1_gizli_mi(t1, "olay_tipi", ["yeni_by"], g):
            tur.add("yeni_by")
        if tablo1_gizli_mi(t1, "yeni_by_72_168", ["1", "0"], g):
            tur.add("yeni_by_72_168")
        if tablo1_gizli_mi(t1, "olay_tipi", ["sansur"], g):
            tur.add("sansur")
        if tur:
            sonuc[g] = tur
    return sonuc


def kumulatif_insidans_capraz(ki, grup_sut, gizli, veri, veri_grup, sure_gun, olay_tipi, ikili_72_168):
    """Kumulatif insidans tablosunda Tablo 1'de gizlenen sonuc hucrelerini geri hesaplatan hucreleri gizler.
    Idari sansur yalnizca 28. gunde oldugu icin kumulatif_olay (ve kumulatif_insidans x n) o gune kadarki olay
    sayisinin kendisidir; risk_altinda 25. gunde idari sansur sayisidir. Bu yuzden gizli grupta
    - kumulatif_olay Tablo 1'de gizli yeni BY (28 gun) veya 72-168 saat sayisina esitse kumulatif_olay,
      kumulatif_insidans ve GA'si,
    - risk_altinda gizli idari sansur sayisina esitse risk_altinda
    'gizli' / bos yapilir. kumulatif_olay "<5" olan satirda da kumulatif_insidans bos (tum gruplarda). Gercek degerler yalnizca karar icin kullanilir, yazilmaz."""
    ki = capraz_gizle(ki, pd.Series(False, index=ki.index), ["kumulatif_olay", "risk_altinda"])
    # kumulatif_olay "<5" ise kumulatif_insidans x n o kucuk sayiyi verir
    ki.loc[ki["kumulatif_olay"] == "<5", ["kumulatif_insidans", "alt_95", "ust_95"]] = np.nan
    for g, tur in gizli.items():
        x = veri[veri[veri_grup] == g]
        olay_deg = set()
        if "yeni_by" in tur:
            olay_deg.add(int((x[olay_tipi] == "yeni_by").sum()))
        if "yeni_by_72_168" in tur:
            olay_deg.add(int(x[ikili_72_168].sum()))
        sansur = {int((x[olay_tipi] == "sansur").sum())} if "sansur" in tur else set()
        satir = ki[grup_sut] == g
        ko = pd.to_numeric(ki["kumulatif_olay"], errors="coerce")
        ra = pd.to_numeric(ki["risk_altinda"], errors="coerce")
        m_olay = satir & ko.isin(olay_deg)
        ki.loc[m_olay, "kumulatif_olay"] = "gizli"
        ki.loc[m_olay, ["kumulatif_insidans", "alt_95", "ust_95"]] = np.nan
        ki.loc[satir & ra.isin(sansur), "risk_altinda"] = "gizli"
    return ki


def aalen_johansen(t, kod):
    """Olay 1 icin kumulatif insidans; donus: (zamanlar, cif)."""
    sira = np.argsort(t, kind="stable")
    t, kod = t[sira], kod[sira]
    zaman, ilk = np.unique(t, return_index=True)
    risk = len(t) - ilk
    d1 = np.add.reduceat((kod == 1).astype(float), ilk)
    d_hepsi = np.add.reduceat((kod > 0).astype(float), ilk)
    s_once = np.concatenate([[1.0], np.cumprod(1 - d_hepsi / risk)[:-1]])
    return zaman, np.cumsum(s_once * d1 / risk)


def cif_noktada(zaman, cif, noktalar):
    i = np.searchsorted(zaman, noktalar, side="right") - 1
    return np.where(i >= 0, cif[np.clip(i, 0, None)], 0.0)


def rubin(katsayilar, varyanslar):
    q, u = np.array(katsayilar), np.array(varyanslar)
    m = len(q)
    qbar, w = q.mean(0), u.mean(0)
    b = q.var(0, ddof=1) if m > 1 else np.zeros_like(qbar)
    t = w + (1 + 1 / m) * b
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (1 + 1 / m) * b / w
        df = np.where(b > 0, (m - 1) * (1 + 1 / r) ** 2, np.inf)
    return qbar, np.sqrt(t), df
