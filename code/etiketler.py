"""Degisken ve kategori etiketleri (Turkce, Ingilizce): makale tablolari ve sekilleri (09) icin tek kaynak.

Her ozellik etiketi, adi ile istatistigi ("ilk", "en kotu", "en dusuk" ...) ve varsa birimini icerir. Butun degiskenler
0-72 saat penceresindendir (SOFA ilk 24 saat); pencere tablo ve sekil notlarinda yazilir. "En kotu" yonu kurallar.py
LAB_EN_KOTU'dadir (albumin ve hemoglobin en dusuk; glukoz, kreatinin ve laktat en yuksek). Ayni etiketler Tablo 1'de
ve yontem metninde kullanilmalidir. Yeni bir analiz degiskeni (05) ya da ozellik (07a) eklenirse buraya da eklenmeli;
09 sozlukte olmayan ozellik icin uyarir ve 09z_atlananlar.csv'ye yazar.
"""

# degisken -> (tr, en)
DEGISKEN = {
    # Demografi ve antropometri
    "yas": ("Yaş (yıl)", "Age (years)"),
    "cinsiyet": ("Cinsiyet", "Sex"),
    "kadin": ("Kadın", "Female"),
    "boy_cm": ("Boy (cm)", "Height (cm)"),
    "kilo_kg": ("Kilo (kg)", "Weight (kg)"),
    "bmi": ("BKİ (kg/m²)", "BMI (kg/m²)"),
    "kabul_tipi": ("Kabul tipi", "Admission type"),
    "ilk_yb_birimi": ("İlk YBÜ birimi", "First ICU unit"),
    "anchor_year_group": ("Referans yıl grubu", "Period (anchor_year_group)"),
    # Hastalik agirligi ve tedavi
    "sofa_24s": ("SOFA (ilk 24 saat)", "SOFA (first 24 h)"),
    "sofa_solunum": ("SOFA solunum (ilk 24 saat)", "SOFA respiratory (first 24 h)"),
    "sofa_koagulasyon": ("SOFA koagülasyon (ilk 24 saat)", "SOFA coagulation (first 24 h)"),
    "sofa_karaciger": ("SOFA karaciğer (ilk 24 saat)", "SOFA liver (first 24 h)"),
    "sofa_kardiyovaskuler": ("SOFA kardiyovasküler (ilk 24 saat)", "SOFA cardiovascular (first 24 h)"),
    "sofa_mss": ("SOFA merkezi sinir sistemi (ilk 24 saat)", "SOFA central nervous system (first 24 h)"),
    "sofa_bobrek": ("SOFA böbrek (ilk 24 saat)", "SOFA renal (first 24 h)"),
    "mekanik_ventilasyon": ("Mekanik ventilasyon", "Mechanical ventilation"),
    "vazopresor": ("Vazopresör", "Vasopressor"),
    "sedatif_propofol": ("Sedatif infüzyon: propofol", "Sedative infusion: propofol"),
    "sedatif_midazolam": ("Sedatif infüzyon: midazolam", "Sedative infusion: midazolam"),
    "sedatif_deksmedetomidin": ("Sedatif infüzyon: deksmedetomidin", "Sedative infusion: dexmedetomidine"),
    "sedatif_herhangi": ("Sedatif infüzyon", "Sedative infusion"),
    "rass_en_dusuk": ("RASS, en düşük", "RASS, lowest"),
    "rass_ortalama": ("RASS, ortalama", "RASS, mean"),
    "fiziksel_kisitlama": ("Fiziksel kısıtlama", "Physical restraint"),
    # Laboratuvar
    "albumin_ilk": ("Albümin, ilk (g/dL)", "Albumin, first (g/dL)"),
    "albumin_en_kotu": ("Albümin, en kötü (g/dL)", "Albumin, worst (g/dL)"),
    "hemoglobin_ilk": ("Hemoglobin, ilk (g/dL)", "Haemoglobin, first (g/dL)"),
    "hemoglobin_en_kotu": ("Hemoglobin, en kötü (g/dL)", "Haemoglobin, worst (g/dL)"),
    "glukoz_ilk": ("Glukoz, ilk (mg/dL)", "Glucose, first (mg/dL)"),
    "glukoz_en_kotu": ("Glukoz, en kötü (mg/dL)", "Glucose, worst (mg/dL)"),
    "kreatinin_ilk": ("Kreatinin, ilk (mg/dL)", "Creatinine, first (mg/dL)"),
    "kreatinin_en_kotu": ("Kreatinin, en kötü (mg/dL)", "Creatinine, worst (mg/dL)"),
    "laktat_ilk": ("Laktat, ilk (mmol/L)", "Lactate, first (mmol/L)"),
    "laktat_en_kotu": ("Laktat, en kötü (mmol/L)", "Lactate, worst (mmol/L)"),
    # Komorbidite (yatis tanilarindan; pencere disi)
    "charlson": ("Charlson indeksi", "Charlson index"),
    "charlson_yassiz": ("Charlson indeksi (yaş puanı hariç)", "Charlson index (age points excluded)"),
    "diyabet": ("Diyabet (Charlson bileşeni)", "Diabetes (Charlson component)"),
    "periferik_damar": ("Periferik damar hastalığı (Charlson bileşeni)",
                        "Peripheral vascular disease (Charlson component)"),
    "kalp_yetmezligi": ("Kalp yetmezliği (Charlson bileşeni)", "Heart failure (Charlson component)"),
    # Braden
    "braden_toplam_ilk": ("Braden toplam, ilk", "Braden total, first"),
    "braden_duyusal_algi_ilk": ("Braden duyusal algı, ilk", "Braden sensory perception, first"),
    "braden_nem_ilk": ("Braden nem, ilk", "Braden moisture, first"),
    "braden_aktivite_ilk": ("Braden aktivite, ilk", "Braden activity, first"),
    "braden_hareket_ilk": ("Braden hareketlilik, ilk", "Braden mobility, first"),
    "braden_beslenme_ilk": ("Braden beslenme, ilk", "Braden nutrition, first"),
    "braden_surtunme_ilk": ("Braden sürtünme ve makaslama, ilk", "Braden friction and shear, first"),
    "braden_mobilite_disi_ilk": ("Mobilite dışı Braden, ilk", "Mobility-excluded Braden, first"),
    "braden_toplam_en_dusuk": ("Braden toplam, en düşük", "Braden total, lowest"),
    "braden_duyusal_algi_en_dusuk": ("Braden duyusal algı, en düşük", "Braden sensory perception, lowest"),
    "braden_nem_en_dusuk": ("Braden nem, en düşük", "Braden moisture, lowest"),
    "braden_aktivite_en_dusuk": ("Braden aktivite, en düşük", "Braden activity, lowest"),
    "braden_hareket_en_dusuk": ("Braden hareketlilik, en düşük", "Braden mobility, lowest"),
    "braden_beslenme_en_dusuk": ("Braden beslenme, en düşük", "Braden nutrition, lowest"),
    "braden_surtunme_en_dusuk": ("Braden sürtünme ve makaslama, en düşük", "Braden friction and shear, lowest"),
    "braden_mobilite_disi_en_dusuk": ("Mobilite dışı Braden, en düşük", "Mobility-excluded Braden, lowest"),
    # Mobilite
    "jh_hlm_ilk": ("JH-HLM, ilk", "JH-HLM, first"),
    "jh_hlm_en_yuksek": ("JH-HLM, en yüksek", "JH-HLM, highest"),
    "jh_hlm_ortalama": ("JH-HLM, ortalama", "JH-HLM, mean"),
    "jh_hlm_kayit_sayisi": ("JH-HLM kayıt sayısı", "JH-HLM, number of records"),
    "jh_hlm_grup": ("JH-HLM grubu (en yüksek)", "JH-HLM group (highest)"),
    "am_pac_ilk": ("AM-PAC, ilk", "AM-PAC, first"),
    "am_pac_en_dusuk": ("AM-PAC, en düşük", "AM-PAC, lowest"),
    # Onleyici girisimler ve bakim planlari
    "pozisyon_degistirme_24s": ("Pozisyon değiştirme (/24 saat)", "Repositioning (per 24 h)"),
    "tedavi_edici_yatak": ("Tedavi edici yatak", "Therapeutic bed"),
    "basinc_azaltici_cihaz": ("Basınç azaltıcı cihaz", "Pressure-reducing device"),
    "yardimci_cihaz": ("Yardımcı cihaz", "Assistive device"),
    "rn_mobilite_hedefi": ("Hemşire mobilite hedefi kaydı", "Nurse-documented mobility goal"),
    "ncp_impaired_mobility": ("Bakım planı: Impaired Mobility", "Care plan: Impaired Mobility"),
    "ncp_activity_intolerance": ("Bakım planı: Activity Intolerance", "Care plan: Activity Intolerance"),
    "ncp_skin_integrity": ("Bakım planı: Altered Skin Integrity", "Care plan: Altered Skin Integrity"),
    # Sonuclar (07 ozelligi degil)
    "olay_tipi": ("Sonuç (28. gün)", "Outcome (day 28)"),
    "yeni_by_72_168": ("Yeni BY, 72–168 saat", "New PI, hours 72–168"),
}

# Kategorik degiskenlerin kategorileri -> (tr, en). YB birimlerinin Ingilizce adlari MIMIC-IV'teki adlardir.
KATEGORI = {
    "F": ("Kadın", "Female"), "M": ("Erkek", "Male"),
    "yeni_by": ("Yeni BY", "New PI"), "yb_olum": ("YBÜ ölümü", "ICU death"),
    "taburculuk": ("Canlı taburculuk", "Discharged alive"), "sansur": ("İdari sansür", "Administrative censoring"),
    "diger": ("Diğer (birleştirilmiş)", "Other (merged)"),
    "1-3": ("1–3", "1–3"), "4-5": ("4–5", "4–5"), "6-8": ("6–8", "6–8"),
    # Kabul tipi
    "AMBULATORY OBSERVATION": ("Ayaktan gözlem", "Ambulatory observation"),
    "DIRECT EMER.": ("Doğrudan acil", "Direct emergency"),
    "DIRECT OBSERVATION": ("Doğrudan gözlem", "Direct observation"),
    "ELECTIVE": ("Elektif", "Elective"),
    "EU OBSERVATION": ("Acil birim gözlemi", "Emergency unit observation"),
    "EW EMER.": ("Acil servis", "Emergency ward"),
    "OBSERVATION ADMIT": ("Gözlem yatışı", "Observation admission"),
    "SURGICAL SAME DAY ADMISSION": ("Aynı gün cerrahi yatış", "Surgical same-day admission"),
    "URGENT": ("İvedi", "Urgent"),
    # YB birimleri
    "Cardiac Vascular Intensive Care Unit (CVICU)": ("Kalp-damar cerrahisi YBÜ (CVICU)",
                                                     "Cardiac Vascular Intensive Care Unit (CVICU)"),
    "Coronary Care Unit (CCU)": ("Koroner YBÜ (CCU)", "Coronary Care Unit (CCU)"),
    "Medical Intensive Care Unit (MICU)": ("Dahili YBÜ (MICU)", "Medical Intensive Care Unit (MICU)"),
    "Medical/Surgical Intensive Care Unit (MICU/SICU)": ("Dahili/cerrahi YBÜ (MICU/SICU)",
                                                         "Medical/Surgical Intensive Care Unit (MICU/SICU)"),
    "Neuro Intermediate": ("Nöroloji ara bakım", "Neuro Intermediate"),
    "Neuro Stepdown": ("Nöroloji basamak bakım", "Neuro Stepdown"),
    "Neuro Surgical Intensive Care Unit (Neuro SICU)": ("Nöroşirürji YBÜ (Neuro SICU)",
                                                        "Neuro Surgical Intensive Care Unit (Neuro SICU)"),
    "Surgical Intensive Care Unit (SICU)": ("Cerrahi YBÜ (SICU)", "Surgical Intensive Care Unit (SICU)"),
    "Trauma SICU (TSICU)": ("Travma cerrahi YBÜ (TSICU)", "Trauma SICU (TSICU)"),
}

KUKLA_KAYNAK = ["cinsiyet", "kabul_tipi", "ilk_yb_birimi", "jh_hlm_grup"]  # 07'deki kategorik ozellikler
EKSIK_ONEK = "missingindicator_"  # Random Forest pipeline'inin eksiklik gostergesi (SimpleImputer add_indicator)


def ozellik_etiketi(ozellik, dil):
    """07 ozellik adi -> etiket; sozlukte yoksa None. Kukla: 'Degisken: kategori'; eksiklik gostergesi: ' (eksik)'."""
    i = 0 if dil == "tr" else 1
    eksik = ozellik.startswith(EKSIK_ONEK)
    o = ozellik[len(EKSIK_ONEK):] if eksik else ozellik
    if o in DEGISKEN:
        et = DEGISKEN[o][i]
    else:
        et = None
        for on in KUKLA_KAYNAK:
            kat = o[len(on) + 1:] if o.startswith(on + "_") else None
            # 07 ozellik adlarinda "<" -> "lt", "[" -> "(" yapilir; MIMIC kategorilerinde bunlar yok
            if kat is not None and kat in KATEGORI:
                et = f"{DEGISKEN[on][i]}: {KATEGORI[kat][i]}"
    if et is None:
        return None
    return et + ((" (eksik)" if dil == "tr" else " (missing)") if eksik else "")
