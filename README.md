# FranchiseHub Backend API Guide

Bu dokuman backend + frontend ekiplerinin ayni kontratla ilerlemesi icin hazirlandi.
Sistem rol bazli calisir: `buyer`, `franchise_owner`, `admin`.

## 1) Hızli Ozet

- Auth JWT Bearer token ile yapilir.
- Login sonrasi tum korumali endpointlerde `Authorization: Bearer <token>` zorunludur.
- Marka listeleme ve basvuru akisi `buyer` icindir.
- Basvuru yonetimi, mesajlasma, envanter, tedarik `franchise_owner` icindir.
- Moderasyon ve override islemleri `admin` icindir.

## 2) Base URL ve Dokuman

- Local base URL: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Health check: `GET /health`

## 3) Roller ve Zorunlu Kayit Alanlari

### Buyer register (`POST /auth/register/buyer`)
Zorunlu alanlar:
- `first_name`
- `last_name`
- `email`
- `phone`
- `city`
- `investment_budget`
- `experience_years`
- `preferred_sector`
- `password`

Opsiyonel:
- `identity_number` (unique)

### Franchise owner register (`POST /auth/register/franchise-owner`)
Zorunlu alanlar:
- `company_name`
- `tax_number`
- `email`
- `phone`
- `authorized_person_name`
- `country`
- `city`
- `company_address`
- `password`

Opsiyonel:
- `website`
- `verification_status` (default: `false`)

### Admin register (`POST /auth/register/admin`)
Zorunlu alanlar:
- `full_name`
- `email`
- `phone`
- `authorization_level`
- `password`

Opsiyonel:
- `is_superadmin` (default: `false`)

## 4) Auth Akisi (Frontend icin kritik)

### Login
`POST /auth/login`

Request:
```json
{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

Response:
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

Token icindeki alanlar:
- `subject_id`
- `role` (`buyer` | `franchise_owner` | `admin`)
- `sub` (`role:id`)

Frontend tarafinda onerilen:
- Token localStorage ya da secure cookie'de saklanir.
- `role` claim decode edilip route guard icin kullanilir.
- `401` => logout + login sayfasina donus.
- `403` => yetki yok ekrani.

## 5) Endpoint Kontratlari

## 5.1 Buyer endpointleri

### Marka listeleme
`GET /brands?sector=&min_cost=&max_cost=&location=`

Not:
- Sadece `is_approved=true` markalar doner.

### Marka detay
`GET /brands/{brand_id}`

### Marka karsilastirma
`POST /brands/compare`

Request:
```json
{
  "brand_ids": [1, 2]
}
```

### Basvuru olusturma
`POST /applications`

Request:
```json
{
  "brand_id": 1,
  "notes": "Istanbul Avrupa yakasi icin planliyorum."
}
```

## 5.2 Franchise owner endpointleri

### Kendi markama gelen basvurular
`GET /applications/my-brand`

### Basvuru durumu guncelle
`PATCH /applications/{application_id}`

Request:
```json
{
  "status": "approved",
  "notes": "On gorusme uygun."
}
```

`status` sadece `approved` veya `rejected`.

### Mesaj gonder
`POST /messages`

Request:
```json
{
  "application_id": 1,
  "content": "Merhaba, gorusme icin musait misiniz?"
}
```

### Mesajlari listele
`GET /messages/{application_id}`

## 5.3 Inventory + Supply endpointleri (franchise_owner)

- `GET /inventory`
- `POST /inventory`
- `PATCH /inventory/{inventory_id}`
- `DELETE /inventory/{inventory_id}`
- `POST /supply-requests/bulk`
- `GET /supply-requests/pool`

`POST /supply-requests/bulk` request:
```json
{
  "requests": [
    { "product_name": "Bardak", "quantity": 100 },
    { "product_name": "Kahve cekirdegi", "quantity": 30 }
  ]
}
```

## 5.4 Admin endpointleri

### Tum kullanicilari listele
`GET /admin/users`

### Marka onayla / onayi kaldir
`PATCH /admin/brands/{brand_id}/approve`

Request:
```json
{
  "is_approved": true
}
```

### Basvuru override
`PATCH /admin/applications/{application_id}/override`

Request:
```json
{
  "status": "rejected",
  "notes": "Politika geregi manuel kapatma."
}
```

## 6) Frontend Durum Kodlari Rehberi

- `200/201`: basarili islem
- `204`: basarili ama body yok (delete)
- `400`: is kurali ihlali (ornek: onaysiz markaya basvuru)
- `401`: token gecersiz/eksik
- `403`: rol yetkisi yok
- `404`: kayit bulunamadi
- `422`: form/alan validasyon hatasi

## 7) DB ve Teknik Mimari Ozet

Kimlik tablolari:
- `buyers`
- `franchise_owners`
- `admins`

Is tablolari:
- `brands` (`franchise_owner_id`, `is_approved`)
- `applications` (`buyer_id`, `brand_id`, `status`)
- `messages` (`application_id`, `sender_role`, `sender_id`)
- `inventories` (`franchise_owner_id`)
- `supply_requests` (`franchise_owner_id`, `status`)

## 8) Kurulum

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 9) Ortam Degiskenleri

```env
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
SECRET_KEY=strong-random-secret
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

## 10) Breaking Migration Notu

Bu surum eski `users` tablosundan ayrik role tablolarina gectigi icin kiricidir.

Migration dosyasi:
- `migrations/20260508_breaking_role_split.sql`

Calistirma:
```bash
psql "postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require" -f migrations/20260508_breaking_role_split.sql
```

Uretimde once backup alin.
