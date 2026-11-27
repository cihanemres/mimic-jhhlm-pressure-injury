"""Adim 9b: Makale 2 ek tablolari (.docx, APA 7), Turkce veya Ingilizce.

Girdi YALNIZCA <cikti>/paylasilabilir/ (10a, 10b, 10c, 10c2, 10f, 10g, 07b, 07c_charlsonlu). Gizlenmis hucreler
("<5", "gizli") aynen yazilir. Bicim 09 ile ayni (sayi bicimi ve APA tablo fonksiyonlari 09'dan kopyalandi; 09 betik
olarak calisirken hedef klasorunu temizledigi icin ice aktarilamiyor; birinde degisirse digerinde de degismeli).
Makale 2'de E1 (alt gruplar) ve E2 (itemid) 09'un E3 ve E5 tablolaridir; bu betik E3-E6'yi uretir.

Cikti: <cikti>/makale2_<dil>/
    E3_degisken_zamani.docx    modele giren degiskenlerin olcum penceresi ve ozeti (10g); Charlson "yalnizca tanimlayici"
    E4_model_ayarlari.docx     secilen hiperparametreler, ozellik sayisi, kodlama (10f; donemsel egitim modelleri)
    E5_pencere_bilesimi.docx   72-168 saat penceresinde yatislarin durumu (10a)
    E6_duyarlilik.docx         birincil | olumler cikarilmis (10b) | SOFA bilesenleri (10c) | Charlson eklenmis (07)
    09bz_atlananlar.csv

Kullanim:
    python code/09b_makale2_ek.py --cikti outputs_tam --dil tr
    python code/09b_makale2_ek.py --cikti outputs_tam --dil en
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from etiketler import ozellik_etiketi  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.section import WD_ORIENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt  # noqa: E402

p = argparse.ArgumentParser(description="Makale 2 ek tablolari")
p.add_argument("--cikti", default="outputs", help="Ciktilar klasoru (paylasilabilir/ buradan okunur)")
p.add_argument("--dil", choices=["tr", "en"], default="tr")
a = p.parse_args()
DIL = a.dil
kaynak = Path(a.cikti) / "paylasilabilir"
hedef = Path(a.cikti) / f"makale2_{DIL}"
hedef.mkdir(parents=True, exist_ok=True)
for eski in hedef.glob("*"):
    eski.unlink()
atlanan = []
GIZLI = {"<5", "gizli"}


def oku(ad):
    yol = kaynak / ad
    return pd.read_csv(yol, dtype=object, encoding="utf-8-sig") if yol.exists() else None


def gerekli(ad):
    df = oku(ad)
    if df is None:
        raise FileNotFoundError(f"{ad} yok")
    return df


def T(tr, en):
    return tr if DIL == "tr" else en


# ---- Sayi bicimi (09 ile ayni) ----
def sayi_mi(x):
    try:
        return np.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def gizli_yaz(x):
    x = x.strip()
    return "suppressed" if (x == "gizli" and DIL == "en") else x


def ondalik(x, nd=2):
    if isinstance(x, str) and x.strip() in GIZLI:
        return gizli_yaz(x)
    if not sayi_mi(x):
        return "–"
    x = round(float(x), nd) + 0.0
    s = f"{abs(x):,.{nd}f}"
    s = s.translate(str.maketrans({",": ".", ".": ","})) if DIL == "tr" else s
    return ("−" if x < 0 else "") + s


def tam(x):
    if isinstance(x, str) and x.strip() in GIZLI:
        return gizli_yaz(x)
    return ondalik(round(float(x)), 0) if sayi_mi(x) else "–"


def p_bicim(x):
    if not sayi_mi(x):
        return "–"
    x = float(x)
    if x < 0.001:
        return T("< 0,001", "< .001")
    s = ondalik(x, 3)
    return s if DIL == "tr" else s.lstrip("0")


def p_hucre(x):
    s = p_bicim(x)
    return s if s == "–" else (f"p {s}" if s.startswith("<") else f"p = {s}")


def etki_ga(e, lo, hi, nd=3):
    """Null degeri olmayan metrik (AUROC, AUROC farki): 09'daki etki_ga(..., oran=False)."""
    if not sayi_mi(e):
        return "–"
    if not (sayi_mi(lo) and sayi_mi(hi)):
        return ondalik(e, nd)
    return f"{ondalik(e, nd)} ({ondalik(lo, nd)}–{ondalik(hi, nd)})"


def fark_ga(e, lo, hi):
    """AUROC farki: bir GA siniri 3 ondalikta 0,000 gorunuyorsa (GA 0'i iceriyor mu okunamaz) 4 ondalik."""
    nd = 4 if any(sayi_mi(v) and round(float(v), 3) == 0 for v in (lo, hi)) else 3
    return etki_ga(e, lo, hi, nd)


def n_yuzde(n, yuzde):
    if isinstance(n, str) and n.strip() in GIZLI:
        return gizli_yaz(n)
    if not sayi_mi(n):
        return "–"
    return f"{tam(n)} ({ondalik(yuzde, 1)})" if sayi_mi(yuzde) else tam(n)


GA = T("%95 GA", "95% CI")
GIZLI_NOT = T('"<5": 1–4 arası sayı; "gizli": küçük bir hücreyi geri hesaplatmasın diye gizlenen sayı (PhysioNet '
              'veri kullanım sözleşmesi).',
              '"<5": count between 1 and 4; "suppressed": count withheld so that a small cell cannot be '
              'back-calculated (PhysioNet data use agreement).')
MODEL = {"L2 lojistik": ("L2 lojistik regresyon", "L2 logistic regression"), "Random Forest": ("Rastgele orman", "Random forest"),
         "XGBoost": ("XGBoost", "XGBoost"), "Braden toplam (lojistik)": ("Braden toplam (lojistik)", "Braden total (logistic)")}
ANALIZ = {"ic_dogrulama": ("İç doğrulama (iç içe çapraz doğrulama)", "Internal validation (nested cross-validation)"),
          "donemsel_dogrulama": ("Dönemsel doğrulama (referans yıl grubu)", "Period validation (anchor_year_group)")}
MODELLER = ["L2 lojistik", "Random Forest", "XGBoost"]


def lab(sozluk, k):
    v = sozluk.get(k)
    return (v[0] if DIL == "tr" else v[1]) if v else str(k)


# ---- APA 7 tablo (09 ile ayni) ----
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


def apa_tablo(dosya, no, baslik, sutunlar, satirlar, not_, yatay=False):
    """satirlar: liste; her satir ya hucre listesi ya da ("panel", metin)."""
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
    doc.add_paragraph().add_run(f"{T('Tablo', 'Table')} {no}").bold = True
    doc.add_paragraph().add_run(baslik).italic = True
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


def calistir(ad, fonk):
    try:
        fonk()
        print(f"  {ad}: tamam")
    except Exception as e:
        print(f"  {ad}: ATLANDI ({type(e).__name__}: {e})")
        atlanan.append({"cikti": ad, "neden": f"{type(e).__name__}: {e}"})


# ---------------------------------------------------------------
# E3 Degiskenlerin olcum penceresi ve ozeti (10g)
# ---------------------------------------------------------------
GRUP = {"demografi": ("Demografi ve kabul", "Demographics and admission"), "antropometri": ("Antropometri", "Anthropometry"),
        "SOFA": ("SOFA", "SOFA"), "tedavi": ("Tedavi", "Treatment"), "laboratuvar": ("Laboratuvar", "Laboratory"),
        "komorbidite": ("Eşlik eden hastalık", "Comorbidity"), "Braden": ("Braden", "Braden"), "JH-HLM": ("JH-HLM", "JH-HLM"),
        "hemsirelik": ("Hemşirelik", "Nursing")}
PENCERE = {"YB girisi": ("YBÜ girişi", "ICU admission"), "sabit": ("Sabit", "Fixed"),
           "hastane yatisi": ("Hastane yatışı", "Hospital admission"),
           "hastane yatisi basi - 72. saat": ("Hastane yatışı başı–72. saat", "Hospital admission to hour 72"),
           "0-24 saat": ("0–24 saat", "0–24 h"), "0-72 saat": ("0–72 saat", "0–72 h"),
           "hastane yatisi (taburculuk ICD kodlari, zaman yok)": ("Hastane yatışı (taburculuk tanı kodları, zamansız)",
                                                                  "Hospital admission (discharge diagnosis codes, untimed)")}
OZET = {"tek deger": ("Tek değer", "Single value"), "ilk": ("İlk", "First"), "en kotu": ("En kötü", "Worst"),
        "var/yok": ("Var/yok", "Any/none"), "en dusuk": ("En düşük", "Lowest"), "en yuksek": ("En yüksek", "Highest"),
        "ortalama": ("Ortalama", "Mean"), "sayi": ("Sayı", "Count")}


def e3():
    g = gerekli("10g_degisken_zamani.csv")
    model = g["model_07_birincil"].str.startswith("evet")
    tanim = ~model & (g["grup"] == "komorbidite")
    bilinmeyen = sorted({*g["pencere"], *g["ozet"], *g["grup"]} - {*PENCERE, *OZET, *GRUP})
    if bilinmeyen:
        raise ValueError(f"cevirisi olmayan deger(ler): {bilinmeyen}")
    satirlar = []
    for grp, x in g[model | tanim].groupby("grup", sort=False):
        satirlar.append(("panel", lab(GRUP, grp)))
        for _, r_ in x.iterrows():
            et = ozellik_etiketi(r_["degisken"], DIL) or r_["degisken"]
            kul = (T("Yalnızca tanımlayıcı", "Descriptive only") if not r_["model_07_birincil"].startswith("evet")
                   else T("Model (kukla)", "Model (dummy)") if "one-hot" in r_["model_07_birincil"] else T("Model", "Model"))
            satirlar.append([et, lab(PENCERE, r_["pencere"]), lab(OZET, r_["ozet"]), kul])
    n_mod = int(model.sum())
    apa_tablo("E3_degisken_zamani.docx", "E3",
              T("Değişkenlerin ölçüm penceresi ve özeti", "Measurement window and summary of variables"),
              [T("Değişken", "Variable"), T("Pencere", "Window"), T("Özet", "Summary"), T("Kullanım", "Use")], satirlar,
              T(f"Tahmin modellerine giren {n_mod} değişken (kategorik değişkenler kukla değişkenlere açılmıştır) ve "
                "yalnızca tanımlayıcı tabloda kullanılan Charlson değişkenleri. Saatler YBÜ girişinden itibarendir. "
                "Charlson indeksi taburculuk tanı kodlarından hesaplandığı ve 72. saatte bilinmediği için modellere "
                "alınmamıştır. Laboratuvar değerleri aynı hastane yatışındaki ölçümlerdir; en kötü değer albümin ve "
                "hemoglobinde en düşük, glukoz, kreatinin ve laktatta en yüksek değerdir. SOFA'da eksik bileşenler "
                "toplamda sıfır puan sayılmıştır. Braden puanları altı alt boyutun aynı anda kaydedildiği tam setlerden "
                "hesaplanmıştır. JH-HLM = Johns Hopkins En Yüksek Mobilite Düzeyi; RASS = Richmond Ajitasyon-Sedasyon "
                "Ölçeği; SOFA = Ardışık Organ Yetmezliği Değerlendirmesi; YBÜ = yoğun bakım ünitesi.",
                f"The {n_mod} variables entering the prediction models (categorical variables expanded to dummy "
                "variables) and the Charlson variables used only in the descriptive table. Hours are counted from ICU "
                "admission. The Charlson index was not used as a predictor because it is derived from discharge "
                "diagnosis codes and is unknown at hour 72. Laboratory values are measurements from the same hospital "
                "admission; worst is the lowest value for albumin and haemoglobin and the highest for glucose, "
                "creatinine and lactate. Missing SOFA components were scored as zero in the total. Braden scores were "
                "computed from complete sets in which all six subscales were recorded at the same time. ICU = intensive "
                "care unit; JH-HLM = Johns Hopkins Highest Level of Mobility; RASS = Richmond Agitation-Sedation Scale; "
                "SOFA = Sequential Organ Failure Assessment."))


# ---------------------------------------------------------------
# E4 Model ayarlari (10f)
# ---------------------------------------------------------------
ARALIK = {"log-duzgun": ("log-düzgün", "log-uniform"), "tamsayi": ("tamsayı", "integer"), "duzgun": ("düzgün", "uniform"),
          "secenekler:": ("seçenekler:", "options:")}


def deger_yaz(x):
    if sayi_mi(x):
        return tam(x) if float(x).is_integer() else ondalik(x, 4) if abs(float(x)) < 0.1 else ondalik(x, 3)
    if isinstance(x, str) and x.startswith("None (xgboost"):
        return T("varsayılan", "default")
    return x


def aralik_yaz(x):
    if not isinstance(x, str) or not x:
        return ""
    if x == "sabit":
        return T("sabit", "fixed")
    for k, v in ARALIK.items():
        x = x.replace(k, v[0] if DIL == "tr" else v[1])
    return x.replace(", ", "; ").replace(".", ",") if DIL == "tr" else x


def e4():
    gerekli("10f_model_ayarlari.csv")
    f = pd.read_csv(kaynak / "10f_model_ayarlari.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")  # "None" metin kalsin
    satirlar = []
    for mod in MODELLER:
        x = f[f["model"] == mod]
        if x.empty:
            continue
        satirlar.append(("panel", lab(MODEL, mod)))
        for _, r_ in x[(x["bolum"] == "hiperparametre") & (x["arama_araligi"] != "sabit")].iterrows():
            satirlar.append([r_["parametre"], deger_yaz(r_["deger"]), aralik_yaz(r_["arama_araligi"])])
        sabit = x[(x["bolum"] == "hiperparametre") & (x["arama_araligi"] == "sabit")]
        if len(sabit):
            satirlar.append([T("Sabit ayarlar", "Fixed settings"),
                             "; ".join(f"{r_['parametre']} = {deger_yaz(r_['deger'])}" for _, r_ in sabit.iterrows()), ""])
        oz = dict(zip(x.loc[x["bolum"] == "ozellik", "parametre"], x.loc[x["bolum"] == "ozellik", "deger"]))
        satirlar.append([T("Özellik sayısı", "Number of features"), tam(oz["giris ozellik sayisi"]), ""])
        if sayi_mi(oz.get("eksiklik gostergesi sayisi")) and float(oz["eksiklik gostergesi sayisi"]) > 0:
            satirlar.append([T("Eksiklik göstergesi", "Missingness indicators"), tam(oz["eksiklik gostergesi sayisi"]), ""])
        sut = dict(zip(x.loc[x["bolum"] == "arama", "parametre"], x.loc[x["bolum"] == "arama", "deger"]))
        if sayi_mi(sut.get("ic CV AUROC (secilen ayar)")):
            satirlar.append([T("İç çapraz doğrulama AUROC (seçilen ayar)", "Inner cross-validation AUROC (selected setting)"),
                             ondalik(sut["ic CV AUROC (secilen ayar)"], 3), ""])
        eksik = {"L2 lojistik": T("Eğitim verisinin ortancasıyla doldurma ve eksiklik göstergesi; ardından bütün sütunlar "
                                  "eğitim verisinde standartlaştırıldı (ortalama 0, SS 1)",
                                  "Median imputation from the training data with missingness indicators; all columns then "
                                  "standardised on the training data (mean 0, SD 1)"),
                 "Random Forest": T("Eğitim verisinin ortancasıyla doldurma ve eksiklik göstergesi; ölçekleme yok",
                                    "Median imputation from the training data with missingness indicators; no scaling"),
                 "XGBoost": T("Doldurma yok, eksik değerler algoritma içinde işlendi; ölçekleme yok",
                              "No imputation, missing values handled by the algorithm; no scaling")}[mod]
        satirlar.append([T("Eksik veri ve ölçekleme", "Missing data and scaling"), eksik, ""])
    kat = f[(f["model"] == MODELLER[0]) & f["parametre"].str.startswith("kategorik: ")]
    kukla = sum(int(re.search(r"(\d+) kukla", str(v)).group(1)) for v in kat["deger"])
    apa_tablo("E4_model_ayarlari.docx", "E4", T("Tahmin modellerinin ayarları", "Settings of the prediction models"),
              [T("Ayar", "Setting"), T("Seçilen değer", "Selected value"), T("Arama aralığı", "Search range")], satirlar,
              T("Dönemsel doğrulamanın eğitim verisinde (referans yıl grubu 2008–2016) seçilen ayarlar. Her algoritma için "
                "40 aday ayarla rastgele arama; iç döngü hastaya göre gruplandırılmış üç katlı çapraz doğrulama, ölçüt "
                f"AUROC. Kategorik değişkenler (cinsiyet, kabul türü, ilk YBÜ birimi, JH-HLM grubu) bütün düzeyleri "
                f"korunarak {kukla} kukla değişkene dönüştürüldü; 100'den az yatışı olan YBÜ birimleri birleştirildi. "
                "Sınıf ağırlıklandırması uygulanmadı. Braden referans modeli yalnızca en düşük toplam Braden puanını "
                "içeren cezasız lojistik regresyondur. AUROC = ROC eğrisi altındaki alan; JH-HLM = Johns Hopkins En "
                "Yüksek Mobilite Düzeyi; SS = standart sapma; YBÜ = yoğun bakım ünitesi.",
                "Settings selected on the training data of the period validation (anchor_year_group 2008–2016). Random "
                "search over 40 candidate settings per algorithm; inner loop three-fold cross-validation grouped by "
                "patient, criterion AUROC. Categorical variables (sex, admission type, first ICU unit, JH-HLM group) were "
                f"expanded into {kukla} dummy variables keeping all levels; ICU units with fewer than 100 stays were "
                "combined. No class weighting was applied. The Braden reference model is an unpenalised logistic "
                "regression with the lowest total Braden score only. AUROC = area under the ROC curve; ICU = intensive "
                "care unit; JH-HLM = Johns Hopkins Highest Level of Mobility; SD = standard deviation."))


# ---------------------------------------------------------------
# E5 72-168 saat penceresinde yatislarin durumu (10a)
# ---------------------------------------------------------------
DURUM = {"yeni BY 72-168 saat": ("72–168. saatte yeni basınç yaralanması", "New pressure injury in hours 72–168"),
         "BY'siz YBU'de olum < 168. saat": ("Yaralanmasız YBÜ'de ölüm (< 168. saat)", "ICU death without injury (< hour 168)"),
         "BY'siz sag taburculuk < 168. saat": ("Yaralanmasız sağ taburculuk (< 168. saat)",
                                              "Discharge alive without injury (< hour 168)"),
         "168. saatte YBU'de, BY'siz": ("168. saatte yaralanmasız olarak YBÜ'de", "In the ICU without injury at hour 168")}
KUME = {"ic_dogrulama": ("Tahmin kohortu (iç doğrulama)", "Prediction cohort (internal validation)"),
        "donemsel_dogrulama": ("Dönemsel test seti (referans yıl grubu 2017–2022)",
                               "Period test set (anchor_year_group 2017–2022)")}


def e5():
    d = gerekli("10a_pencere_bilesimi.csv")
    satirlar = []
    for tip, x in d.groupby("analiz_tipi", sort=False):
        satirlar.append(("panel", f"{lab(KUME, tip)}: n = {tam(x['kume_yatis'].iloc[0])}"))
        for _, r_ in x.iterrows():
            satirlar.append([lab(DURUM, r_["durum_168_saat"]), n_yuzde(r_["yatis"], r_["yuzde"])])
    apa_tablo("E5_pencere_bilesimi.docx", "E5",
              T("72–168 saat penceresinde yatışların durumu", "Status of stays in the 72–168-hour window"),
              [T("168. saatteki durum", "Status at hour 168"), "n (%)"], satirlar,
              T("Tahmin edilen sonuç 72–168. saatlerde gelişen yeni basınç yaralanmasıdır; diğer üç grup sonuç gelişmemiş "
                "sayılmıştır. 168. saatte YBÜ'de kalanlar arasında sonradan yaralanma gelişenler ve tam 168. saatte "
                "çıkanlar vardır. YBÜ = yoğun bakım ünitesi. ",
                "The predicted outcome is a new pressure injury in hours 72–168; the other three groups were counted as "
                "outcome-free. Stays still in the ICU at hour 168 include those with a later injury and those leaving at "
                "exactly hour 168. ICU = intensive care unit. ") + GIZLI_NOT)


# ---------------------------------------------------------------
# E6 Duyarlilik analizleri (07b, 07c_charlsonlu, 10b, 10c, 10c2)
# ---------------------------------------------------------------
def metrik(m, tip, model, surum=None):
    x = m[(m["analiz_tipi"] == tip) & (m["model"] == model) & (m["metrik"] == "auroc")]
    if surum is not None:
        x = x[x["surum"] == surum]
    return x.iloc[0] if len(x) else None


def e6():
    m = gerekli("07b_metrikler.csv")
    ch_m, ch_f = oku("07b_metrikler_charlsonlu.csv"), oku("07c_auroc_farki_charlsonlu.csv")
    b_m, b_f = oku("10b_metrikler.csv"), oku("10b_auroc_farki.csv")
    c_m, c_f = oku("10c_metrikler.csv"), oku("10c_auroc_farki.csv")
    birincil_ayni = T("birincil (aynı yatışlar)", "primary (same stays)")
    birincil = T("birincil", "primary")
    satirlar = []

    def satir(analiz, mod, r_, karsi="", f_=None):
        return [f"{analiz}: {lab(MODEL, mod)}", tam(r_["n"]) if r_ is not None else "–",
                tam(r_["olay"]) if r_ is not None else "–",
                etki_ga(r_["deger"], r_["alt_95"], r_["ust_95"]) if r_ is not None else "–", karsi,
                fark_ga(f_["auroc_farki"], f_["alt_95"], f_["ust_95"]) if f_ is not None else "–",
                p_hucre(f_["p_delong"]) if f_ is not None else "–"]

    for tip in ["ic_dogrulama", "donemsel_dogrulama"]:
        if (m["analiz_tipi"] == tip).sum() == 0:
            continue
        satirlar.append(("panel", lab(ANALIZ, tip)))
        ad = T("Birincil", "Primary")
        for mod in MODELLER + ["Braden toplam (lojistik)"]:
            satirlar.append(satir(ad, mod, metrik(m, tip, mod)))
        if b_m is not None and b_f is not None:
            ad = T("Ölümler çıkarılmış", "Deaths excluded")
            fb = b_f[b_f["analiz_tipi"] == tip]
            for mod in MODELLER + ["Braden toplam (lojistik)"]:
                f_ = fb[(fb["model"] == mod) & (fb["karsilastirma"].str.contains("birincil"))]
                satirlar.append(satir(ad, mod, metrik(b_m, tip, mod, "duyarlilik"), birincil_ayni if len(f_) else "",
                                      f_.iloc[0] if len(f_) else None))
            for _, f_ in fb[~fb["karsilastirma"].str.contains("birincil")].iterrows():
                satirlar.append([f"{ad}: {lab(MODEL, f_['model'])}", "", "", "", lab(MODEL, f_["karsilastirma"]),
                                 fark_ga(f_["auroc_farki"], f_["alt_95"], f_["ust_95"]), p_hucre(f_["p_delong"])])
        for df_m, df_f, ad, surum in [(c_m, c_f, T("SOFA bileşenleri", "SOFA components"), "duyarlilik"),
                                      (ch_m, ch_f, T("Charlson eklenmiş", "Charlson added"), None)]:
            if df_m is None or df_f is None:
                continue
            for mod in MODELLER:
                f_ = df_f[(df_f["analiz_tipi"] == tip) & (df_f["model"] == mod)]
                satirlar.append(satir(ad, mod, metrik(df_m, tip, mod, surum), birincil if len(f_) else "",
                                      f_.iloc[0] if len(f_) else None))
    se = oku("10c2_sofa_eksiklik.csv")
    sofa_not = ""
    if se is not None:
        s_ = se[se["kume"] == "tum kohort"].set_index("degisken")
        oran = {k: ("%" + ondalik(s_.loc[k, "yuzde"], 1)) if DIL == "tr" else (ondalik(s_.loc[k, "yuzde"], 1) + "%")
                for k in s_.index if sayi_mi(s_.loc[k, "yuzde"])}
        gz = [k for k in ["sofa_kardiyovaskuler", "sofa_mss"] if s_.loc[k, "eksik"] in GIZLI]
        sofa_not = T(f"SOFA bileşenlerinin eksiklik oranı (tüm kohort): en az bir bileşen {oran['en az bir bilesen']}, solunum "
                     f"{oran['sofa_solunum']}, karaciğer {oran['sofa_karaciger']}, koagülasyon {oran['sofa_koagulasyon']}, "
                     f"böbrek {oran['sofa_bobrek']}" + ("; kardiyovasküler ve merkezi sinir sistemi bileşenleri çok az "
                                                        "yatışta eksiktir (sayı gizli). " if gz else ". "),
                     f"Missingness of SOFA components (whole cohort): at least one component {oran['en az bir bilesen']}, "
                     f"respiratory {oran['sofa_solunum']}, liver {oran['sofa_karaciger']}, coagulation "
                     f"{oran['sofa_koagulasyon']}, renal {oran['sofa_bobrek']}" + ("; the cardiovascular and central "
                     "nervous system components are missing in very few stays (count suppressed). " if gz else ". "))
    apa_tablo("E6_duyarlilik.docx", "E6", T("Tahmin modelleri: duyarlılık analizleri", "Prediction models: sensitivity analyses"),
              [T("Analiz: model", "Analysis: model"), "n", T("Olay", "Events"), f"AUROC ({GA})", T("Karşılaştırma", "Comparison"),
               T(f"AUROC farkı ({GA})", f"Difference in AUROC ({GA})"), "p (DeLong)"], satirlar,
              T("Ölümler çıkarılmış: 72–168. saatlerde yaralanma gelişmeden YBÜ'de ölen yatışlar eğitim ve test verisinden "
                "çıkarılmış, modeller aynı ayarlar ve aynı aramayla yeniden eğitilmiştir; fark, birincil modellerin aynı "
                "yatışlardaki AUROC değerine göredir. Braden referans modeli tek değişkenli olduğundan AUROC'u birincil "
                "modelle aynıdır ve DeLong testi yapılmamıştır. SOFA bileşenleri: SOFA toplamı yerine altı bileşen eksik "
                "değerler doldurulmadan alınmıştır (XGBoost eksik değerleri kendi içinde işler; lojistik regresyon ve "
                "rastgele ormanda ortanca ile doldurma ve eksiklik göstergesi). Charlson eklenmiş: Charlson indeksi ve "
                "bileşenleri aday değişkenlere eklenmiştir. Fark = duyarlılık modeli − karşılaştırma; GA DeLong standart "
                f"hatasından, AUROC'un GA'sı 1000 tekrarlı hasta düzeyinde bootstrap ile. {sofa_not}"
                "AUROC = ROC eğrisi altındaki alan; SOFA = Ardışık Organ Yetmezliği Değerlendirmesi; YBÜ = yoğun bakım "
                "ünitesi. ",
                "Deaths excluded: stays ending in ICU death without injury in hours 72–168 were removed from training and "
                "test data and the models were retrained with the same settings and search; the difference is relative "
                "to the AUROC of the primary models in the same stays. The Braden reference model has a single "
                "predictor, so its AUROC equals that of the primary model and no DeLong test was done. SOFA components: "
                "the six components replaced the SOFA total without imputation (XGBoost handles missing values "
                "internally; logistic regression and random forest use median imputation with missingness indicators). "
                "Charlson added: the Charlson index and its components were added to the candidate predictors. "
                "Difference = sensitivity model − comparison; CI from the DeLong standard error, CI of the AUROC from "
                f"1000 patient-level bootstrap replicates. {sofa_not}AUROC = area under the ROC curve; ICU = intensive "
                "care unit; SOFA = Sequential Organ Failure Assessment. ") + GIZLI_NOT, yatay=True)


print(f"Kaynak: {kaynak}  Hedef: {hedef}  Dil: {DIL}")
for ad, f in [("E3", e3), ("E4", e4), ("E5", e5), ("E6", e6)]:
    calistir(ad, f)
pd.DataFrame(atlanan, columns=["cikti", "neden"]).to_csv(hedef / "09bz_atlananlar.csv", index=False, encoding="utf-8-sig")
print(f"\n{len(atlanan)} cikti atlandi (09bz_atlananlar.csv). Ciktilar: {hedef}")
