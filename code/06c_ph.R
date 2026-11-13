# Adim 6c (Faz 2): Orantili hazard ihlali icin analizler. 06_istatistik.py'den sonra calistirilir.
# Girdi: <cikti>/ozel/06_atanmis_veri.csv.gz (06_istatistik.py'nin MICE ile atadigi veri setleri).
# Tum modeller cause-specific Cox: olay yeni basinc yarasi; YB olumu, canli taburculuk ve idari sansur sansur.
# Strata = YB birimi (seyrekler "diger" olarak birlesik) x anchor_year_group; yil kuklalari modelde yok.
# Tum atanmis veri setlerinde kestirilir, Rubin kurallariyla birlestirilir (t dagilimi, Rubin sd).
# Standart hatalar hasta duzeyinde kumelenmis (cluster = subject_id, robust); *_naif sutunlari kumelenmemis.
# cox.zph kumelenmemis modelde (standart test).
#
#   1. Birincil HR -> 06d_modeller.csv (analiz_kodu birincil_strata_birim_yil)
#      cox.zph (rank zaman donusumu) her atamada -> 06e2_ph_varsayimi_coxzph.csv: ilk atanmis setin
#      ki-kare ve p degeri, tum atamalarin D2 ile birlestirilmis p degeri (Li, Meng, Raghunathan 1991)
#   2. Donem bazinda HR: survSplit ile 72-168 saat ve >168 saat; donem x maruziyet etkilesimi
#      (>168 HR / 72-168 HR) -> 06j_donem_hr.csv
#   3. Duyarlilik (i): bes karistirici x log(zaman) etkilesimi (tt) -> 06d_modeller.csv
#      (analiz_kodu i_tt_log_zaman; yalnizca JH-HLM HR'leri)
#   4. jh_4_5 ve jh_6_8 icin Schoenfeld grafigi (ilk atanmis set): yalnizca yumusatilmis beta(t) egrisi
#      (dogal spline, 4 sd) ve %95 GA bandi; tek tek artik noktasi yok, egri 5.-95. yuzdelik arasinda
#      -> 06e3_schoenfeld_jhhlm.png / .svg
# Hata veren analiz atlanir, 06z_hatalar.csv'ye eklenir.
#
# Kullanim (proje kokunden):
#   "C:\Program Files\R\R-4.6.1\bin\Rscript.exe" code/06c_ph.R outputs_tam
suppressPackageStartupMessages({
  library(survival)
  library(splines)
})

args <- commandArgs(trailingOnly = TRUE)
cikti <- if (length(args) >= 1) args[1] else "outputs"
paylas <- file.path(cikti, "paylasilabilir")
veri <- read.csv(gzfile(file.path(cikti, "ozel", "06_atanmis_veri.csv.gz")))
maruziyet <- c("jh_4_5", "jh_6_8")
terimler <- setdiff(names(veri), c("atama", "stay_id", "subject_id", "ilk_yb_birimi", "anchor_year_group",
                                   "sure_saat", "olay_kod_yeni_by"))
terimler <- terimler[!startsWith(terimler, "yil_")]
TT <- c("braden_mobilite_disi_en_dusuk", "vazopresor", "sedatif_herhangi", "sofa_24s", "charlson_yassiz")
DONEM <- 96  # 72. saatten sonraki 96. saat = YB'deki 168. saat
STRATA_ADI <- "strata birim x anchor_year_group"

veri$olay <- as.integer(veri$olay_kod_yeni_by == 1)
veri$strata_by <- interaction(veri$ilk_yb_birimi, veri$anchor_year_group, drop = TRUE)
# Sayma sureci baslangic < bitis ve log(zaman) ister: 72. saatte olan olay (sure 0) 1 dakika sayilir
veri$sure_saat <- pmax(veri$sure_saat, 1 / 60)
atamalar <- split(veri, veri$atama)
m <- length(atamalar)
v1 <- atamalar[[1]]
gizle <- function(x) ifelse(x > 0 & x < 5, "<5", as.character(x))
hatalar <- list()
dene <- function(ad, ifade) invisible(tryCatch(ifade, error = function(e) {
  cat("  [HATA]", ad, ":", conditionMessage(e), "\n")
  hatalar[[ad]] <<- conditionMessage(e)
  NULL
}))
sabit_disi <- function(v, t) t[sapply(v[t], function(x) length(unique(x)) > 1)]
formul <- function(sol, t, ek = NULL) {
  as.formula(paste(sol, "~", paste(c(t, ek), collapse = " + "), "+ strata(strata_by)"))
}

# Rubin: q ve u atama basina adli katsayi ve (robust) varyans vektorleri; un kumelenmemis (naif) varyanslar.
# Tum atamalarda ortak terimler.
rubin_tek <- function(Q, U) {
  k <- nrow(Q)
  qbar <- colMeans(Q)
  W <- colMeans(U)
  B <- if (k > 1) apply(Q, 2, var) else rep(0, ncol(Q))
  se <- sqrt(W + (1 + 1 / k) * B)
  df <- ifelse(B > 0, (k - 1) * (1 + W / ((1 + 1 / k) * B))^2, 1e6)
  tq <- qt(0.975, df)
  list(q = qbar, se = se, alt = exp(qbar - tq * se), ust = exp(qbar + tq * se),
       p = 2 * pt(abs(qbar / se), df, lower.tail = FALSE))
}
rubin <- function(q, u, un) {
  ortak <- Reduce(intersect, lapply(q, names))
  Q <- do.call(rbind, lapply(q, function(x) x[ortak]))
  r <- rubin_tek(Q, do.call(rbind, lapply(u, function(x) x[ortak])))
  n <- rubin_tek(Q, do.call(rbind, lapply(un, function(x) x[ortak])))
  data.frame(terim = ortak, katsayi = r$q, se = r$se, etki = exp(r$q), alt_95 = r$alt, ust_95 = r$ust, p = r$p,
             se_naif = n$se, alt_95_naif = n$alt, ust_95_naif = n$ust, p_naif = n$p, row.names = NULL)
}
# Robust (vcov) ve naif varyans matrisleri, katsayi adlariyla
naif_var <- function(fit) {
  V <- fit$naive.var
  dimnames(V) <- list(names(coef(fit)), names(coef(fit)))
  V
}

# D2: atamalar arasi ki-kare istatistiklerinin birlestirilmesi (k serbestlik derecesi)
d2_p <- function(d, k) {
  d <- pmax(d, 0)
  n <- length(d)
  if (n < 2) return(pchisq(d, k, lower.tail = FALSE))
  r <- (1 + 1 / n) * var(sqrt(d))
  D <- (mean(d) / k - (n + 1) / (n - 1) * r) / (1 + r)
  if (D <= 0) return(1)
  df2 <- if (r > 0) k^(-3 / n) * (n - 1) * (1 + 1 / r)^2 else 1e6
  pf(D, k, df2, lower.tail = FALSE)
}

satir_06d <- function(sonuc, analiz_tipi, kod, analiz, model) {
  data.frame(analiz_tipi = analiz_tipi, analiz_kodu = kod, analiz = analiz, model = model, sonuc = "yeni_by",
             etki_olcusu = "HR", terim = sonuc$terim,
             maruziyet = ifelse(sonuc$terim %in% maruziyet, "True", "False"),  # Python ciktisiyla ayni yazim
             sonuc[, c("katsayi", "se", "etki", "alt_95", "ust_95", "p")],
             n = gizle(nrow(v1)), olay = gizle(sum(v1$olay)), atama_sayisi = m,
             sonuc[, c("se_naif", "alt_95_naif", "ust_95_naif", "p_naif")])
}
yeni_06d <- list()

# ---- 1. Birincil (strata birim x yil) ve cox.zph ----
dene("birincil_strata_birim_yil", {
  q <- u <- un <- zph <- list()
  for (i in seq_len(m)) {
    v <- atamalar[[i]]
    f <- formul("Surv(sure_saat, olay)", sabit_disi(v, terimler))
    fit <- coxph(f, data = v, cluster = subject_id)
    q[[i]] <- coef(fit)
    u[[i]] <- diag(vcov(fit))
    un[[i]] <- diag(naif_var(fit))
    zph[[i]] <- cox.zph(coxph(f, data = v), transform = "rank")$table
  }
  s <- rubin(q, u, un)
  yeni_06d$birincil <- satir_06d(s, "birincil", "birincil_strata_birim_yil",
                                 "Cause-specific Cox, MICE, strata birim x yil",
                                 paste("cause-specific Cox,", STRATA_ADI, "(yil terimi yok), robust SE (hasta kumesi)"))
  ortak <- Reduce(intersect, lapply(zph, rownames))
  ph <- data.frame(analiz_tipi = "birincil", model = paste("cause-specific Cox,", STRATA_ADI),
                   terim = ortak, chisq_ilk_atama = zph[[1]][ortak, "chisq"], df = zph[[1]][ortak, "df"],
                   p_ilk_atama = zph[[1]][ortak, "p"],
                   p_birlesik_d2 = sapply(ortak, function(t) d2_p(sapply(zph, function(z) z[t, "chisq"]),
                                                                  zph[[1]][t, "df"])),
                   atama_sayisi = m, row.names = NULL)
  write.csv(ph, file.path(paylas, "06e2_ph_varsayimi_coxzph.csv"), row.names = FALSE, fileEncoding = "UTF-8")
  print(s[s$terim %in% maruziyet, c("terim", "etki", "alt_95", "ust_95", "p")], row.names = FALSE)
  print(ph[, c("terim", "chisq_ilk_atama", "p_ilk_atama", "p_birlesik_d2")], row.names = FALSE)
})

# ---- 2. Donem bazinda HR (survSplit) ----
dene("j_donem_hr", {
  q <- u <- un <- list()
  for (i in seq_len(m)) {
    s <- survSplit(Surv(sure_saat, olay) ~ ., data = atamalar[[i]], cut = DONEM, episode = "donem")
    donem_t <- c()
    for (x in maruziyet) {
      s[[paste0(x, "_d1")]] <- s[[x]] * (s$donem == 1)
      s[[paste0(x, "_d2")]] <- s[[x]] * (s$donem == 2)
      donem_t <- c(donem_t, paste0(x, c("_d1", "_d2")))
    }
    fit <- coxph(formul("Surv(tstart, sure_saat, olay)",
                        sabit_disi(s, c(donem_t, setdiff(terimler, maruziyet)))), data = s, cluster = subject_id)
    b <- coef(fit)
    V <- vcov(fit)
    Vn <- naif_var(fit)
    e1 <- paste0(maruziyet, "_d1")
    e2 <- paste0(maruziyet, "_d2")
    var_ <- e1 %in% names(b) & e2 %in% names(b)  # sabit oldugu icin dusen donem terimi varsa etkilesim yok
    e1 <- e1[var_]
    e2 <- e2[var_]
    # Etkilesim: >168 saat log HR - 72-168 saat log HR
    q[[i]] <- c(b, setNames(b[e2] - b[e1], paste0(maruziyet[var_], "_etkilesim")))
    u[[i]] <- c(diag(V), setNames(diag(V)[e2] + diag(V)[e1] - 2 * V[cbind(e1, e2)],
                                  paste0(maruziyet[var_], "_etkilesim")))
    un[[i]] <- c(diag(Vn), setNames(diag(Vn)[e2] + diag(Vn)[e1] - 2 * Vn[cbind(e1, e2)],
                                    paste0(maruziyet[var_], "_etkilesim")))
  }
  r <- rubin(q, u, un)
  r <- r[grepl("^jh_.*_(d1|d2|etkilesim)$", r$terim), ]
  sonek <- sub("^jh_[0-9]_[0-9]_", "", r$terim)
  d1 <- v1$sure_saat <= DONEM
  sonuc <- data.frame(
    analiz_tipi = "duyarlilik", analiz_kodu = "j_donem_hr",
    model = paste("cause-specific Cox, survSplit 168. saatte,", STRATA_ADI, ", robust SE (hasta kumesi)"),
    etki_olcusu = "HR",
    terim = sub("_(d1|d2|etkilesim)$", "", r$terim),
    donem = c(d1 = "72-168 saat", d2 = ">168 saat", etkilesim = "etkilesim (>168 HR / 72-168 HR)")[sonek],
    r[, c("katsayi", "se", "etki", "alt_95", "ust_95", "p")],
    n = c(d1 = gizle(nrow(v1)), d2 = gizle(sum(!d1)), etkilesim = gizle(nrow(v1)))[sonek],
    olay = c(d1 = gizle(sum(v1$olay & d1)), d2 = gizle(sum(v1$olay & !d1)),
             etkilesim = gizle(sum(v1$olay)))[sonek],
    atama_sayisi = m, r[, c("se_naif", "alt_95_naif", "ust_95_naif", "p_naif")], row.names = NULL)
  sonuc <- sonuc[order(sonuc$terim, match(sonek, c("d1", "d2", "etkilesim"))), ]
  write.csv(sonuc, file.path(paylas, "06j_donem_hr.csv"), row.names = FALSE, fileEncoding = "UTF-8")
  print(sonuc[, c("terim", "donem", "etki", "alt_95", "ust_95", "p")], row.names = FALSE)
})

# ---- 3. tt: bes karistirici x log(zaman) ----
dene("i_tt_log_zaman", {
  q <- u <- un <- list()
  for (i in seq_len(m)) {
    v <- atamalar[[i]]
    t_i <- sabit_disi(v, terimler)
    fit <- coxph(formul("Surv(sure_saat, olay)", t_i, paste0("tt(", intersect(TT, t_i), ")")), data = v,
                 tt = function(x, t, ...) x * log(t), cluster = subject_id)
    q[[i]] <- coef(fit)[maruziyet]
    u[[i]] <- diag(vcov(fit))[maruziyet]
    un[[i]] <- diag(naif_var(fit))[maruziyet]
  }
  s <- rubin(q, u, un)
  yeni_06d$tt <- satir_06d(s, "duyarlilik", "i_tt_log_zaman",
                           "Bes karistirici x log(zaman) etkilesimi (tt), yalnizca JH-HLM HR",
                           paste("cause-specific Cox + tt(x * log(saat)):", paste(TT, collapse = ", "), ";",
                                 STRATA_ADI))
  print(s[, c("terim", "etki", "alt_95", "ust_95", "p")], row.names = FALSE)
})

# ---- 4. Schoenfeld grafigi (ilk atanmis set) ----
dene("schoenfeld_grafik", {
  fit <- coxph(formul("Surv(sure_saat, olay)", sabit_disi(v1, terimler)), data = v1)
  z <- cox.zph(fit, transform = "identity")
  ciz <- function() {
    par(mfrow = c(1, 2), mar = c(4.5, 4.5, 3, 1))
    for (x in maruziyet) {
      if (!x %in% colnames(z$y)) next
      zx <- z$x
      zy <- z$y[, x]
      izgara <- seq(quantile(zx, 0.05), quantile(zx, 0.95), length.out = 100)
      sp <- lm(zy ~ ns(zx, df = 4))
      tah <- predict(sp, newdata = data.frame(zx = izgara), se.fit = TRUE)
      alt <- tah$fit - 1.96 * tah$se.fit
      ust <- tah$fit + 1.96 * tah$se.fit
      saat <- izgara + 72
      plot(saat, tah$fit, type = "n", ylim = range(c(alt, ust, 0, coef(fit)[x])),
           xlab = "YB'deki saat", ylab = "beta(t) (log HR)", main = x)
      polygon(c(saat, rev(saat)), c(alt, rev(ust)), col = "grey85", border = NA)
      lines(saat, tah$fit, lwd = 2)
      abline(h = coef(fit)[x], lty = 2)
      abline(h = 0, lty = 3)
      abline(v = 168, col = "grey50", lty = 3)
    }
  }
  png(file.path(paylas, "06e3_schoenfeld_jhhlm.png"), width = 1800, height = 800, res = 150)
  ciz()
  invisible(dev.off())
  svg(file.path(paylas, "06e3_schoenfeld_jhhlm.svg"), width = 12, height = 5.3)
  ciz()
  invisible(dev.off())
})

# ---- 06d'ye ekle (ayni analiz_kodu satirlari once silinir; betik tekrar calisirsa cift olmasin) ----
d_yol <- file.path(paylas, "06d_modeller.csv")
md <- read.csv(d_yol, fileEncoding = "UTF-8-BOM", colClasses = "character", check.names = FALSE)
md <- md[!md$analiz_kodu %in% c("birincil_strata_birim_yil", "i_tt_log_zaman"), ]
for (y in yeni_06d) {
  y[] <- lapply(y, as.character)
  for (s in setdiff(names(md), names(y))) y[[s]] <- ""
  md <- rbind(md, y[names(md)])
}
baglanti <- file(d_yol, "wb")
writeBin(as.raw(c(0xef, 0xbb, 0xbf)), baglanti)  # Python ciktisiyla ayni: UTF-8 BOM
write.csv(md, baglanti, row.names = FALSE, na = "")
close(baglanti)

if (length(hatalar)) {
  z_yol <- file.path(paylas, "06z_hatalar.csv")
  hz <- read.csv(z_yol, fileEncoding = "UTF-8-BOM", colClasses = "character")
  hz <- rbind(hz, data.frame(analiz = paste0("R 06c: ", names(hatalar)), hata = unlist(hatalar)))
  write.csv(hz, z_yol, row.names = FALSE, fileEncoding = "UTF-8")
}
cat(length(hatalar), "analizde hata. Ciktilar:", paylas, "\n")
