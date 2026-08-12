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
- Tam mühit (Postgres ilə): `docker compose up`

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
- Yeni sahə (field) bir formaya əlavə edəndə onun backend sxemində (`app/schemas/`) və müvafiq bütün yaradılış yollarında (məs. həm `ReservationCreate`, həm `QuickBookingCreate`) mövcud olduğunu yoxla — bax "Bilinən məhdudiyyətlər".
- Rol yoxlaması UI-da düyməni gizlətməklə bitmir — hər endpoint-də serverdə də yoxlanmalıdır (`app/core/deps.py`-dəki asılılıqlar).

## Bilinən məhdudiyyətlər

- E-poçt bildirişləri yoxdur, tək valyuta dəstəyi var (`.env`-dəki `CURRENCY`).
- `.env`-dəki `SECRET_KEY` yalnız development üçündür, real yayımdan əvvəl dəyişdirilməlidir.
- `nightly_rate` override-i (`ReservationCreate`) rol səviyyəsində serverdə qorunmur — frontend bu sahəni yalnız menecerlərə göstərir, amma API-yə birbaşa müraciət edən istənilən `StaffUser` onu göndərə bilər. Hələ görünməyib, amma "role yoxlaması yalnız UI-da bitməməlidir" qaydasına bir istisnadır.

## Növbəti addım

- [ ] `nightly_rate` override-ə server-side rol yoxlaması əlavə et (`app/routers/api/reservations.py` — `create_reservation`/`create_walk_in`, hazırda `CurrentUser`, `ManagerUser` olmalıdır ya da servis daxilində manual yoxlama). Sahib özü yazacaq.

## Git / commit qaydası

- Push etməzdən əvvəl hər commit-ə **geniş və təfərrüatlı description** yaz: nə dəyişdi, niyə dəyişdi, hansı fayllara təsir etdi. Tək sətir "fix bug" kimi mesajlar kifayət etmir.
- Format: birinci sətir qısa xülasə, boş sətirdən sonra bullet-lərlə səbəb və detallar.
- Məqsəd: gələcəkdə tarixçəyə baxanda (Sahib və ya Claude) nəyin niyə edildiyini oxumaqla anlamaq, kod-a yenidən baxmadan.

## Düzəldilmiş bug-lar (tarixçə üçün)

- ~~Walk-in rezervasiyada menecer qiymət override-i işləmirdi~~ — `QuickBookingCreate`-ə `nightly_rate` əlavə edildi, `new_reservation.html`-də `common` obyektinə köçürüldü. Regressiya testi: `tests/test_reservations.py::test_walk_in_honours_a_nightly_rate_override`.
- ~~Otaqlar səhifəsi 100-dən çox rezervasiya olduqda hazırkı qonaqları itirə bilərdi~~ — `reservations` axtarışına `order=asc` seçimi əlavə edildi; `rooms.html` indi "occupied" (otaq sayı ilə məhdud) və "upcoming" (`date_from` + artan sıra ilə məhdud) üçün ayrı, təbii şəkildə məhdudlaşan sorğular göndərir.
- ~~Login-də `next` parametri açıq yönləndirmə riski daşıyırdı~~ — indi yalnız `/` ilə başlayan (və `//` ilə başlamayan) nisbi yollar qəbul edilir.
