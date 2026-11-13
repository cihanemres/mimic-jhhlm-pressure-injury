# Adim 6b (Faz 2): Duyarlilik (a) Fine-Gray alt dagilim hazard modeli.
# Girdi: <cikti>/ozel/06_atanmis_veri.csv.gz (06_istatistik.py'nin MICE ile atadigi veri setleri;
# birincil modelle ayni atamalar ve ayni terimler). Olay 1 = yeni basinc yarasi; 2 = YB olumu ve
# 3 = canli taburculuk (ikisi de yarisan); 0 = idari sansur. first_careunit strata. Rubin kurallariyla birlestirilir.
# Standart hata hasta duzeyinde kumelenmis (cluster(subject_id), robust); *_naif sutunlari kumelenmemis.
# Cikti: <cikti>/paylasilabilir/06i_fine_gray.csv (06d_modeller.csv ile ayni sutunlar)
#
# Kullanim (proje kokunden):
#   "C:\Program Files\R\R-4.6.1\bin\Rscript.exe" code/06b_fine_gray.R outputs_tam
suppressPackageStartupMessages(library(survival))

args <- commandArgs(trailingOnly = TRUE)
cikti <- if (length(args) >= 1) args[1] else "outputs"
veri <- read.csv(gzfile(file.path(cikti, "ozel", "06_atanmis_veri.csv.gz")))
terimler <- setdiff(names(veri), c("atama", "stay_id", "subject_id", "ilk_yb_birimi", "anchor_year_group",
                                   "sure_saat", "olay_kod_yeni_by"))
maruziyet <- c("jh_4_5", "jh_6_8")
veri$olay <- factor(veri$olay_kod_yeni_by, levels = c(0, 1, 2, 3),
                    labels = c("sansur", "yeni_by", "yb_olum", "taburculuk"))

# finegray sayma sureci baslangic < bitis ister: 72. saatte olan olay (sure 0) 1 dakika sayilir
veri$sure_saat <- pmax(veri$sure_saat, 1 / 60)

m <- max(veri$atama)
q <- list()
u <- list()
un <- list()
for (i in seq_len(m)) {
  v <- veri[veri$atama == i, ]
  t_i <- terimler[sapply(v[terimler], function(x) length(unique(x)) > 1)]  # sabit terim duser
  # subject_id formulde: finegray yalnizca formuldeki degiskenleri tasir (model terimi degil, kume icin)
  f <- as.formula(paste("Surv(sure_saat, olay) ~", paste(c(t_i, "ilk_yb_birimi", "subject_id"), collapse = " + ")))
  fg <- finegray(f, data = v, etype = "yeni_by")
  ff <- as.formula(paste("Surv(fgstart, fgstop, fgstatus) ~", paste(t_i, collapse = " + "),
                         "+ strata(ilk_yb_birimi)"))
  fit <- coxph(ff, data = fg, weights = fgwt, cluster = subject_id)
  q[[i]] <- coef(fit)
  u[[i]] <- diag(vcov(fit))
  un[[i]] <- setNames(diag(fit$naive.var), names(coef(fit)))
}
ortak <- Reduce(intersect, lapply(q, names))
Q <- do.call(rbind, lapply(q, function(x) x[ortak]))
qbar <- colMeans(Q)
B <- if (m > 1) apply(Q, 2, var) else rep(0, length(ortak))
birlestir <- function(u_) {  # Rubin: toplam varyans, serbestlik derecesi, t kritik degeri
  W <- colMeans(do.call(rbind, lapply(u_, function(x) x[ortak])))
  df <- ifelse(B > 0, (m - 1) * (1 + W / ((1 + 1 / m) * B))^2, 1e6)
  list(se = sqrt(W + (1 + 1 / m) * B), df = df, t = qt(0.975, df))
}
r <- birlestir(u)
nv <- birlestir(un)
se <- r$se
df <- r$df
tdeg <- r$t

v1 <- veri[veri$atama == 1, ]
gizle <- function(x) ifelse(x > 0 & x < 5, "<5", as.character(x))
sonuc <- data.frame(
  analiz_tipi = "duyarlilik", analiz_kodu = "a_fine_gray", analiz = "Fine-Gray alt dagilim hazard, MICE",
  model = "Fine-Gray (survival::finegray + coxph), strata first_careunit, robust SE (hasta kumesi)", sonuc = "yeni_by",
  etki_olcusu = "SHR", terim = ortak, maruziyet = ortak %in% maruziyet, katsayi = qbar, se = se,
  etki = exp(qbar), alt_95 = exp(qbar - tdeg * se), ust_95 = exp(qbar + tdeg * se),
  p = 2 * pt(abs(qbar / se), df, lower.tail = FALSE),
  n = gizle(nrow(v1)), olay = gizle(sum(v1$olay_kod_yeni_by == 1)), atama_sayisi = m,
  se_naif = nv$se, alt_95_naif = exp(qbar - nv$t * nv$se), ust_95_naif = exp(qbar + nv$t * nv$se),
  p_naif = 2 * pt(abs(qbar / nv$se), nv$df, lower.tail = FALSE)
)
yol <- file.path(cikti, "paylasilabilir", "06i_fine_gray.csv")
write.csv(sonuc, yol, row.names = FALSE, fileEncoding = "UTF-8")
print(sonuc[sonuc$maruziyet, c("terim", "etki", "alt_95", "ust_95", "p")], row.names = FALSE)
cat("Cikti:", yol, "\n")
