"""Degiskenlerin ham degerden analiz degerine cevrilme kurallari.

Bu dosyadaki kurallar yontem bolumunde aynen raporlanmalidir.
Tam veride kurallara uymayan degerler 03_on_denetim.py tarafindan
'tanimsiz' olarak listelenir; o listeye bakip kurallari guncelleyin.
"""
import re

# ---------------------------------------------------------------
# Itemid'leri bulmak icin anahtar kelimeler (d_items.label uzerinde)
# Her kalip bir degisken grubuna karsilik gelir.
# ---------------------------------------------------------------
ARAMA_KALIPLARI = {
    "jh_hlm": r"JH-HLM",
    "rn_mobilite_hedefi": r"RN Daily Mobility Goal",
    "am_pac": r"AM-PAC",
    "braden_alt": r"^Braden ",
    "by_evre_eski": r"^Pressure Ulcer Stage #",
    "by_evre_yeni": r"^Pressure ulcer #\d+- Stage$",
    "by_kabulde_var": r"^Pressure Ulcer Present$",
    "by_tespit_tarihi": r"Date Indentified|Date Identified",
    "by_konum": r"^Pressure Ulcer #\d+- Location$",
    # Yeni "Pressure Injury" sablonu (Skin - Assessment): evre alani yok, yaraya numara verilmiyor
    "by_yeni_sablon": r"^Pressure Injury Location$|^No Pressure Injury Present$",
    "ncp_impaired_mobility": r"Impaired Mobility\s+NCP",
    "ncp_activity_intolerance": r"Activity Intolerance\s+NCP",
    "ncp_skin_integrity": r"Altered Skin Integrity NCP",
    "rom": r"^Range of Motion",
    "pozisyon": r"^Position$|^Turn$",
    "yardimci_cihaz": r"^Assist(?:ance)? Device$",
    "tedavi_edici_yatak": r"^Therapeutic Bed$",
    "basinc_azaltici_cihaz": r"^Pressure Reducing Device$",
    "gks": r"^GCS - ",
    # Faz 2 (05_analiz_seti.py)
    "boy": r"^Height$|^Height \(cm\)$",
    "kilo": r"^Admission Weight \((?:Kg|lbs\.)\)$|^Daily Weight$",
    "sedatif_propofol": r"^Propofol$",
    "sedatif_midazolam": r"^Midazolam \(Versed\)$",
    "sedatif_deksmedetomidin": r"^Dexmedetomidine \(Precedex\)$",
    "rass": r"^Richmond-RAS Scale$",
    "kisitlama": r"^Restraint \(Non-violent\)$|^Restraints \(Violent\)$",
}

# Laboratuvar: d_labitems.label uzerinde; 02 yalnizca fluid = 'Blood' satirlarini alir
ARAMA_KALIPLARI_LAB = {
    "lab_albumin": r"^Albumin$",
    "lab_hemoglobin": r"^Hemoglobin$",
    "lab_glukoz": r"^Glucose$",
    "lab_kreatinin": r"^Creatinine$",
    "lab_laktat": r"^Lactate$",
}

# ---------------------------------------------------------------
# Faz 2 degisken kurallari
# ---------------------------------------------------------------
# Tum degiskenler intime ile intime + PENCERE_SAAT arasindan hesaplanir (sizinti olmasin).
# SOFA ilk 24 saatten (mimic-code first_day_sofa puanlamasi; pencere intime - 6 saat yerine intime).
PENCERE_SAAT = 72
SOFA_SAAT = 24

# Boy ve kilo: itemid -> cm / kg carpani; makul aralik disi deger bos sayilir
BOY_CARPAN = {226730: 1.0, 226707: 2.54}          # cm, inch
KILO_CARPAN = {226512: 1.0, 224639: 1.0, 226531: 0.453592}  # kg, kg, lbs
BOY_ARALIK = (120, 220)
KILO_ARALIK = (25, 300)
BMI_ARALIK = (12, 70)  # bu araligin disindaki BMI bos sayilir; atanan BMI de bu araliga sinirlanir

# Laboratuvar "en kotu" deger yonu
LAB_EN_KOTU = {"lab_albumin": "min", "lab_hemoglobin": "min", "lab_glukoz": "max",
               "lab_kreatinin": "max", "lab_laktat": "max"}

# Cihaz/kisitlama: "var" sayilmayan degerler (kucuk harf). Bos deger hicbir zaman "var" degildir.
CIHAZ_YOK = {
    "tedavi_edici_yatak": {"none"},
    "basinc_azaltici_cihaz": {"none"},
    "yardimci_cihaz": {"none", "independent"},
}
KISITLAMA_VAR = {"on"}  # Restraint (Non-violent): On/Off; Restraints (Violent) icin tam veride 03c'ye bak

# Analiz setindeki degisken turleri (05a ozeti ve 06 Tablo 1). Digerleri sayisal.
ANALIZ_KATEGORIK = ["cinsiyet", "kabul_tipi", "ilk_yb_birimi", "anchor_year_group", "jh_hlm_grup",
                    "olay_tipi", "olay_tipi_evre2", "olay_tipi_bilinen"]
ANALIZ_IKILI = ["mekanik_ventilasyon", "vazopresor", "sedatif_propofol", "sedatif_midazolam",
                "sedatif_deksmedetomidin", "sedatif_herhangi", "fiziksel_kisitlama", "diyabet", "periferik_damar",
                "kalp_yetmezligi", "tedavi_edici_yatak", "basinc_azaltici_cihaz", "yardimci_cihaz",
                "rn_mobilite_hedefi", "ncp_impaired_mobility", "ncp_activity_intolerance", "ncp_skin_integrity",
                "yeni_by_72_168", "yeni_by_72_168_evre2", "yeni_by_72_168_bilinen"]

# JH-HLM gruplari (en yuksek duzey uzerinden)
JH_GRUP = {1: "1-3", 2: "1-3", 3: "1-3", 4: "4-5", 5: "4-5", 6: "6-8", 7: "6-8", 8: "6-8"}


# RASS: metin "-2 Light sedation ..." -> -2
def rass_sayi(deger):
    if deger is None:
        return None
    m = re.match(r"\s*([+-]?[0-5])\b", str(deger))
    return int(m.group(1)) if m else None

# ---------------------------------------------------------------
# JH-HLM: degerler metin ("2b - Turning in bed"). Bastaki rakam alinir.
# MIMIC 2. duzeyi 2a/2b/2c olarak boluyor; hepsi 2 sayilir.
# ---------------------------------------------------------------
def jh_hlm_sayi(deger):
    if deger is None:
        return None
    m = re.match(r"\s*([1-8])", str(deger))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------
# Braden: toplam skor kayitli degil. Alt boyutlar metin olarak tutuluyor.
# Puanlar Braden olceginin standart puanlamasidir (toplam 6-23).
# ---------------------------------------------------------------
BRADEN_ITEMID = {
    224054: "duyusal_algi",
    224055: "nem",
    224056: "aktivite",
    224057: "hareket",
    224058: "beslenme",
    224059: "surtunme",
}

BRADEN_PUAN = {
    "duyusal_algi": {"completely limited": 1, "very limited": 2,
                     "slight impairment": 3, "slightly limited": 3, "no impairment": 4},
    "nem": {"consistently moist": 1, "constantly moist": 1, "moist": 2, "very moist": 2,
            "occasionally moist": 3, "rarely moist": 4},
    "aktivite": {"bedfast": 1, "chairfast": 2, "walks occasionally": 3, "walks frequently": 4},
    "hareket": {"completely immobile": 1, "very limited": 2,
                "slight limitations": 3, "slightly limited": 3, "no limitations": 4, "no limitation": 4},
    "beslenme": {"very poor": 1, "probably inadequate": 2, "adequate": 3, "excellent": 4},
    "surtunme": {"problem": 1, "potential problem": 2, "no apparent problem": 3},
}

# Mobiliteyle ortusmeyen alt boyutlar (mobilite disi Braden skoru)
BRADEN_MOBILITE_DISI = ["duyusal_algi", "nem", "beslenme", "surtunme"]


def braden_puan(alt_boyut, deger):
    if deger is None:
        return None
    return BRADEN_PUAN[alt_boyut].get(str(deger).strip().lower())


# ---------------------------------------------------------------
# Basinc yarasi evresi. Iki kayit bicimi var:
#   eski: "Pressure Ulcer Stage #1..#10" -> "Red; unbroken", "Not applicable" ...
#   yeni: "Pressure ulcer #1- Stage"     -> "2 - Stage II", "Suspected deep tissue injury" ...
# "#2" yaranin numarasidir, evresi degildir.
# "Not applicable" ve "Status Changed: Skin Impairment" yara DEGILDIR.
# "Unknown" ve "Unable to assess; dressing not removed": yara var, evresi bilinmiyor.
# Eski sablonda evre 4 metni de "Full thickness" ile basliyor
# ("... with damage to muscle, bone ..."); bu yuzden evre 3'ten once kontrol edilir.
# Donus: "1","2","3","4","DDH" (derin doku hasari), "EV" (evrelendirilemeyen),
#        "BILINMIYOR" (yara var, evre bilinmiyor),
#        None (yara yok) veya "tanimsiz" (kurala uymayan deger).
# ---------------------------------------------------------------
YARA_DEGIL = {"not applicable", "none", "n/a", "na", "no", "0", "status changed: skin impairment"}
EVRE_BILINMIYOR = {"unknown", "unable to assess; dressing not removed"}


def by_evre(deger):
    if deger is None:
        return None
    d = str(deger).strip().lower()
    if d == "" or d in YARA_DEGIL:
        return None
    if d in EVRE_BILINMIYOR:
        return "BILINMIYOR"
    if (re.match(r"^4\b", d) or "stage iv" in d or "extensive destruction" in d
            or "damage to muscle" in d):
        return "4"
    if re.match(r"^3\b", d) or "stage iii" in d or "full thickness" in d:
        return "3"
    if re.match(r"^2\b", d) or "stage ii" in d or "partial thickness" in d:
        return "2"
    if re.match(r"^1\b", d) or "stage i" in d or "unbroken" in d:
        return "1"
    if "deep tissue" in d:
        return "DDH"
    if "unable to stage" in d or "unstageable" in d or "eschar" in d:
        return "EV"
    return "tanimsiz"


# Analiz pencereleri (saat)
MARUZIYET_SAAT = 72
SABIT_PENCERE_BITIS = 168
IDARI_SANSUR_GUN = 28

# Bundan az yatisli YB birimleri modellerde (06 Cox strata ve lojistik kukla, 07 ozellik) "diger" olarak birlesir
SEYREK_BIRIM = 100
