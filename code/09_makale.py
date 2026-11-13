"""Adim 9 (Faz 5): Makale tablolari (.docx, APA 7) ve sekilleri (PNG 300 dpi + SVG), Turkce veya Ingilizce.

Girdi YALNIZCA <cikti>/paylasilabilir/ dosyalari (ozel/ okunmaz) ve config/itemids_onayli.csv (ek tablo; kayit ve
yatis sayisi sutunlari alinmaz). Gizlenmis hucreler ("<5", "gizli") aynen yazilir.
Cikti: <cikti>/makale_<dil>/ (T1-T6, E1-E5 .docx; S1-S7 .png/.svg; 09z_atlananlar.csv: girdisi olmayan ya da hata
veren tablo/sekiller). Hangi tablo/seklin hangi csv'den geldigi README "Makale tablolari ve sekilleri (09)".

Bicim: tr ondalik virgul, binlik nokta, "p < 0,001", "%95 GA"; en ondalik nokta, binlik virgul, "p < .001" (APA:
p'de bastaki sifir yok), "95% CI".

Kullanim:
    python code/09_makale.py --cikti outputs_tam --dil tr
    python code/09_makale.py --cikti outputs_tam --dil en
"""
import argparse
import re
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from etiketler import DEGISKEN, KATEGORI, ozellik_etiketi  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.section import WD_ORIENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt  # noqa: E402

p = argparse.ArgumentParser(description="Makale tablolari ve sekilleri")
p.add_argument("--cikti", default="outputs", help="Ciktilar klasoru (paylasilabilir/ buradan okunur)")
p.add_argument("--dil", choices=["tr", "en"], default="tr")
a = p.parse_args()
DIL = a.dil
kaynak = Path(a.cikti) / "paylasilabilir"
hedef = Path(a.cikti) / f"makale_{DIL}"
hedef.mkdir(parents=True, exist_ok=True)
for eski in hedef.glob("*"):
    eski.unlink()
warnings.filterwarnings("ignore", category=FutureWarning)
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none"})
atlanan = []
GIZLI = {"<5", "gizli"}


def oku(ad):
    yol = kaynak / ad
    return pd.read_csv(yol, dtype=object, encoding="utf-8-sig") if yol.exists() else None


def T(tr, en):
    return tr if DIL == "tr" else en


# ---------------------------------------------------------------
# Sayi bicimi
# ---------------------------------------------------------------
def sayi_mi(x):
    try:
        return np.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def gizli_yaz(x):
    """Gizli hucre: "<5" aynen; "gizli" Ingilizcede "suppressed"."""
    x = x.strip()
    return "suppressed" if (x == "gizli" and DIL == "en") else x


def ondalik(x, nd=2):
    """Gizli hucre (gizli_yaz); bos -> en tire; sayi dile gore."""
    if isinstance(x, str) and x.strip() in GIZLI:
        return gizli_yaz(x)
    if not sayi_mi(x):
        return "–"
    x = round(float(x), nd) + 0.0  # -0,00 yazilmasin
    s = f"{abs(x):,.{nd}f}"
    s = s.translate(str.maketrans({",": ".", ".": ","})) if DIL == "tr" else s
    return ("−" if x < 0 else "") + s  # APA: eksi isareti


def tam(x):
    if isinstance(x, str) and x.strip() in GIZLI:
        return gizli_yaz(x)
    return ondalik(round(float(x)), 0) if sayi_mi(x) else "–"


def esnek(x):
    """Medyan/IQR: tamsayiysa ondaliksiz, degilse 1 ondalik."""
    if not sayi_mi(x):
        return ondalik(x)
    return ondalik(x, 0) if float(x).is_integer() else ondalik(x, 1)


def p_bicim(x):
    if not sayi_mi(x):
        return "–"
    x = float(x)
    if x < 0.001:
        return T("< 0,001", "< .001")
    s = ondalik(x, 3)
    return s if DIL == "tr" else s.lstrip("0")


def etki_ga(e, lo, hi, nd=2):
    if not sayi_mi(e):
        return "–"
    if not (sayi_mi(lo) and sayi_mi(hi)):
        return ondalik(e, nd)
    return f"{ondalik(e, nd)} ({ondalik(lo, nd)}–{ondalik(hi, nd)})"


def n_yuzde(n, yuzde):
    if isinstance(n, str) and n.strip() in GIZLI:
        return gizli_yaz(n)
    if not sayi_mi(n):
        return "–"
    return f"{tam(n)} ({ondalik(yuzde, 1)})" if sayi_mi(yuzde) else tam(n)


GA = T("%95 GA", "95% CI")

# ---------------------------------------------------------------
# Etiketler
# ---------------------------------------------------------------
DEG = DEGISKEN  # etiketler.py: tum degisken ve ozellik etiketleri (Tablo 1, SHAP, ek tablolar)
KUME_AD = {  # ASCII ad (08) -> (tr, en)
    "yatakta kalan": ("Yatakta kalan", "Bed-bound"), "mobilitesi azalan": ("Mobilitesi azalan", "Declining mobility"),
    "gec mobilize olan (36. saat sonrasi)": ("Geç mobilize olan (36. saat sonrası)", "Late mobilization (after hour 36)"),
    "erken mobilize olan (12-36. saat)": ("Erken mobilize olan (12–36. saat)", "Early mobilization (hours 12–36)"),
    "bastan mobil": ("Baştan mobil", "Mobile from admission"), "gec mobilize olan": ("Geç mobilize olan", "Late mobilization"),
    "erken mobilize olan": ("Erken mobilize olan", "Early mobilization"), "erken yuruyen": ("Erken yürüyen", "Early walking"),
}
MODEL = {"L2 lojistik": ("L2 lojistik regresyon", "L2 logistic regression"), "Random Forest": ("Random Forest", "Random forest"),
         "XGBoost": ("XGBoost", "XGBoost"), "Braden toplam (lojistik)": ("Braden toplam (lojistik)", "Braden total (logistic)")}
ANALIZ = {"ic_dogrulama": ("İç doğrulama (iç içe çapraz doğrulama)", "Internal validation (nested cross-validation)"),
          "donemsel_dogrulama": ("Dönemsel doğrulama (anchor_year_group)", "Period validation (anchor_year_group)")}
DONEM = {"72-168 saat": ("72–168 saat", "72–168 h"), ">168 saat": ("> 168 saat", "> 168 h")}
ANALIZ_KISA = {"ic_dogrulama": ("iç doğrulama", "internal validation"),
               "donemsel_dogrulama": ("dönemsel doğrulama", "period validation")}
JH = {"jh_4_5": ("JH-HLM 4–5", "JH-HLM 4–5"), "jh_6_8": ("JH-HLM 6–8", "JH-HLM 6–8")}


def lab(sozluk, k):
    v = sozluk.get(k)
    return (v[0] if DIL == "tr" else v[1]) if v else str(k)


# Arastirmacilarin verdigi kume adlari (k, kume, yatis -> ad). Ad yalnizca kume buyuklugu dosyadakiyle ayniysa
# kullanilir (cozum degisirse eski ad yanlis kumeye gitmesin); degilse uyari verilir ve 08'in adina donulur.
_ka = Path("config/kume_adlari.csv")
KUME_ADLARI = ({(str(r.k), r.kume): r for r in pd.read_csv(_ka, dtype=str, encoding="utf-8-sig").itertuples()}
               if _ka.exists() else {})
KUME_AD.update({r.ad_tr: (r.ad_tr, r.ad_en) for r in KUME_ADLARI.values()})  # 08'in ad_onayli'si (ad_tr) -> en
_ka_uyari = set()


def _tamsayi_str(x):
    try:
        return str(int(float(x)))
    except (TypeError, ValueError):
        return str(x)


def config_adi(satir):
    """config/kume_adlari.csv'deki ad (k, kume ve yatis eslesirse); yoksa None."""
    anahtar = (_tamsayi_str(satir.get("k")), satir.get("kume"))
    r = KUME_ADLARI.get(anahtar)
    if r is None:
        return None
    if _tamsayi_str(satir.get("yatis")) != _tamsayi_str(r.yatis):
        if anahtar not in _ka_uyari:
            _ka_uyari.add(anahtar)
            print(f"  UYARI: k = {anahtar[0]} {anahtar[1]} yatis sayisi config/kume_adlari.csv ile ayni degil "
                  f"({_tamsayi_str(satir.get('yatis'))} / {r.yatis}); dosyadaki ad kullanilmadi")
        return None
    return r.ad_tr if DIL == "tr" else r.ad_en


def kume_adi(satir):
    ad = config_adi(satir)
    if ad:
        return ad
    ad = satir.get("ad_onayli") if isinstance(satir.get("ad_onayli"), str) and satir.get("ad_onayli") else satir.get("ad_onerisi")
    if not isinstance(ad, str) or not ad:
        return satir["kume"]
    if ad.startswith("orta duzeyde sabit"):
        return T("Orta düzeyde sabit", "Stable intermediate") + ad[len("orta duzeyde sabit"):]
    return lab(KUME_AD, ad)


etiketsiz = set()  # sozlukte olmayan ozellikler (ETIKET adiminda uyari ve 09z)


def ozellik_adi(o):
    """07 ozellik adi -> etiket (etiketler.py); sozlukte yoksa ham ad yazilir ve etiketsiz'e eklenir."""
    et = ozellik_etiketi(o, DIL)
    if et is None:
        etiketsiz.add(o)
        return o
    return et


# ---------------------------------------------------------------
# APA 7 tablo (.docx): yatay cizgiler, dikey cizgi yok, not satiri
# ---------------------------------------------------------------
def kenar(eleman, **taraflar):
    pr = eleman.get_or_add_tcPr() if hasattr(eleman, "get_or_add_tcPr") else eleman
    sinir = OxmlElement("w:tcBorders")
    for taraf, deger in taraflar.items():
        e = OxmlElement(f"w:{taraf}")
        e.set(qn("w:val"), deger)
        if deger != "nil":
            e.set(qn("w:sz"), "8")
            e.set(qn("w:color"), "000000")
        sinir.append(e)
    pr.append(sinir)


def apa_tablo(dosya, no, baslik, sutunlar, satirlar, not_, yatay=False, girinti=()):
    """satirlar: liste; her satir ya hucre listesi ya da ("panel", metin). girinti: girintili satir indeksleri."""
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(10)
    sec = doc.sections[0]
    if yatay:
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = sec.page_height, sec.page_width
    for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, m, Cm(2.54))
    p1 = doc.add_paragraph()
    p1.add_run(f"{T('Tablo', 'Table')} {no}").bold = True
    p2 = doc.add_paragraph()
    p2.add_run(baslik).italic = True
    tb = doc.add_table(rows=1 + len(satirlar), cols=len(sutunlar))
    tb.autofit = True
    for j, s in enumerate(sutunlar):
        c = tb.rows[0].cells[j]
        c.text = s
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
        kenar(c._tc, top="single", bottom="single", left="nil", right="nil")
    for i, satir in enumerate(satirlar, start=1):
        hucreler = tb.rows[i].cells
        if isinstance(satir, tuple) and satir[0] == "panel":
            birlesik = hucreler[0].merge(hucreler[-1])
            birlesik.text = ""
            birlesik.paragraphs[0].add_run(satir[1]).italic = True
            hucreler = [birlesik]
        else:
            for j, v in enumerate(satir):
                hucreler[j].text = str(v)
                hucreler[j].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            if (i - 1) in girinti:
                hucreler[0].paragraphs[0].paragraph_format.left_indent = Cm(0.4)
        son = i == len(satirlar)
        for c in hucreler:
            kenar(c._tc, top="nil", bottom="single" if son else "nil", left="nil", right="nil")
    for r_ in tb.rows:
        for c in r_.cells:
            for par in c.paragraphs:
                par.paragraph_format.space_after = Pt(0)
                for run in par.runs:
                    run.font.size = Pt(9)
    pn = doc.add_paragraph()
    pn.add_run(T("Not. ", "Note. ")).italic = True
    pn.add_run(not_)
    doc.save(hedef / dosya)


def eksen_bicim(eksen):
    """Eksen isaretleri 1, 2, 5 x 10^k adimlarla; ondalik sayisi adimdan (0,05 -> 2, 0,005 -> 3), dile gore."""
    eksen.set_major_locator(matplotlib.ticker.MaxNLocator(steps=[1, 2, 5, 10]))

    def bicim(v, _):
        loc = eksen.get_majorticklocs()
        adim = np.min(np.diff(loc)) if len(loc) > 1 else 1
        return ondalik(v, max(0, int(np.ceil(-np.log10(adim) - 1e-9))))
    eksen.set_major_formatter(matplotlib.ticker.FuncFormatter(bicim))


def sekil_kaydet(fig, ad):
    for uz in ("png", "svg"):
        fig.savefig(hedef / f"{ad}.{uz}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def etiket_kontrol():
    """07a'daki tum ozellikler ve 07f'deki SHAP ozellikleri (RF eksiklik gostergeleri dahil) sozlukte mi."""
    adlar = []
    for dosya in ["07a_ozellikler.csv", "07f_shap_ozet.csv"]:
        df = oku(dosya)
        if df is not None:
            adlar += df["ozellik"].tolist()
    if not adlar:
        raise FileNotFoundError("07a_ozellikler.csv ve 07f_shap_ozet.csv yok")
    for o in adlar:
        ozellik_adi(o)
    if etiketsiz:
        raise ValueError(f"etiket sozlugunde (code/etiketler.py) olmayan {len(etiketsiz)} ozellik: "
                         + "; ".join(sorted(etiketsiz)))


def calistir(ad, fonk):
    try:
        fonk()
        print(f"  {ad}: tamam")
    except Exception as e:  # girdi yoksa (demo) ya da beklenmeyen bicim: atlanir, 09z'ye yazilir
        print(f"  {ad}: ATLANDI ({type(e).__name__}: {e})")
        atlanan.append({"cikti": ad, "neden": f"{type(e).__name__}: {e}"})


def gerekli(ad):
    df = oku(ad)
    if df is None:
        raise FileNotFoundError(f"{ad} yok")
    return df


ROBUST_NOT = T("Cox, Fine-Gray ve lojistik modellerde standart hatalar hasta düzeyinde kümelenmiştir (robust sandwich; aynı "
                "hastanın birden fazla YB yatışı); kümelenmemiş GA'lar Ek Tablo E6'da. ",
                "In Cox, Fine-Gray and logistic models standard errors are clustered at the patient level (robust sandwich; "
                "patients with more than one ICU stay); non-clustered CIs are given in Supplementary Table E6. ")
GIZLI_NOT = T('"<5": 1–4 arası sayı; "gizli": küçük bir hücreyi geri hesaplatmasın diye gizlenen sayı (PhysioNet '
              'veri kullanım sözleşmesi).',
              '"<5": count between 1 and 4; "suppressed": count withheld so that a small cell cannot be '
              'back-calculated (PhysioNet data use agreement).')
KISALTMA = T("BY = basınç yarası; GA = güven aralığı; HR = hazard oranı; JH-HLM = Johns Hopkins Highest Level of "
             "Mobility; YB = yoğun bakım.",
             "CI = confidence interval; HR = hazard ratio; ICU = intensive care unit; JH-HLM = Johns Hopkins Highest "
             "Level of Mobility; PI = pressure injury.")


# ---------------------------------------------------------------
# T1 Kohort ozellikleri JH-HLM grubuna gore (06a)
# ---------------------------------------------------------------
T1_DEG = ["yas", "cinsiyet", "bmi", "ilk_yb_birimi", "sofa_24s", "mekanik_ventilasyon", "vazopresor", "sedatif_herhangi",
          "rass_en_dusuk", "fiziksel_kisitlama", "charlson_yassiz", "braden_toplam_en_dusuk",
          "braden_mobilite_disi_en_dusuk", "albumin_en_kotu", "jh_hlm_en_yuksek", "olay_tipi", "yeni_by_72_168"]


def tablo1_satirlari(t, gruplar, ref, degiskenler):
    satirlar, girinti = [], []
    smd_g = [g for g in gruplar if g != ref]
    for v in degiskenler:
        x = t[t["degisken"] == v]
        if x.empty:
            continue
        if x["tip"].iloc[0] == "sayisal":
            hucre = [f"{lab(DEG, v)}, {T('medyan (ÇAA)', 'median (IQR)')}"]
            for g in gruplar:
                r_ = x[x["grup"] == g].iloc[0]
                hucre.append(f"{esnek(r_['medyan'])} ({esnek(r_['q1'])}–{esnek(r_['q3'])})" if sayi_mi(r_["medyan"]) else "–")
            hucre += [ondalik(x.loc[x["grup"] == g, "smd_ref"].iloc[0]) for g in smd_g]
            satirlar.append(hucre)
            continue
        kats = list(dict.fromkeys(x["kategori"]))
        ikili = set(map(str, kats)) <= {"0", "1", "0.0", "1.0"}
        if ikili:
            kats, baslik = [k for k in kats if str(k) in ("1", "1.0")], f"{lab(DEG, v)}, n (%)"
        else:
            satirlar.append([f"{lab(DEG, v)}, n (%)"] + [""] * (len(gruplar) + len(smd_g)))
        for k in kats:
            xk = x[x["kategori"] == k]
            hucre = [baslik if ikili else lab(KATEGORI, k)]
            for g in gruplar:
                r_ = xk[xk["grup"] == g].iloc[0]
                hucre.append(n_yuzde(r_["sayi"], r_["yuzde"]))
            hucre += [ondalik(xk.loc[xk["grup"] == g, "smd_ref"].iloc[0]) for g in smd_g]
            if not ikili:
                girinti.append(len(satirlar))
            satirlar.append(hucre)
    return satirlar, girinti


def t1():
    t = gerekli("06a_tablo1_jhhlm.csv")
    t = t[t["tip"] != "not"]
    gruplar = ["1-3", "4-5", "6-8"]
    n_g = {g: t.loc[t["grup"] == g, "n_grup"].iloc[0] for g in gruplar}
    sut = [T("Özellik", "Characteristic")] + [f"JH-HLM {g.replace('-', '–')}\n(n = {tam(n_g[g])})" for g in gruplar] \
        + [f"SMD {g.replace('-', '–')}" for g in gruplar[1:]]
    satirlar, girinti = tablo1_satirlari(t, gruplar, "1-3", T1_DEG)
    apa_tablo("T1_kohort_ozellikleri.docx", 1,
              T("JH-HLM grubuna göre kohort özellikleri (0–72 saat)", "Cohort characteristics by JH-HLM group (hours 0–72)"),
              sut, satirlar, T("JH-HLM grubu 0–72 saatteki en yüksek düzeye göredir. SMD, JH-HLM 1–3'e göre standartlaştırılmış "
                              "ortalama farktır. Yüzdeler dolu kayıtlar içindir. 100'den az yatışı olan YB birimleri "
                              "\"Diğer\" olarak birleştirildi. ",
                              "JH-HLM group is based on the highest level in hours 0–72. SMD = standardized mean difference "
                              "versus JH-HLM 1–3. Percentages are of non-missing records. ICU units with fewer than 100 "
                              "stays were merged as \"Other\". ") + "ÇAA = çeyrekler arası aralık; " * (DIL == "tr")
              + "IQR = interquartile range; " * (DIL == "en") + KISALTMA + " " + GIZLI_NOT, yatay=True, girinti=girinti)


# ---------------------------------------------------------------
# T2 Birincil Cox: donem bazinda HR + ortalama HR + surekli etki + E-degerleri (06d, 06j)
# ---------------------------------------------------------------
def satir_bul(d, kod, terim, olcu=None):
    m = (d["analiz_kodu"] == kod) & (d["terim"] == terim)
    if olcu:
        m &= d["etki_olcusu"] == olcu
    return d[m].iloc[0] if m.any() else None


def t2():
    d = gerekli("06d_modeller.csv")
    j = oku("06j_donem_hr.csv")
    satirlar = []
    for terim in ["jh_4_5", "jh_6_8"]:
        b = satir_bul(d, "birincil", terim)
        bs = satir_bul(d, "birincil_strata_birim_yil", terim)
        hucre = [f"{lab(JH, terim)} {T('(ref. 1–3)', '(ref. 1–3)')}",
                 etki_ga(b["etki"], b["alt_95"], b["ust_95"]) if b is not None else "–", p_bicim(b["p"]) if b is not None else "–",
                 etki_ga(bs["etki"], bs["alt_95"], bs["ust_95"]) if bs is not None else "–"]
        for dn in ["72-168 saat", ">168 saat"]:
            r_ = j[(j["terim"] == terim) & (j["donem"] == dn)] if j is not None else pd.DataFrame()
            hucre.append(etki_ga(*r_.iloc[0][["etki", "alt_95", "ust_95"]]) if len(r_) else "–")
        r_ = j[(j["terim"] == terim) & j["donem"].str.startswith("etkilesim")] if j is not None else pd.DataFrame()
        hucre.append(p_bicim(r_.iloc[0]["p"]) if len(r_) else "–")
        for kod in ["birincil_e_degeri_hr", "birincil_e_degeri_sik"]:
            nk = satir_bul(d, kod, terim, "E-degeri (nokta tahmini)")
            sn = satir_bul(d, kod, terim, "E-degeri (GA'nin 1'e yakin siniri)")
            hucre.append(f"{ondalik(nk['etki'])} / {ondalik(sn['etki'])}" if nk is not None else "–")
        satirlar.append(hucre)
    h = satir_bul(d, "h_jh_surekli", "jh_hlm_en_yuksek")
    if h is not None:
        satirlar.append([T("JH-HLM en yüksek düzey, 1 düzey artış", "JH-HLM highest level, per 1-level increase"),
                         etki_ga(h["etki"], h["alt_95"], h["ust_95"]), p_bicim(h["p"])] + ["–"] * 6)
    b0 = satir_bul(d, "birincil", "jh_4_5")
    sut = [T("Maruziyet", "Exposure"), f"HR ({GA})", "p", f"HR ({GA}),\n{T('strata birim × dönem', 'strata unit × period')}",
           f"HR ({GA}),\n{lab(DONEM, '72-168 saat')}", f"HR ({GA}),\n{lab(DONEM, '>168 saat')}",
           T("Etkileşim p", "Interaction p"), T("E-değeri\n(HR)", "E-value\n(HR)"), T("E-değeri\n(sık sonuç)", "E-value\n(common outcome)")]
    n_txt = f"n = {tam(b0['n'])}, {T('olay', 'events')} = {tam(b0['olay'])}" if b0 is not None else ""
    apa_tablo("T2_birincil_cox.docx", 2,
              T("JH-HLM ile yeni basınç yarası: birincil cause-specific Cox modeli", "JH-HLM and new pressure injury: primary cause-specific Cox model"),
              sut, satirlar,
              T(f"{n_txt}. Cause-specific Cox; karıştırıcılar: yaş, cinsiyet, BKİ, SOFA, mekanik ventilasyon, vazopresör, "
                "sedatif, RASS, fiziksel kısıtlama, Braden mobilite dışı skor, Charlson, dönem; strata ilk YB birimi; MICE "
                "(m = 20), Rubin kuralları. Dönem bazında HR ve etkileşim (> 168 saat HR / 72–168 saat HR) strata birim × "
                "dönem modelinden (dönem kuklası yok). E-değeri: nokta tahmini / GA'nın 1'e yakın sınırı; \"HR\" sürümü "
                "HR'yi risk oranı sayar, \"sık sonuç\" sürümü VanderWeele (2017) dönüşümünü kullanır. ",
                f"{n_txt}. Cause-specific Cox model adjusted for age, sex, BMI, SOFA, mechanical ventilation, vasopressor, "
                "sedative, RASS, physical restraint, Braden non-mobility score, Charlson index and period; stratified by "
                "first ICU unit; multiple imputation (m = 20) pooled with Rubin's rules. Period-specific HRs and the "
                "interaction (HR > 168 h / HR 72–168 h) are from the model stratified by unit × period (no period terms). "
                "E-value: point estimate / CI limit closest to 1; the \"HR\" version treats the HR as a risk ratio, the "
                "\"common outcome\" version uses the VanderWeele (2017) conversion. ") + ROBUST_NOT + KISALTMA, yatay=True)


# ---------------------------------------------------------------
# T3 Duyarlilik analizleri (06d, 06i)
# ---------------------------------------------------------------
DUYARLILIK = [  # kod, tr, en
    ("birincil", "Birincil analiz", "Primary analysis"),
    ("a_fine_gray", "(a) Fine-Gray alt dağılım hazard modeli", "(a) Fine-Gray subdistribution hazard model"),
    ("b_evre2", "(b) Evre 2 ve üstü", "(b) Stage 2 or higher"),
    ("c_72_168", "(c) 72–168 saat, lojistik regresyon", "(c) Hours 72–168, logistic regression"),
    ("d_bilinmiyor_haric", "(d) Evresi bilinmeyen kayıt hariç", "(d) Unknown-stage records excluded"),
    ("e_albumin", "(e) Albümin eklenmiş", "(e) Albumin added"),
    ("f_onleyici", "(f) Önleyici girişimler eklenmiş", "(f) Preventive interventions added"),
    ("g_tam_kayit", "(g) Tam kayıtlı analiz", "(g) Complete-case analysis"),
    ("h_jh_surekli", "(h) JH-HLM sürekli (1 düzey)", "(h) JH-HLM continuous (per level)"),
    ("i_tt_log_zaman", "(i) Karıştırıcı × log(zaman) etkileşimi", "(i) Confounder × log(time) interaction"),
    ("birincil_strata_birim_yil", "(j) Strata birim × dönem", "(j) Strata unit × period"),
]
OLCU = {"HR": ("HR", "HR"), "OR": ("OA", "OR"), "SHR": ("SHR", "SHR")}


def t3():
    d = gerekli("06d_modeller.csv")
    fg = oku("06i_fine_gray.csv")
    if fg is not None:
        d = pd.concat([d, fg], ignore_index=True)
    satirlar = []
    for kod, tr, en in DUYARLILIK:
        x = d[(d["analiz_kodu"] == kod) & d["terim"].notna()]  # 06d'de a_fine_gray yalnizca 06i'ye yonlendirir
        if x.empty:
            continue
        r0 = x.iloc[0]
        if kod == "h_jh_surekli":
            r_ = x[x["terim"] == "jh_hlm_en_yuksek"].iloc[0]
            hucre = [etki_ga(r_["etki"], r_["alt_95"], r_["ust_95"]), "–"]
        else:
            hucre = []
            for terim in ["jh_4_5", "jh_6_8"]:
                r_ = x[x["terim"] == terim]
                hucre.append(etki_ga(*r_.iloc[0][["etki", "alt_95", "ust_95"]]) if len(r_) else "–")
        satirlar.append([T(tr, en), lab(OLCU, r0["etki_olcusu"]), tam(r0["n"]), tam(r0["olay"])] + hucre)
    sut = [T("Analiz", "Analysis"), T("Ölçü", "Measure"), "n", T("Olay", "Events"),
           f"JH-HLM 4–5 ({GA})", f"JH-HLM 6–8 ({GA})"]
    # (i) karistiricilari 06c'nin cox.zph'ten sectigi liste; 06d model sutunundan okunur (elle yazilmaz)
    tt = d.loc[d["analiz_kodu"] == "i_tt_log_zaman", "model"].dropna()
    tt = re.search(r"log\(saat\)\):\s*(.*?)\s*;", tt.iloc[0]) if len(tt) else None
    tt = "; ".join(lab(DEGISKEN, k.strip()) for k in tt.group(1).split(",")) if tt else "?"  # etiketlerde virgul var
    apa_tablo("T3_duyarlilik.docx", 3, T("Duyarlılık analizleri", "Sensitivity analyses"), sut, satirlar,
              T("Referans JH-HLM 1–3. (a) ölüm ve canlı taburculuk yarışan olay; (c) olasılık oranı (OA); (d) yalnızca "
                "evresi bilinen yara kaydı olay; (g) atamasız; (h) en yüksek JH-HLM düzeyi sürekli, HR 1 düzey artış için; "
                f"(i) orantılı hazard varsayımını sağlamayan karıştırıcılar (cox.zph p < 0,05: {tt}) için × log(saat) "
                "etkileşimi; (j) strata YB birimi × anchor_year_group. SHR = alt dağılım hazard oranı. ",
                "Reference JH-HLM 1–3. (a) death and discharge alive as competing events; (c) odds ratio (OR); (d) only "
                "records with a known stage counted as events; (g) no imputation; (h) highest JH-HLM level as continuous, "
                f"HR per 1-level increase; (i) × log(hour) interaction for confounders violating proportional hazards "
                f"(cox.zph p < .05: {tt}); (j) stratified by ICU unit × anchor_year_group. "
                "SHR = subdistribution hazard ratio. ")
              + ROBUST_NOT + KISALTMA)


# ---------------------------------------------------------------
# T4 Model performansi (07b, 07c); T5 Braden kesim noktalari (07b)
# ---------------------------------------------------------------
MODELLER = ["L2 lojistik", "Random Forest", "XGBoost", "Braden toplam (lojistik)"]


def metrik(m, tip, model, ad):
    r_ = m[(m["analiz_tipi"] == tip) & (m["model"] == model) & (m["metrik"] == ad)]
    return r_.iloc[0] if len(r_) else None


def t4():
    m = gerekli("07b_metrikler.csv")
    c = oku("07c_auroc_farki.csv")
    satirlar = []
    for tip in ["ic_dogrulama", "donemsel_dogrulama"]:
        r0 = m[m["analiz_tipi"] == tip]
        if r0.empty:
            continue
        satirlar.append(("panel", f"{lab(ANALIZ, tip)}: n = {tam(r0['n'].iloc[0])}, {T('olay', 'events')} = {tam(r0['olay'].iloc[0])}"))
        for mod in MODELLER:
            hucre = [lab(MODEL, mod)]
            for ad, nd in [("auroc", 3), ("auprc", 3), ("brier", 3), ("kalibrasyon_egimi", 2), ("kalibrasyon_kesisimi", 2)]:
                r_ = metrik(m, tip, mod, ad)
                hucre.append(etki_ga(r_["deger"], r_["alt_95"], r_["ust_95"], nd) if r_ is not None else "–")
            satirlar.append(hucre)
    if c is not None:
        satirlar.append(("panel", T("AUROC farkı (DeLong)", "Difference in AUROC (DeLong)")))
        for _, r_ in c.iterrows():
            pd_ = p_bicim(r_["p_delong"])
            satirlar.append([f"{lab(MODEL, r_['model'])} − {lab(MODEL, r_['karsilastirma'])}, "
                             f"{lab(ANALIZ_KISA, r_['analiz_tipi'])}",
                             etki_ga(r_["auroc_farki"], r_["alt_95"], r_["ust_95"], 3),
                             f"p {pd_}" if pd_.startswith("<") else f"p = {pd_}", "", "", ""])
    sut = [T("Model", "Model"), f"AUROC ({GA})", f"AUPRC ({GA})", f"Brier ({GA})", T(f"Kalibrasyon eğimi ({GA})", f"Calibration slope ({GA})"),
           T(f"Kalibrasyon kesişimi ({GA})", f"Calibration intercept ({GA})")]
    apa_tablo("T4_model_performansi.docx", 4,
              T("72–168 saatte yeni basınç yarası tahmini: model performansı", "Prediction of new pressure injury in hours 72–168: model performance"),
              sut, satirlar,
              T("Tahminler 0–72 saat verileriyle. İç doğrulama: hasta düzeyinde 5 katlı iç içe çapraz doğrulama, metrikler "
                "birleştirilmiş kat dışı tahminlerde. Dönemsel doğrulama: anchor_year_group 2008–2016 eğitim, 2017–2022 "
                "test; anchor_year_group takvim yılı değil, kaydırılmış tarihlerin düştüğü dönemdir. GA 1000 yüzdelik "
                "bootstrap; AUROC farkının GA'sı DeLong standart hatasından. Modeller ağırlıksız (dengesizlik düzeltmesi yok). "
                "AUPRC = kesinlik-duyarlılık eğrisi altındaki alan; AUROC = ROC eğrisi altındaki alan.",
                "Predictions use data from hours 0–72. Internal validation: patient-level 5-fold nested cross-validation; "
                "metrics on pooled out-of-fold predictions. Period validation: anchor_year_group 2008–2016 for training and "
                "2017–2022 for testing; anchor_year_group is not a calendar year but the period into which the shifted dates "
                "fall. CIs from 1000 percentile bootstrap replicates; CI of the AUROC difference from the DeLong standard "
                "error. Models are unweighted (no class-imbalance correction). AUPRC = area under the precision-recall curve; "
                "AUROC = area under the ROC curve."), yatay=True)


def t5():
    m = gerekli("07b_metrikler.csv")
    satirlar = []
    for tip in ["ic_dogrulama", "donemsel_dogrulama"]:
        if (m["analiz_tipi"] == tip).sum() == 0:
            continue
        satirlar.append(("panel", lab(ANALIZ, tip)))
        for k in [18, 14, 12]:
            ad = f"Braden <= {k}"
            r_ = {x: metrik(m, tip, ad, x) for x in ["duyarlilik", "ozgulluk", "ppd", "npd"]}
            if r_["duyarlilik"] is None:
                continue
            sonra = r_["duyarlilik"].get("belirleme") == "sonradan_eklenen"
            hucre = [f"Braden ≤ {k}{'ᵃ' if sonra else ''}"]
            hucre += [etki_ga(r_[x]["deger"], r_[x]["alt_95"], r_[x]["ust_95"]) for x in ["duyarlilik", "ozgulluk", "ppd", "npd"]]
            for mod in ["L2 lojistik", "Random Forest", "XGBoost"]:
                o = metrik(m, tip, mod, f"ozgulluk_braden{k}_duyarliliginda")
                hucre.append(etki_ga(o["deger"], o["alt_95"], o["ust_95"]) if o is not None else "–")
            satirlar.append(hucre)
    sut = [T("Kesim noktası", "Cut-off"), T("Duyarlılık", "Sensitivity"), T("Özgüllük", "Specificity"), T("PKD", "PPV"),
           T("NKD", "NPV"), T("Özgüllük, L2\nlojistik", "Specificity,\nL2 logistic"), T("Özgüllük,\nRandom Forest", "Specificity,\nrandom forest"),
           T("Özgüllük,\nXGBoost", "Specificity,\nXGBoost")]
    apa_tablo("T5_braden_kesim.docx", 5,
              T("Braden kesim noktaları ve aynı duyarlılıkta modellerin özgüllüğü", "Braden cut-offs and model specificity at the same sensitivity"),
              sut, satirlar,
              T(f"Değerler oran ({GA}). Braden toplam 0–72 saatteki en düşük; Braden yoksa risk yok sayıldı. Model "
                "özgüllüğü, modelin duyarlılığının ilk kez kesim noktasının duyarlılığına ulaştığı ROC noktasındadır. "
                "ᵃ Sonradan eklenen kesim noktası (≤ 18 önceden belirlenmişti; kohortta hemen herkes ≤ 18 olduğu için ≤ 14 "
                "ve ≤ 12 sonradan eklendi). NKD = negatif kestirim değeri; PKD = pozitif kestirim değeri.",
                f"Values are proportions ({GA}). Braden total is the lowest value in hours 0–72; missing Braden was counted as "
                "not at risk. Model specificity is taken at the ROC point where model sensitivity first reaches the "
                "sensitivity of the cut-off. ᵃ Post hoc cut-off (≤ 18 was prespecified; ≤ 14 and ≤ 12 were added because "
                "almost the whole cohort scored ≤ 18). NPV = negative predictive value; PPV = positive predictive value."),
              yatay=True)


# ---------------------------------------------------------------
# T6 Mobilite kumeleri (08c, 08d2, 08e, 08h)
# ---------------------------------------------------------------
def kume_listesi(yor):
    return sorted(yor["kume"].unique(), key=lambda x: int(x.split("_")[1]))


def t6():
    yor = gerekli("08c_kume_yorunge.csv")
    oz = oku("08d2_kume_sonuc_ozeti.csv")
    cox = oku("08e_kume_cox.csv")
    don = oku("08h_kume_donem_hr.csv")
    kumeler = kume_listesi(yor)
    yatis = {c: float(yor.loc[yor["kume"] == c, "yatis"].iloc[0]) if sayi_mi(yor.loc[yor["kume"] == c, "yatis"].iloc[0]) else np.nan
             for c in kumeler}
    toplam = np.nansum(list(yatis.values()))

    def oz_hucre(c, deg, sut="sayi", yz="yuzde"):
        if oz is None:
            return "–"
        r_ = oz[(oz["grup"] == c) & (oz["degisken"] == deg)]
        return n_yuzde(r_.iloc[0][sut], r_.iloc[0][yz]) if len(r_) else "–"

    satirlar = [("panel", T("A. Tanım, sonuç ve yeni basınç yarası ile ilişki", "A. Definition, outcome and association with new pressure injury"))]
    for c in kumeler:
        y_ = yor[yor["kume"] == c].sort_values("blok_bas_saat", key=lambda s: s.astype(float))
        ilk, son = y_["ortalama_jh_hlm"].iloc[0], y_["ortalama_jh_hlm"].iloc[-1]
        hr = "1 (ref.)"
        if cox is not None and c != "kume_1":
            r_ = cox[cox["terim"] == c]
            hr = etki_ga(*r_.iloc[0][["etki", "alt_95", "ust_95"]]) if len(r_) else "–"
        dh = {}
        for dn in ["72-168 saat", ">168 saat"]:
            r_ = don[(don["kume"] == c) & (don["donem"] == dn)] if don is not None else pd.DataFrame()
            dh[dn] = etki_ga(*r_.iloc[0][["etki", "alt_95", "ust_95"]]) if len(r_) else ("1 (ref.)" if c == "kume_1" else "–")
        r_ = don[(don["kume"] == c) & don["donem"].str.startswith("etkilesim")] if don is not None else pd.DataFrame()
        satirlar.append([f"{c.replace('kume_', T('Küme ', 'Cluster '))}: {kume_adi(y_.iloc[0])}",
                         n_yuzde(yatis[c], 100 * yatis[c] / toplam), f"{ondalik(ilk, 1)} → {ondalik(son, 1)}",
                         oz_hucre(c, "olay_tipi"), oz_hucre(c, "yeni_by_72_168"), hr, dh["72-168 saat"], dh[">168 saat"],
                         p_bicim(r_.iloc[0]["p"]) if len(r_) else "–"])
    if oz is not None and "sayi_yb_suresince" in oz:
        satirlar.append(("panel", T("B. Bakım planı görülme oranı, n (%)", "B. Care plan documentation, n (%)")))
        planlar = [d_ for d_ in ["ncp_impaired_mobility", "ncp_activity_intolerance", "ncp_skin_integrity"]
                   if (oz["degisken"] == d_).any()]
        alt_baslik = [""]
        for d_ in planlar:
            ad_ = lab(DEG, d_).split(": ")[-1]
            alt_baslik += [f"{ad_},\n{T('0–72 saat', 'h 0–72')}", f"{ad_},\n{T('YB süresince', 'ICU stay')}"]
        satirlar.append(alt_baslik + [""] * (9 - len(alt_baslik)))
        for c in kumeler:
            hucre = [f"{c.replace('kume_', T('Küme ', 'Cluster '))}"]
            for d_ in planlar:
                hucre += [oz_hucre(c, d_), oz_hucre(c, d_, "sayi_yb_suresince", "yuzde_yb_suresince")]
            satirlar.append(hucre + [""] * (9 - len(hucre)))
    sut = [T("Küme", "Cluster"), "n (%)", T("JH-HLM, 0–12 → 60–72 saat", "JH-HLM, h 0–12 → 60–72"),
           T("Yeni BY, n (%)", "New PI, n (%)"), T("Yeni BY 72–168 saat, n (%)", "New PI h 72–168, n (%)"),
           f"HR ({GA})", f"HR ({GA}),\n{lab(DONEM, '72-168 saat')}", f"HR ({GA}),\n{lab(DONEM, '>168 saat')}",
           T("Etkileşim p", "Interaction p")]
    sut_b = ""
    apa_tablo("T6_mobilite_kumeleri.docx", 6,
              T("0–72 saat JH-HLM yörüngesine göre mobilite kümeleri (keşfedici)", "Mobility clusters by JH-HLM trajectory in hours 0–72 (exploratory)"),
              sut, satirlar,
              T("Gaussian Mixture, altı 12 saatlik blokta en yüksek JH-HLM. JH-HLM sütunu ilk ve son bloğun ortalamasıdır. "
                "Yeni BY 72. saat ile 28. gün arası, YB süresince. HR birincil Cox modeliyle aynı karıştırıcılar ve strata, "
                "MICE; referans küme 1. Dönem HR'leri takip 168. saatte bölünerek; etkileşim > 168 saat HR / 72–168 saat HR. "
                "Bakım planı 0–72 saat ve YB süresince (giriş–çıkış) ayrı pencerelerde. ",
                "Gaussian mixture on the highest JH-HLM level in six 12-hour blocks. The JH-HLM column gives the mean of the "
                "first and last block. New PI from hour 72 to day 28 during the ICU stay. HRs adjusted for the same "
                "confounders and strata as the primary Cox model, multiple imputation; reference cluster 1. Period HRs from "
                "follow-up split at hour 168; interaction = HR > 168 h / HR 72–168 h. Care plans in hours 0–72 and during "
                "the ICU stay (admission to discharge). ") + sut_b + ROBUST_NOT + KISALTMA + " " + GIZLI_NOT, yatay=True)


# ---------------------------------------------------------------
# Ek tablolar
# ---------------------------------------------------------------
def e1():
    o = gerekli("05a_degisken_ozeti.csv")
    o = o[~o["tip"].isin(["aralik_disi_eksik"])].drop_duplicates("degisken")
    mice = oku("06d2_atama_eksik_oranlari.csv")
    atanan = set(mice.loc[mice["eksik_orani"].notna(), "degisken"]) if mice is not None else set()
    satirlar = []
    for _, r_ in o.iterrows():
        if r_["degisken"] in ("stay_id",) or r_["degisken"].startswith(("sure_saat", "olay_tipi", "yeni_by_72_168")):
            continue
        eksik = 100 - float(r_["doluluk_yuzde"]) if sayi_mi(r_["doluluk_yuzde"]) else np.nan
        satirlar.append([lab(DEG, r_["degisken"]) if r_["degisken"] in DEG else r_["degisken"], tam(r_["bos"]),
                         ondalik(eksik, 1), T("evet", "yes") if r_["degisken"] in atanan else T("hayır", "no")])
    not_ = T("Eksik = 0–72 saat penceresinde kaydı olmayan yatış. MICE: birincil modelde atanan değişkenler (m = 20). ",
             "Missing = stays without a record in hours 0–72. MICE: variables imputed for the primary model (m = 20). ")
    if mice is not None:
        b = mice[mice["olcu"].notna()].set_index("olcu")["deger"]
        if len(b):
            not_ += T(f"Atanan BKİ aralığı {ondalik(b.get('min'), 1)}–{ondalik(b.get('max'), 1)} (medyan {ondalik(b.get('medyan'), 1)}). ",
                      f"Imputed BMI range {ondalik(b.get('min'), 1)}–{ondalik(b.get('max'), 1)} (median {ondalik(b.get('medyan'), 1)}). ")
    apa_tablo("E1_eksik_veri.docx", "E1", T("Eksik veri", "Missing data"),
              [T("Değişken", "Variable"), T("Eksik, n", "Missing, n"), T("Eksik, %", "Missing, %"), T("MICE ile atandı", "Imputed (MICE)")],
              satirlar, not_ + GIZLI_NOT)


def e2():
    z = gerekli("06e2_ph_varsayimi_coxzph.csv")
    satirlar = [[lab(JH, r_["terim"]) if r_["terim"] in JH else ("GLOBAL" if r_["terim"] == "GLOBAL" else
                 lab(DEG, r_["terim"]) if r_["terim"] in DEG else r_["terim"]),
                 ondalik(r_["chisq_ilk_atama"]), tam(r_["df"]), p_bicim(r_["p_ilk_atama"]), p_bicim(r_["p_birlesik_d2"])]
                for _, r_ in z.iterrows()]
    apa_tablo("E2_schoenfeld.docx", "E2", T("Orantılı hazard varsayımı (Schoenfeld artıkları, cox.zph)",
                                            "Proportional hazards assumption (Schoenfeld residuals, cox.zph)"),
              [T("Terim", "Term"), "χ²", T("sd", "df"), T("p, ilk atama", "p, first imputation"), T("p, D2 birleşik", "p, pooled (D2)")],
              satirlar, T("Birincil cause-specific Cox modeli, strata YB birimi × anchor_year_group, rank zaman dönüşümü. "
                          "D2: 20 atamanın ki-kare istatistiklerinin birleştirilmesi (Li, Meng ve Raghunathan, 1991).",
                          "Primary cause-specific Cox model stratified by ICU unit × anchor_year_group, rank time transform. "
                          "D2: pooled chi-square statistics across 20 imputations (Li, Meng and Raghunathan, 1991)."))


ALT_DEG = {"cinsiyet": ("Cinsiyet", "Sex"), "yas_grubu": ("Yaş grubu", "Age group"), "ilk_yb_birimi": ("YB birimi", "ICU unit")}


def e3():
    g = gerekli("07d_alt_gruplar.csv")
    satirlar = []
    for tip in ["ic_dogrulama", "donemsel_dogrulama"]:
        x = g[g["analiz_tipi"] == tip]
        if x.empty:
            continue
        satirlar.append(("panel", lab(ANALIZ, tip)))
        for (deg, ag), y_ in x.groupby(["alt_grup_degiskeni", "alt_grup"], sort=False):
            r0 = y_.iloc[0]
            hucre = [f"{lab(ALT_DEG, deg)}: {lab(KATEGORI, ag)}", tam(r0["n"]), tam(r0["olay"])]
            for mod in MODELLER:
                r_ = y_[y_["model"] == mod]
                hucre.append(etki_ga(*r_.iloc[0][["auroc", "alt_95", "ust_95"]], nd=3) if len(r_) else "–")
            satirlar.append(hucre)
    apa_tablo("E3_alt_gruplar.docx", "E3", T("Alt gruplarda AUROC", "AUROC in subgroups"),
              [T("Alt grup", "Subgroup"), "n", T("Olay", "Events")] + [lab(MODEL, m_) for m_ in MODELLER], satirlar,
              T(f"AUROC ({GA}); olay ve olaysız sayısı 5'ten az olan alt grupta hesaplanmadı. ",
                f"AUROC ({GA}); not computed when events or non-events were fewer than 5. ") + GIZLI_NOT, yatay=True)


def e4():
    k3 = gerekli("08g_k3_duyarlilik.csv")
    y_ = k3[k3["bolum"] == "yorunge"]
    c_ = k3[k3["bolum"] == "cox_hr"]
    satirlar = []
    arastirmaci = True  # tum adlar config/kume_adlari.csv'den mi
    for c in kume_listesi(y_):
        yy = y_[y_["kume"] == c].sort_values("blok_bas_saat", key=lambda s: s.astype(float))
        arastirmaci = arastirmaci and config_adi(yy.iloc[0]) is not None
        r_ = c_[c_["kume"] == c]
        satirlar.append([f"{c.replace('kume_', T('Küme ', 'Cluster '))}: {kume_adi(yy.iloc[0])}", tam(yy["yatis"].iloc[0]),
                         f"{ondalik(yy['ortalama_jh_hlm'].iloc[0], 1)} → {ondalik(yy['ortalama_jh_hlm'].iloc[-1], 1)}",
                         tam(r_.iloc[0]["kume_olay"]) if len(r_) else "–",
                         "1 (ref.)" if c == "kume_1" else (etki_ga(*r_.iloc[0][["etki", "alt_95", "ust_95"]]) if len(r_) else "–")])
    apa_tablo("E4_k3_duyarlilik.docx", "E4", T("Duyarlılık: üç kümeli çözüm", "Sensitivity: three-cluster solution"),
              [T("Küme", "Cluster"), "n", T("JH-HLM, 0–12 → 60–72 saat", "JH-HLM, h 0–12 → 60–72"), T("Yeni BY, n", "New PI, n"), f"HR ({GA})"],
              satirlar, (T("Küme adları, ortalama JH-HLM profillerine bakılarak araştırmacılar tarafından verilmiştir. ",
                           "Cluster labels were assigned by the investigators after inspection of mean JH-HLM profiles. ")
                         if arastirmaci else
                         T("Ad, kurala dayalı öneridir (onaylanmadı). ", "Names are rule-based suggestions (not approved). "))
              + T("Ana çözümle birlikte okunduğunda birkaç yatışı ayıran kümelerde olay sayısı ve yörünge yazılmaz. ",
                  "Event counts and trajectories are not shown for clusters that would isolate a few stays when read "
                  "together with the main solution. ") + KISALTMA + " " + GIZLI_NOT)


def e5():
    it = pd.read_csv("config/itemids_onayli.csv", dtype=object)
    it = it.sort_values(["degisken_grubu", "onay", "itemid"], ascending=[True, False, True])
    satirlar = [[r_["degisken_grubu"], r_["itemid"], r_["label"],
                 T("onaylandı", "approved") if str(r_["onay"]).strip() in ("1", "1.0") else T("reddedildi", "rejected"),
                 r_["gerekce"] if isinstance(r_["gerekce"], str) else ""] for _, r_ in it.iterrows()]
    apa_tablo("E5_itemid_listesi.docx", "E5", T("Kullanılan MIMIC-IV kayıt numaraları (itemid)", "MIMIC-IV item identifiers (itemid)"),
              [T("Değişken grubu", "Variable group"), "itemid", T("Etiket (d_items)", "Label (d_items)"), T("Karar", "Decision"),
               T("Gerekçe", "Rationale")], satirlar,
              T("Aday itemid'ler d_items üzerinde metin aramasıyla bulundu ve elle onaylandı. Kayıt sayıları tabloya alınmadı.",
                "Candidate itemids were found by text search in d_items and reviewed manually. Record counts are not shown. "
                "Rationales are in Turkish."), yatay=True)


def e6():
    """Kumelenmemis (naif) ve hasta duzeyinde kumelenmis (robust) GA yan yana: maruziyet / kume terimleri."""
    satir, kayit = [], []

    def ekle(baslik, df, etiket):
        if df is None or "alt_95_naif" not in df:
            return
        satir.append(("panel", baslik))
        for _, r_ in df.iterrows():
            et = etiket(r_)
            satir.append([et, ondalik(r_["etki"]), f"{ondalik(r_['alt_95_naif'])}–{ondalik(r_['ust_95_naif'])}",
                          f"{ondalik(r_['alt_95'])}–{ondalik(r_['ust_95'])}", p_bicim(r_.get("p_naif")), p_bicim(r_["p"])])
            kayit.append({"bolum": baslik, "terim": et, **{k: r_.get(k) for k in
                          ["etki", "alt_95_naif", "ust_95_naif", "alt_95", "ust_95", "p_naif", "p", "se_naif", "se"]}})

    d = oku("06d_modeller.csv")
    fg = oku("06i_fine_gray.csv")
    if d is not None:
        d = pd.concat([d, fg], ignore_index=True) if fg is not None else d
        d = d[d["maruziyet"].astype(str).isin(["True", "TRUE"]) & d["alt_95_naif"].notna()]
        sira = {k: i for i, (k, *_r) in enumerate(DUYARLILIK)}
        d = d.assign(_s=d["analiz_kodu"].map(sira)).sort_values(["_s", "terim"])
        adlar = {k: T(tr, en) for k, tr, en in DUYARLILIK}
        ekle(T("Birincil ve duyarlılık analizleri", "Primary and sensitivity analyses"), d,
             lambda r_: f"{adlar.get(r_['analiz_kodu'], r_['analiz_kodu'])}: "
                        f"{lab(JH, r_['terim']) if r_['terim'] in JH else T('JH-HLM, 1 düzey', 'JH-HLM, per level')}")
    j = oku("06j_donem_hr.csv")
    if j is not None:
        ekle(T("Dönem bazında HR (06j)", "Period-specific HR"), j,
             lambda r_: f"{lab(JH, r_['terim'])}, " + (lab(DONEM, r_["donem"]) if r_["donem"] in DONEM
                                                      else T("etkileşim", "interaction")))
    yor = oku("08c_kume_yorunge.csv")
    adlar_k = {c: kume_adi(g.iloc[0]) for c, g in yor.groupby("kume")} if yor is not None else {}
    e = oku("08e_kume_cox.csv")
    if e is not None:
        ekle(T("Mobilite kümeleri", "Mobility clusters"), e[e["kume_terimi"].astype(str).isin(["True"]) & e["se"].notna()],
             lambda r_: f"{r_['terim'].replace('kume_', T('Küme ', 'Cluster '))}: {adlar_k.get(r_['terim'], '')}")
    h = oku("08h_kume_donem_hr.csv")
    if h is not None:
        ekle(T("Mobilite kümeleri, dönem bazında", "Mobility clusters by period"), h,
             lambda r_: f"{r_['kume'].replace('kume_', T('Küme ', 'Cluster '))}, " +
                        (lab(DONEM, r_["donem"]) if r_["donem"] in DONEM else T("etkileşim", "interaction")))
    if not kayit:
        raise ValueError("naif GA sutunu olan girdi yok (06/08 eski surum)")
    pd.DataFrame(kayit).to_csv(hedef / "E6_robust_karsilastirma.csv", index=False, encoding="utf-8-sig")
    apa_tablo("E6_robust_karsilastirma.docx", "E6",
              T("Kümelenmemiş ve hasta düzeyinde kümelenmiş standart hatalarla güven aralıkları",
                "Confidence intervals with non-clustered and patient-clustered standard errors"),
              [T("Analiz / terim", "Analysis / term"), T("HR / OA", "HR / OR"), T(f"{GA}, kümelenmemiş", f"{GA}, non-clustered"),
               T(f"{GA}, robust (hasta kümesi)", f"{GA}, robust (patient cluster)"), T("p, kümelenmemiş", "p, non-clustered"),
               T("p, robust", "p, robust")], satir,
              T("Nokta tahminleri iki yöntemde aynıdır; yalnızca standart hata değişir. Robust: Lin-Wei sandwich, "
                "subject_id kümesi (R: coxph cluster(subject_id); Python: lifelines cluster_col). MICE, Rubin kuralları. "
                "Ana tablolarda robust GA kullanılır. (c) lojistik regresyonda etki ölçüsü olasılık oranıdır (OA; "
                "statsmodels cov_type = \"cluster\"). ",
                "Point estimates are identical; only the standard error differs. Robust: Lin-Wei sandwich clustered on "
                "subject_id (R: coxph cluster(subject_id); Python: lifelines cluster_col). Multiple imputation, Rubin's "
                "rules. Main tables use robust CIs. In analysis (c), logistic regression, the measure is the odds ratio "
                "(OR; statsmodels cov_type = \"cluster\"). ") + KISALTMA,
              yatay=True)


# ---------------------------------------------------------------
# Sekiller
# ---------------------------------------------------------------
AKIS = {  # 04a adimi -> (dahil kutusu, dislanma gerekcesi) tr / en
    "Tum YB yatislari": (("Tüm YB yatışları", None), ("All ICU stays", None)),
    "Yas >= 18": (("≥ 18 yaş", "< 18 yaş"), ("Age ≥ 18 years", "Age < 18 years")),
    "YB'de >= 72 saat": (("YB'de ≥ 72 saat", "YB'de < 72 saat"), ("ICU stay ≥ 72 h", "ICU stay < 72 h")),
    "0-72. saatte >= 1 gecerli JH-HLM": (("0–72. saatte ≥ 1 geçerli JH-HLM", "0–72. saatte geçerli JH-HLM yok"),
                                         ("≥ 1 valid JH-HLM in hours 0–72", "No valid JH-HLM in hours 0–72")),
    "Kabulde basinc yarasi isareti yok": (("Kabulde BY işareti yok", "Kabulde BY işareti var"),
                                          ("No PI flag at admission", "PI flag at admission")),
    "0-72. saatte basinc yarasi kaydi yok": (("0–72. saatte BY kaydı yok", "0–72. saatte BY kaydı var"),
                                             ("No PI record in hours 0–72", "PI record in hours 0–72")),
    "Tespit tarihi 72. saatten once olan yara yok": (("Tespit tarihi 72. saatten önce olan yara yok", "Tespit tarihi 72. saatten önce olan yara"),
                                                     ("No PI detected before hour 72", "PI detected before hour 72")),
}


def s1():
    k = gerekli("04a_kohort_akisi.csv")
    adimlar = []
    for i, r_ in k.iterrows():
        ad = AKIS.get(r_["adim"])
        dahil, neden = (ad[0] if DIL == "tr" else ad[1]) if ad else (r_["adim"], T(f"Dışlanan: {r_['adim']}", f"Excluded: {r_['adim']}"))
        if i > 0 and str(r_["dislanan"]) in ("0", "0.0"):
            continue  # dislanan olmayan adim kutu olarak cizilmez (notta)
        adimlar.append((dahil, neden, r_["yatis"], r_["hasta"], r_["dislanan"]))
    n = len(adimlar)
    fig, ax = plt.subplots(figsize=(7.5, 1.25 * n + 0.5))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.6, n - 0.4)
    kutu = dict(boxstyle="round,pad=0.4", fc="white", ec="black", lw=0.8)
    for i, (dahil, neden, yatis, hasta, disl) in enumerate(adimlar):
        y_ = n - 1 - i
        son = i == n - 1
        metin = (T("Analiz kohortu\n", "Analysis cohort\n") if son else "") + f"{dahil}\n" + \
            T(f"{tam(yatis)} yatış ({tam(hasta)} hasta)", f"{tam(yatis)} stays ({tam(hasta)} patients)")
        ax.text(0.32, y_, metin, ha="center", va="center", fontsize=8, bbox={**kutu, "lw": 1.4 if son else 0.8})
        if i > 0:
            ax.annotate("", xy=(0.32, y_ + 0.28), xytext=(0.32, y_ + 0.72), arrowprops=dict(arrowstyle="->", lw=0.8))
            ax.annotate("", xy=(0.62, y_ + 0.5), xytext=(0.32, y_ + 0.5), arrowprops=dict(arrowstyle="->", lw=0.8))
            ax.text(0.64, y_ + 0.5, T(f"Dışlanan: {tam(disl)} yatış\n{neden}", f"Excluded: {tam(disl)} stays\n{neden}"),
                    ha="left", va="center", fontsize=7.5, bbox=kutu)
    sekil_kaydet(fig, "S1_kohort_akisi")


def s2():
    c = gerekli("06c_kumulatif_insidans.csv")
    fig, (ax, ax_r) = plt.subplots(2, 1, figsize=(6, 4.8), gridspec_kw={"height_ratios": [4, 1]}, sharex=True)
    gruplar = list(dict.fromkeys(c["grup"]))
    for g in gruplar:
        x = c[c["grup"] == g]
        gun = np.concatenate([[0], x["gun_72s_sonrasi"].astype(float)])
        ki = np.concatenate([[0], pd.to_numeric(x["kumulatif_insidans"], errors="coerce")]) * 100
        lo = np.concatenate([[0], pd.to_numeric(x["alt_95"], errors="coerce")]) * 100
        hi = np.concatenate([[0], pd.to_numeric(x["ust_95"], errors="coerce")]) * 100
        cz, = ax.plot(gun, ki, "o-", ms=3, label=f"JH-HLM {g.replace('-', '–')}")
        ax.fill_between(gun, lo, hi, color=cz.get_color(), alpha=0.15, lw=0)
    ax.set_ylabel(T("Kümülatif insidans (%)", "Cumulative incidence (%)"))
    ax.set_ylim(bottom=0)  # insidans negatif olamaz (tum degerler gizliyse eksen kaymasin)
    ax.legend(frameon=False)
    eksen_bicim(ax.yaxis)
    gunler = sorted(c["gun_72s_sonrasi"].astype(float).unique())
    ax_r.axis("off")
    ax_r.text(-0.5, len(gruplar), T("Risk altında", "At risk"), fontsize=7, fontweight="bold", va="center", ha="right")
    for i, g in enumerate(gruplar):
        x = c[c["grup"] == g]
        ax_r.text(-0.5, len(gruplar) - 1 - i, f"JH-HLM {g.replace('-', '–')}", fontsize=7, va="center", ha="right")
        for gun, r_ in zip(x["gun_72s_sonrasi"].astype(float), x["risk_altinda"]):
            ax_r.text(gun, len(gruplar) - 1 - i, tam(r_), fontsize=7, va="center", ha="center")
    ax_r.set_ylim(-0.5, len(gruplar) + 0.5)
    ax.set_xticks(gunler)
    ax.set_xlim(-0.5, max(gunler) + 0.5)
    ax.set_xlabel(T("72. saatten sonraki gün (25. gün = YB girişinden sonraki 28. gün)",
                    "Days after hour 72 (day 25 = day 28 after ICU admission)"))
    ax.xaxis.set_tick_params(labelbottom=True)
    fig.tight_layout()
    sekil_kaydet(fig, "S2_kumulatif_insidans")


def s3():
    j = oku("06j_donem_hr.csv")
    h = oku("08h_kume_donem_hr.csv")
    if j is None and h is None:
        raise FileNotFoundError("06j_donem_hr.csv ve 08h_kume_donem_hr.csv yok")
    satir = []  # (etiket, hr, lo, hi, baslik_mi)
    if j is not None:
        satir.append((T("JH-HLM grubu (ref. 1–3)", "JH-HLM group (ref. 1–3)"), None, None, None, True))
        for terim in ["jh_4_5", "jh_6_8"]:
            for dn in ["72-168 saat", ">168 saat"]:
                r_ = j[(j["terim"] == terim) & (j["donem"] == dn)]
                if len(r_):
                    satir.append((f"{lab(JH, terim)}, {lab(DONEM, dn)}", *r_.iloc[0][["etki", "alt_95", "ust_95"]].astype(float), False))
    if h is not None:
        yor = oku("08c_kume_yorunge.csv")  # ad onerisi 08h'de yok; onayli ad yoksa buradan
        adlar = {c: kume_adi(g.iloc[0]) for c, g in yor.groupby("kume")} if yor is not None else {}
        satir.append((T("Mobilite kümesi (ref. küme 1)", "Mobility cluster (ref. cluster 1)"), None, None, None, True))
        for c in sorted(h["kume"].unique(), key=lambda x: int(x.split("_")[1])):
            for dn in ["72-168 saat", ">168 saat"]:
                r_ = h[(h["kume"] == c) & (h["donem"] == dn)]
                if len(r_):
                    ad = f"{c.replace('kume_', T('Küme ', 'Cluster '))}: {adlar.get(c, kume_adi(r_.iloc[0]))}"
                    satir.append((f"{ad}, {lab(DONEM, dn)}", *r_.iloc[0][["etki", "alt_95", "ust_95"]].astype(float), False))
    n = len(satir)
    fig, ax = plt.subplots(figsize=(7.5, 0.32 * n + 0.8))
    for i, (et, hr, lo, hi, bas) in enumerate(satir):
        y_ = n - 1 - i
        if bas:  # baslik satiri: y ekseni etiketi kalin
            continue
        if np.isfinite(hr):
            ax.plot([lo, hi], [y_, y_], color="black", lw=0.9)
            ax.plot(hr, y_, "s", color="black", ms=4)
            ax.text(1.02, y_, etki_ga(hr, lo, hi), transform=ax.get_yaxis_transform(), va="center", fontsize=7.5)
    ax.axvline(1, color="grey", ls="--", lw=0.8)
    ax.set_xscale("log")
    ax.set_yticks(range(n))
    ax.set_yticklabels([s_[0] for s_ in satir][::-1], fontsize=8)
    for t_, s_ in zip(ax.get_yticklabels(), satir[::-1]):
        if s_[4]:
            t_.set_fontweight("bold")
    ax.set_ylim(-0.7, n - 0.3)
    ax.xaxis.set_major_locator(matplotlib.ticker.FixedLocator([0.125, 0.25, 0.5, 1, 2, 4, 8]))
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: ondalik(v, 2 if v < 1 else 0)))
    ax.set_xlabel(f"HR ({GA}, {T('log ölçek', 'log scale')})")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    sekil_kaydet(fig, "S3_donem_hr_orman")


def s4():
    e = gerekli("07h_egri_noktalari.csv")
    m = oku("07b_metrikler.csv")
    e = e[e["analiz_tipi"] == "donemsel_dogrulama"]
    if e.empty:
        raise ValueError("donemsel dogrulama egrisi yok")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.6))
    for mod in MODELLER:
        x = e[(e["egri"] == "roc") & (e["model"] == mod)]
        au = metrik(m, "donemsel_dogrulama", mod, "auroc") if m is not None else None
        a1.plot(x["x"].astype(float), x["y"].astype(float),
                label=f"{lab(MODEL, mod)}" + (f" (AUROC {ondalik(au['deger'], 3)})" if au is not None else ""))
    isaret = {"Braden <= 18": "ks", "Braden <= 14": "kD", "Braden <= 12": "k^"}
    for _, r_ in e[e["egri"] == "roc_kesim"].iterrows():
        a1.plot(float(r_["x"]), float(r_["y"]), isaret.get(r_["model"], "ko"), ms=5,
                label=r_["model"].replace("<=", "≤") + ("ᵃ" if r_.get("belirleme") == "sonradan_eklenen" else ""))
    a1.plot([0, 1], [0, 1], ":", color="grey")
    a1.set(xlabel=T("1 − özgüllük", "1 − specificity"), ylabel=T("Duyarlılık", "Sensitivity"), title="A. ROC")
    a1.legend(fontsize=7, frameon=False, loc="lower right")
    ust = 0
    for mod in MODELLER:
        x = e[(e["egri"] == "kalibrasyon") & (e["model"] == mod)].copy()
        x = x[pd.to_numeric(x["y"], errors="coerce").notna()]
        a2.plot(x["x"].astype(float), x["y"].astype(float), "o-", ms=3, label=lab(MODEL, mod))
        ust = max(ust, x["x"].astype(float).max(), x["y"].astype(float).max())
    a2.plot([0, ust], [0, ust], ":", color="grey")
    a2.set(xlabel=T("Ortalama tahmin (ondalık dilim)", "Mean predicted risk (decile)"), ylabel=T("Gözlenen oran", "Observed proportion"),
           title=T("B. Kalibrasyon", "B. Calibration"))
    a2.legend(fontsize=7, frameon=False)
    for ax in (a1, a2):
        eksen_bicim(ax.xaxis)
        eksen_bicim(ax.yaxis)
    fig.tight_layout()
    sekil_kaydet(fig, "S4_roc_kalibrasyon")


def s5():
    e = gerekli("07h_egri_noktalari.csv")
    e = e[(e["analiz_tipi"] == "donemsel_dogrulama") & (e["egri"] == "karar")]
    if e.empty:
        raise ValueError("donemsel karar egrisi yok")
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    stil = {"Braden <= 18": "k--", "Braden <= 12": "k-.", "herkese": None}
    ymax = 0
    for mod in MODELLER + ["Braden <= 18", "Braden <= 12", "herkese"]:
        x = e[e["model"] == mod]
        if x.empty:
            continue
        et = {"herkese": T("Herkese", "Treat all")}.get(mod, lab(MODEL, mod).replace("<=", "≤"))
        if mod == "Braden <= 12":
            et += "ᵃ"
        if mod == "herkese":
            ax.plot(x["x"].astype(float), x["y"].astype(float), color="grey", label=et)
        else:
            ax.plot(x["x"].astype(float), x["y"].astype(float), *([stil[mod]] if mod in stil else []), label=et)
        ymax = max(ymax, x["y"].astype(float).max())
    ax.axhline(0, color="black", lw=0.8, label=T("Hiç kimseye", "Treat none"))
    ax.set(xlabel=T("Eşik olasılık", "Threshold probability"), ylabel=T("Net fayda", "Net benefit"), ylim=(-0.01, ymax * 1.1))
    eksen_bicim(ax.xaxis)
    eksen_bicim(ax.yaxis)
    ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    sekil_kaydet(fig, "S5_karar_egrisi")


def s6():
    s = gerekli("07f_shap_ozet.csv")
    s = s.assign(sira=s["sira"].astype(int)).sort_values("sira").head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.barh([ozellik_adi(o) for o in s["ozellik"]], s["ortalama_abs_shap"].astype(float), color="#4C72B0")
    ax.set_xlabel(T("Ortalama |SHAP| (log-odds)", "Mean |SHAP| (log-odds)"))
    ax.set_title(f"{s['model'].iloc[0]}, {T('dönemsel test seti', 'period test set')}", fontsize=9)
    eksen_bicim(ax.xaxis)
    fig.tight_layout()
    sekil_kaydet(fig, "S6_shap")


def s7():
    yor = gerekli("08c_kume_yorunge.csv")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for c in kume_listesi(yor):
        g = yor[yor["kume"] == c].sort_values("blok_bas_saat", key=lambda s: s.astype(float))
        ort = pd.to_numeric(g["ortalama_jh_hlm"], errors="coerce")
        if ort.isna().all():
            continue
        x = g["blok_bas_saat"].astype(float) + 6
        cz, = ax.plot(x, ort, "o-", ms=3, label=f"{c.replace('kume_', T('Küme ', 'Cluster '))}: {kume_adi(g.iloc[0])} (n = {tam(g['yatis'].iloc[0])})")
        ax.fill_between(x, pd.to_numeric(g["alt_95"], errors="coerce"), pd.to_numeric(g["ust_95"], errors="coerce"),
                        color=cz.get_color(), alpha=0.2, lw=0)
    ax.set(xlabel=T("YB girişinden sonraki saat (12 saatlik blok)", "Hours after ICU admission (12-hour blocks)"),
           ylabel=T(f"JH-HLM (ortalama, {GA})", f"JH-HLM (mean, {GA})"), xticks=range(0, 73, 12), ylim=(1, 8),
           yticks=range(1, 9))
    ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    sekil_kaydet(fig, "S7_kume_yorungeleri")


print(f"Kaynak: {kaynak}  Hedef: {hedef}  Dil: {DIL}")
for ad, f in [("ETIKET", etiket_kontrol), ("T1", t1), ("T2", t2), ("T3", t3), ("T4", t4), ("T5", t5), ("T6", t6), ("E1", e1), ("E2", e2), ("E3", e3),
              ("E4", e4), ("E5", e5), ("E6", e6), ("S1", s1), ("S2", s2), ("S3", s3), ("S4", s4), ("S5", s5), ("S6", s6), ("S7", s7)]:
    calistir(ad, f)
pd.DataFrame(atlanan, columns=["cikti", "neden"]).to_csv(hedef / "09z_atlananlar.csv", index=False, encoding="utf-8-sig")
if etiketsiz:
    print(f"  UYARI: etiketsiz ozellik(ler) ham adla yazildi: {', '.join(sorted(etiketsiz))}")
print(f"\n{len(atlanan)} cikti atlandi (09z_atlananlar.csv). Ciktilar: {hedef}")
