# HotelManagementSystem

Otel qonaq qeydiyyatı və rezervasiya idarəetmə sistemi. FastAPI backend,
server-render edilən Jinja2 + Alpine.js + TailwindCSS frontend. Tədris/portfolio
layihəsidir — real otel istifadəçiləri yoxdur, PostgreSQL/SQLite üzərində işləyir.

## Əmrlər

- Server (dev): `.venv\Scripts\python.exe run.py` → http://127.0.0.1:8000, API docs `/api/docs`
- Testlər: `.venv\Scripts\python.exe -m pytest -v`
- Bir test faylı: `.venv\Scripts\python.exe -m pytest tests/test_reservations.py -v`
- Demo məlumat: `.venv\Scripts\python.exe seed.py` (`--reset` ilə sıfırdan qurur)
- Yeni migration: `.venv\Scripts\alembic.exe revision --autogenerate -m "..."`
- Migration tətbiq et: `.venv\Scripts\alembic.exe upgrade head`
- Tam mühit (Postgres ilə): əvvəlcə `export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")`, sonra `docker compose up` — compose `APP_ENV=production` ilə işlədiyi üçün açar olmadan qəsdən start etmir

## Arxitektura qaydası

Qat ardıcıllığı sabitdir: `routers/api` → `services` → `repositories` → SQLAlchemy model.

- Router heç vaxt birbaşa ORM sorğusu yazmır — yalnız uyğun `services/*Service` metodunu çağırır və rolu (`StaffUser`/`ManagerUser`/`AdminUser`) yoxlayır.
- Bütün SQL sorğuları `repositories/`-də yaşayır — başqa heç bir qatda yoxdur.
- Biznes qaydası (overbooking, qiymətləndirmə, VAT, lifecycle keçidləri) yalnız `services/`-də yaşayır, router və ya template-də təkrarlanmır.
- Yeni endpoint əlavə edəndə `app/routers/api/__init__.py`-də uyğun router-i qeydiyyatdan keçirməyi unutma (invoices/staff kimi alt-router-lər ayrıca fayl deyil, mövcud fayllar daxilində əlavə `APIRouter` obyektləridir — məs. `payments.invoices_router`, `auth.staff_router`).

## Konvensiyalar

- Yeni funksiyaya docstring/comment yazma — WHY aydın deyilsə bir sətir kifayətdir, nə etdiyini izah etmə.
- Yeni biznes qaydası əlavə edəndə mütləq `tests/`-ə uyğun test əlavə et (xüsusən overlap/overbooking, qiymətləndirmə, rol icazələri ilə bağlı hər şey).
- Frontend-də API çağırışı həmişə `app/static/js/app.js`-dəki `api()` helper-i ilə edilir, birbaşa `fetch()` yazılmır — 401 aşkarlanması və xəta formatı yalnız orada həll olunub.
- Yeni sahə (field) bir formaya əlavə edəndə onun backend sxemində (`app/schemas/`) və müvafiq bütün yaradılış yollarında (məs. həm `ReservationCreate`, həm `QuickBookingCreate`) mövcud olduğunu yoxla — `nightly_rate` məhz belə bir yoldan itmişdi, bax "Düzəldilmiş bug-lar".
- Rol yoxlaması UI-da düyməni gizlətməklə bitmir — hər endpoint-də serverdə də yoxlanmalıdır (`app/core/deps.py`-dəki asılılıqlar).

## Təhlükəsizlik qaydaları

Bunlar audit nəticəsində qoyulub; pozulsa, testlər qırılır (`tests/test_security.py`).

- **Pul və qiymət sahələri servis qatında yoxlanılır, router-də yox.** `nightly_rate` üç ayrı endpoint-dən gəlir (`create`, `walk-in`, `PATCH`), ona görə icazə yoxlaması `ReservationService._assert_may_set_rate`-dədir — hər üçü oradan keçir. Yeni "yalnız menecer" sahəsi əlavə edəndə eyni nümunəni izlə.
- **Sxemdə `dict` tipli sahə yazma.** Konkret pydantic modeli istifadə et. `QuickBookingCreate.guest` `dict` idi və səhv giriş 422 əvəzinə 500 qaytarırdı.
- **Token `pwf` claim-i daşıyır** — istifadəçinin parol hash-inin barmaq izi (`app/core/security.py`). Hər sorğuda yoxlanılır, ona görə parol dəyişdikdə bütün köhnə sessiyalar dərhal ölür. Token-ə yeni claim əlavə edəndə bunu silmə.
- **Yeni autentifikasiya endpoint-inə rate limit qoy** (`@limiter.limit(...)` — `app/core/ratelimit.py`). Dekorator işləməsi üçün funksiyada `request: Request` parametri **olmalıdır**, əks halda səssizcə heç nə etmir.
- **Yeni təhlükəsizlik parametri əlavə edəndə** `config.py::_refuse_unsafe_production`-a da yoxlama əlavə et — production dev default-ları ilə start etməməlidir.
- **Admin sayı**: son aktiv admini deaktiv etmək və ya rolunu aşağı salmaq `AuthService`-də bağlıdır. `deactivate()` və `update_user()` — hər ikisi eyni vəziyyətə apara bilir, ona görə qoruma hər ikisindədir.

## Bilinən məhdudiyyətlər

Açıq qalan təhlükəsizlik işləri və yayımdan əvvəlki checklist ayrıca fayldadır:
**`SECURITY-TODO.md`**. Aşağıdakılar isə bilərəkdən qəbul edilmiş məhdudiyyətlərdir.

- E-poçt bildirişləri yoxdur, tək valyuta dəstəyi var (`.env`-dəki `CURRENCY`).
- CSP hələ `unsafe-inline`/`unsafe-eval` saxlayır, çünki Tailwind/Alpine/Chart.js CDN-dən gəlir və Tailwind brauzerdə kompilyasiya edir. Bu üç faylı layihəyə köçürmək (vendor) CSP-ni tam sərtləşdirməyə imkan verər.
- Rate limit IP əsaslıdır və yaddaşdadır: proxy arxasında real client IP ötürülməlidir, birdən çox instansiyada isə Redis kimi paylaşılan storage lazımdır.
- Audit log yoxdur — rezervasiyanı kimin dəyişdiyi (`created_by_id`-dən başqa) saxlanmır.
- İki faktorlu autentifikasiya yoxdur.

## Git / commit qaydası

- Push etməzdən əvvəl hər commit-ə **geniş və təfərrüatlı description** yaz: nə dəyişdi, niyə dəyişdi, hansı fayllara təsir etdi. Tək sətir "fix bug" kimi mesajlar kifayət etmir.
- Format: birinci sətir qısa xülasə, boş sətirdən sonra bullet-lərlə səbəb və detallar.
- Məqsəd: gələcəkdə tarixçəyə baxanda (Sahib və ya Claude) nəyin niyə edildiyini oxumaqla anlamaq, kod-a yenidən baxmadan.

## Düzəldilmiş bug-lar (tarixçə üçün)

- ~~Walk-in rezervasiyada menecer qiymət override-i işləmirdi~~ — `QuickBookingCreate`-ə `nightly_rate` əlavə edildi, `new_reservation.html`-də `common` obyektinə köçürüldü. Regressiya testi: `tests/test_reservations.py::test_walk_in_honours_a_nightly_rate_override`.
- ~~Otaqlar səhifəsi 100-dən çox rezervasiya olduqda hazırkı qonaqları itirə bilərdi~~ — `reservations` axtarışına `order=asc` seçimi əlavə edildi; `rooms.html` indi "occupied" (otaq sayı ilə məhdud) və "upcoming" (`date_from` + artan sıra ilə məhdud) üçün ayrı, təbii şəkildə məhdudlaşan sorğular göndərir.
- ~~Login-də `next` parametri açıq yönləndirmə riski daşıyırdı~~ — indi yalnız `/` ilə başlayan (və `//` ilə başlamayan) nisbi yollar qəbul edilir.

### Təhlükəsizlik auditi (2026-08)

- ~~Login endpoint-i brute-force-a tam açıq idi~~ — `slowapi` quraşdırılmışdı, `app.state.limiter` təyin edilmişdi, amma heç bir endpoint-də `@limiter.limit` yox idi və `default_limits=[]` idi, yəni nəzarət tamamilə ölü idi. İndi `/auth/login` 10/dəq, `/auth/change-password` 5/dəq (`app/core/ratelimit.py`).
- ~~Resepsiyonist `nightly_rate` göndərərək istənilən qiymətə rezervasiya aça bilirdi~~ — üç endpoint-də də (`create`, `walk-in`, `PATCH`) icazə yoxlanılmırdı; `PATCH` yolu əvvəllər sənədləşdirilməmişdi. İndi `ReservationService._assert_may_set_rate` hamısını əhatə edir.
- ~~`PATCH /staff/{id}` son admini deaktiv edə və ya rolunu aşağı sala bilirdi~~ — `deactivate()`-də qoruma var idi, amma PATCH eyni vəziyyətə `role`/`is_active` sahələri ilə yan yoldan çatırdı və sistemi adminsiz qoya bilirdi.
- ~~Parol dəyişmək köhnə sessiyaları ləğv etmirdi~~ — oğurlanmış token 12 saat işləməyə davam edirdi. İndi token parol hash-inin barmaq izini (`pwf`) daşıyır və hər sorğuda yoxlanılır; parol dəyişən istifadəçinin öz sessiyası avtomatik yenilənir.
- ~~Naməlum e-poçtla login bcrypt-i tamamilə atlayırdı~~ — cavab müddəti hansı ünvanların qeydiyyatda olduğunu açırdı, halbuki mesaj qəsdən eyni idi. İndi hər iki yol bir bcrypt raundu ödəyir (`waste_password_time`).
- ~~Production dev default-ları ilə start edirdi~~ — placeholder `SECRET_KEY` sessiya imzalaya bilirdi. İndi `config.py::_refuse_unsafe_production` boot-da imtina edir (default/qısa açar, `DEBUG=true`, `CORS_ORIGINS=*`).
- ~~`/api/docs` və OpenAPI sxemi production-da açıq idi~~ — indi yalnız development-də açılır.
- ~~`QuickBookingCreate.guest` tipsiz `dict` idi~~ — qonaq validasiyası tam atlanırdı və səhv giriş 500 qaytarırdı; indi `GuestCreate`.
- ~~Cavablarda CSP, HSTS və `Cache-Control` yox idi~~ — qonaq PII-si (pasport, telefon, ünvan) brauzer keşində qala bilirdi. İndi bütün qeyri-static cavablar `no-store`.
- ~~`/health` `APP_ENV`-i açırdı~~ — indi yalnız `{"status": "ok"}`.
- ~~Parol siyasəti 8 simvol idi, sinif tələbi yox idi~~ — indi 10 simvol + böyük/kiçik hərf + rəqəm, və yeni parol köhnəsindən fərqli olmalıdır.
- ~~`python-jose 3.3.0`~~ — CVE-2024-33663 və CVE-2024-33664; 3.4.0-a yüksəldildi.
