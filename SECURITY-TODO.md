# Təhlükəsizlik — görüləcək addımlar

2026-08 auditindən sonra qalan işlər. Auditdə tapılan 11 boşluq artıq
bağlanıb (commit `89b3dcb`, tarixçə CLAUDE.md-dədir) — bu fayl **hələ
edilməmiş** addımları saxlayır.

Bir bənd bitəndə onu buradan sil və CLAUDE.md-dəki "Düzəldilmiş bug-lar"
bölməsinə keçir.

---

## 1. Yayımdan (deploy) əvvəl mütləq

Kod dəyişikliyi tələb etmir — konfiqurasiya və mühit məsələləridir.
`APP_ENV=production` bunlardan bir neçəsini boot-da özü yoxlayır, qalanları
səssizcə keçir, ona görə siyahını əl ilə keç.

- [ ] **`SECRET_KEY` generasiya et.** `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
      Production default açarla start etmir, amma açar bir dəfə sızarsa
      hər kəsin sessiyasını saxtalaşdırmaq olar — açarı dəyişmək bütün
      mövcud sessiyaları da ləğv edir.
- [ ] **`CORS_ORIGINS`-i real domenə qoy.** Cookie kredensiallı olduğu üçün
      `*` boot-da rədd edilir, amma səhv domen yazmaq rədd edilmir.
- [ ] **`TRUSTED_HOSTS`-u real hostname-lərə qoy.** Hazırda default `*`-dır və
      bu halda Host başlığı yoxlaması ümumiyyətlə söndürülür.
- [ ] **HTTPS arxasında işlət.** Sessiya cookie-si `secure` bayrağını və HSTS
      başlığını yalnız `APP_ENV=production`-da alır; HTTP üzərindən yayımlasan
      cookie açıq şəkildə gedəcək.
- [ ] **Proxy arxasındasa real client IP-ni ötür.** Uvicorn-u `--proxy-headers
      --forwarded-allow-ips=<proxy-ip>` ilə işlət. Bu edilməzsə rate limit
      bütün istifadəçiləri **bir IP** kimi görəcək: həm brute-force qorumasını
      faydasız edir, həm də bir nəfərin səhv parolu bütün oteli bloklayır.
- [ ] **`alembic upgrade head`.** `create_all` yalnız development-də işə düşür.
- [ ] **`seed.py`-ni production bazasına qarşı işlətmə.** İçində sabit demo
      parolları var (`Admin1234`, `Manager1234`, `Reception1234`) və onlar
      modelə birbaşa yazıldığı üçün yeni parol siyasətindən yan keçir —
      API vasitəsilə belə parol artıq yaradıla bilməz.

---

## 2. Kod dəyişikliyi tələb edən (prioritetlə)

### 2.1 Invoice PDF qonaq adından qırılır — *təsdiqlənib*

**Problem.** `app/services/invoice_service.py:140` qonaq adını, telefonunu və
e-poçtunu birbaşa reportlab `Paragraph`-a verir. `Paragraph` mətnə mini-XML
markup kimi baxır, ona görə tərkibində bağlanmamış teq olan ad parse
xətası ilə 500 qaytarır:

```
'<b>Bold Guest'  ->  ValueError: paragraph text '<para><b>Bold Guest<br/>+994</para>' caused exception
```

`&` və tək `<` simvolları problem yaratmır — yalnız teqə oxşayan konstruksiya.

**Niyə vacibdir.** Səviyyəsi aşağıdır (adı personal daxil edir, kənar
istifadəçi deyil), amma effekt davamlıdır: belə bir ad bir dəfə bazaya
düşəndə həmin qonağın invoice-u **daimi olaraq** çıxarıla bilmir və səbəbi
loga baxmadan aydın olmur.

**Həlli.** PDF-ə gedən bütün istifadəçi mətnini escape et:

```python
from xml.sax.saxutils import escape
Paragraph(f"{escape(reservation.guest.full_name)}<br/>...", value)
```

Eyni şey `folio.lines`-dakı `line.label`/`line.detail` üçün də keçərlidir —
onlar otaq nömrəsi və otaq tipi adından qurulur.

**Test.** `tests/test_security.py`-a: adında `<b>` olan qonaq yarat, invoice
PDF-i endir, 200 gözlə.

### 2.2 CSP-dən `unsafe-inline` və `unsafe-eval`-i çıxar

**Problem.** `app/main.py`-dakı CSP hər ikisini saxlayır, çünki Tailwind,
Alpine.js və Chart.js CDN-dən yüklənir və Tailwind-in brauzer versiyası
stilləri runtime-da kompilyasiya edir (`eval` tələb edir). Bu iki güzəşt
CSP-nin XSS-ə qarşı dəyərinin böyük hissəsini yeyir.

**Həlli.** Hər üç kitabxananı `app/static/vendor/`-a köçür (Tailwind üçün
build mərhələsi lazımdır — CDN versiyası deyil, CLI ilə əvvəlcədən
kompilyasiya edilmiş CSS). Sonra:

- `script-src 'self'` (CDN domenlərini sil)
- `style-src 'self'` — inline `style=` atributları qalırsa əvvəlcə onları təmizlə
- Alpine `x-data` kimi atributlar CSP-yə toxunmur, amma Alpine-in özü
  ifadələri qiymətləndirmək üçün `unsafe-eval` istəyir — Alpine-in
  **CSP build**-ini (`@alpinejs/csp`) istifadə et, yoxsa bu bənd yarımçıq qalır.

**Qeyd.** Bu, əlaqəli bir problemi də həll edir: hazırda üç kənar CDN
kompromis olunsa, otelin bütün sessiyaları oğurlana bilər. Vendorlamaq bu
asılılığı tamamilə aradan qaldırır.

### 2.3 Rate limit-i paylaşılan storage-a keçir

**Problem.** `app/core/ratelimit.py` limiter-i yaddaşda (`MemoryStorage`)
sayır. Bir instansiyada işləyir; iki və daha çox uvicorn worker-i və ya
konteyner olan kimi hər biri öz sayğacını saxlayır və effektiv limit
worker sayına vurulur.

**Həlli.** `Limiter(storage_uri="redis://...")`. `slowapi` bunu birbaşa
dəstəkləyir, `.env`-ə `RATE_LIMIT_STORAGE_URI` əlavə et və default olaraq
yaddaşı saxla ki, development quraşdırma tələb etməsin.

### 2.4 Uğursuz login-ləri hesab üzrə də say

**Problem.** Hazırda limit yalnız IP üzrədir. Bot şəbəkəsi (hər IP-dən
10 cəhd) bir hesaba qarşı yavaş brute-force apara bilir.

**Həlli.** IP limitinə əlavə olaraq e-poçt üzrə sayğac: məsələn ardıcıl 10
uğursuz cəhddən sonra hesabı 15 dəqiqə kilidlə. Diqqət — kilid mesajı
mövcud olmayan hesab üçün də eyni görünməlidir, əks halda audit-də
bağladığımız hesab-sayımı sızması geri qayıdır.

### 2.5 Axtarışda LIKE joker simvolları

**Problem.** `app/repositories/reservation_repo.py:64` və qonaq axtarışı
istifadəçi mətnini birbaşa `LIKE` şablonuna qoyur. `%` yazan istifadəçi
bütün sətirləri çəkir. SQL injection **deyil** (sorğu parametrlidir), sadəcə
gözlənilməz nəticə və böyük bazada yavaşlama.

**Həlli.** Şablonu qurmazdan əvvəl `%`, `_` və `\` simvollarını escape et və
`.like(pattern, escape="\\")` istifadə et.

---

## 3. Uzunmüddətli

- **Audit log.** Hazırda yalnız `Reservation.created_by_id` saxlanır. Kim
  qiyməti dəyişdi, kim rezervasiyanı ləğv etdi, kim ödənişi geri qaytardı —
  heç biri izlənmir. Pul toxunan sistemdə bu, mübahisə yarananda yeganə
  arqumentdir. Ayrıca `audit_log` cədvəli: aktor, əməliyyat, obyekt, əvvəl/sonra, vaxt.
- **İki faktorlu autentifikasiya.** Ən azı admin və menecer rolları üçün (TOTP).
- **`passlib` əvəzlənməsi.** `passlib` 1.7.4 artıq aktiv saxlanılmır və
  `bcrypt==4.0.1`-ə bağlı qalmağımızın səbəbi budur (4.1+ ilə sınır).
  Alternativ: birbaşa `bcrypt` kitabxanası və ya `argon2-cffi`.
- **Asılılıq skanı CI-da.** `pip-audit` və ya Dependabot — `python-jose`
  CVE-ləri auditə qədər gözlədi, halbuki avtomatik tutula bilərdi.
