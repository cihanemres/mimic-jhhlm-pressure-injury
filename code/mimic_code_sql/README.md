# mimic-code concept SQL (DuckDB)

Bu klasördeki `.sql` dosyaları değiştirilmeden alınmıştır.

- Kaynak: https://github.com/MIT-LCP/mimic-code, klasör `mimic-iv/concepts_duckdb/`
- Commit: `25f6c47ca99bb3b904b704aa4f072850cec6681b`
- Lisans: MIT (`LICENSE`)
- Atıf: Johnson AEW, Stone DJ, Celi LA, Pollard TJ. The MIMIC Code Repository: enabling reproducibility in critical care research. JAMIA. 2018;25(1):32-39.

`05_analiz_seti.py` bu dosyaları sırayla çalıştırır ve `mimiciv_derived` şemasında tablolar oluşturur. Tablolar yalnızca kohort hastalarının kayıtlarıyla kurulur.

| Dosya | Kullanım |
|---|---|
| age, charlson | Charlson indeksi, diyabet, periferik damar hastalığı, kalp yetmezliği |
| bg, chemistry, complete_blood_count, enzyme, gcs, vitalsign, urine_output | SOFA bileşenleri |
| oxygen_delivery, ventilator_setting, ventilation | Mekanik ventilasyon (`InvasiveVent`), SOFA solunum |
| norepinephrine, epinephrine, dopamine, dobutamine | SOFA kardiyovasküler |
| norepinephrine, epinephrine, dopamine, phenylephrine, vasopressin | Vazopresör değişkeni (dobutamin inotrop olduğu için dahil değil) |

SOFA, `firstday/first_day_sofa.sql` dosyasının puanlamasıyla aynıdır. Tek fark pencerededir: mimic-code `intime − 6 saat` ile `intime + 24 saat` arasını kullanır, bu projede pencere `intime` ile `intime + 24 saat` arasıdır.

Dosyaları güncellemek için yukarıdaki commit kimliğini değiştirip aynı dosyaları yeniden indirin; ardından demo veride 05'in çıktısını karşılaştırın.
