# FranchiseHub Frontend Contract

Bu dosya frontend ekibi icin net API kontratidir.

## Base

- Base URL: `http://127.0.0.1:8000`
- Auth: `Authorization: Bearer <access_token>`

## Auth

### Buyer Register
`POST /auth/register/buyer`

Request:
```json
{
  "email": "buyer1@franchisehub.local",
  "first_name": "Ayse",
  "last_name": "Demir",
  "phone": "+905550001111",
  "city": "Istanbul",
  "investment_budget": 3500000,
  "experience_years": 3,
  "preferred_sector": "Kafe",
  "identity_number": "TR12345678901",
  "password": "Buyer12345!"
}
```

### Franchise Owner Register
`POST /auth/register/franchise-owner`

Request:
```json
{
  "email": "owner1@franchisehub.local",
  "company_name": "Demo Franchise A.S.",
  "tax_number": "TAX-2026-001",
  "phone": "+905550002222",
  "authorized_person_name": "Mehmet Kaya",
  "country": "Turkiye",
  "city": "Istanbul",
  "company_address": "Maslak, Istanbul",
  "website": "https://demo-franchise.local",
  "verification_status": true,
  "password": "Owner12345!"
}
```

### Admin Register
`POST /auth/register/admin`

Request:
```json
{
  "email": "admin1@franchisehub.local",
  "full_name": "Platform Admin",
  "phone": "+905550003333",
  "authorization_level": "supervisor",
  "is_superadmin": true,
  "password": "Admin12345!"
}
```

### Login
`POST /auth/login`

Request:
```json
{
  "email": "buyer1@franchisehub.local",
  "password": "Buyer12345!"
}
```

Response:
```json
{
  "access_token": "<jwt>",
  "refresh_token": "<opaque>",
  "token_type": "bearer"
}
```

### Forgot / reset password
- `POST /auth/forgot-password` — body: `{ "email": "..." }`. Her zaman ayni mesaj; gelistirmede `EXPOSE_AUTH_TOKENS_IN_RESPONSE=true` ise cevapta `reset_token` doner (uretimde e-posta servisi kullanin).
- `POST /auth/reset-password` — body: `{ "token": "...", "new_password": "..." }`

### E-posta dogrulama
- Kayitta 6 haneli kod uretilir (sunucu logunda; SMTP yok).
- `POST /auth/verify-email` — body: `{ "email": "...", "code": "123456" }`

### Token yenileme ve profil
- `POST /auth/refresh` — body: `{ "refresh_token": "..." }` → yeni access + refresh
- `GET /auth/me` — Bearer zorunlu; rol bazli profil (`buyer` / `franchise_owner` / `admin` alt objesi)
- `PATCH /auth/me` — rolune uygun alanlar (ornek buyer: `first_name`, `phone`, ...)
- `POST /auth/change-password` — body: `{ "current_password": "...", "new_password": "..." }`

## Marka discovery (public — auth gerekmez)

- `GET /brands` — filtre: `sector`, `min_cost`, `max_cost`, `location`, `q`, `page`, `page_size`, `sort` (`name_asc` | `name_desc` | `cost_asc` | `cost_desc`)
- `GET /brands/{brand_id}`
- `POST /brands/compare` — cevapta `brands` + `comparison_table` (normalize satirlar)
- `GET /brands/{brand_id}/media` — `{ "logo": {...}, "gallery": [...] }`
- `GET /brands/{brand_id}/fdd` — FDD metadata listesi
- `GET /brands/{brand_id}/fdd/{fdd_id}/download` — `{ "download_url", "expires_at", "expires_in_seconds" }`
- `GET /brands/{brand_id}/territories` — musait / rezerve bolgeler + sayaclar
- `GET /files/media/{media_id}` — gorsel dosya
- `GET /files/fdd/download?token=...` — PDF indirme (signed token)

### Franchise owner medya

`POST /franchise-owner/brand/media` — `multipart/form-data`: `file`, `media_type` (`logo` | `gallery`), opsiyonel `sort_order`. Bearer + rol `franchise_owner`.

## Buyer — favoriler ve deneyim (Bearer, rol `buyer`)

- `GET /buyer/favorites` — `{ "brand_ids": [1, 2] }`
- `POST /buyer/favorites/{brand_id}` — favori ekle
- `DELETE /buyer/favorites/{brand_id}` — favori kaldir (204)
- `GET /buyer/applications` — tum basvurular + marka ozeti + durum
- `GET /buyer/applications/{id}` — tek basvuru + tam marka profili
- `GET /buyer/dashboard/summary` — favori sayisi, bekleyen/onayli/reddedilen basvurular
- `POST /buyer/qualification` — body: `investment_budget`, `preferred_sector`, `experience_years`, opsiyonel `city` → kural tabanli onerilen markalar (`match_score`, `match_reasons`)

## Basvurular ve mesajlasma

### Basvurular
- `POST /applications` — buyer basvuru olusturur
- `GET /applications/mine` — buyer tum basvurulari (`unread_count` dahil)
- `GET /applications/my-brand` — franchise owner markasina gelen basvurular
- `PATCH /applications/{id}` — franchise owner onay / red
- `GET /applications/{id}` — detay (buyer | franchise_owner | admin; rol bazli alanlar)

### Mesajlar
- `GET /conversations` — inbox (onayli basvurular, son mesaj, okunmamis sayisi)
- `GET /messages/{application_id}` — mesaj listesi (`is_read`, `read_at`)
- `POST /messages` — mesaj gonder (onayli basvuru)
- `PATCH /messages/{id}/read` — okundu isaretle

## Buyer Endpoints

- `POST /applications` (Bearer, rol `buyer`) — `/applications/mine` ile ayni akis

`POST /brands/compare` request:
```json
{ "brand_ids": [1, 2] }
```

`POST /applications` request:
```json
{
  "brand_id": 1,
  "notes": "Ankara icin franchise dusunuyorum."
}
```

## Franchise Owner Panel (tum ekranlar)

Header: `Authorization: Bearer <token>` (rol: `franchise_owner`).

### Next.js proxy

Ornek: istemci `GET /api/proxy/applications/my-brand` cagiriyorsa, proxy sunucu tarafinda **FastAPI** adresine yonlendirmeli:

- Hedef: `http://127.0.0.1:8000/applications/my-brand`
- Ayni HTTP metodu, `Authorization` header oldugu gibi iletilmeli.
- 404 aliyorsaniz: proxy route dosyasi yok veya yanlis path; backend bu yolu sunar.

### Ozet (dashboard kartlari)

`GET /franchise-owner/dashboard/summary`

Ornek cevap:

```json
{
  "has_brand": true,
  "brand_id": 1,
  "brand_name": "Demo Kahve Franchise",
  "applications_pending": 2,
  "applications_approved": 1,
  "applications_rejected": 0,
  "applications_total": 3,
  "inventory_item_count": 5,
  "supply_requests_pending": 2,
  "supply_requests_total": 4
}
```

Marka yoksa `has_brand: false`, sayilar 0 (404 degil).

### Marka bilgisi

`GET /franchise-owner/my-brand` — marka yoksa `null`.

### Marka olusturma / guncelleme

`POST /franchise-owner/brand` — ilk marka (name zorunlu; maliyet icin `initial_cost` **veya** `min_investment_cost` / `max_investment_cost`).

`PATCH /franchise-owner/brand` — mevcut markayi gunceller; gonderilmeyen alanlar degismez.

### Subeler, dokumanlar, analitik (franchise_owner)

- `GET|POST /franchise-owner/outlets` — sube listesi / ekle
- `PATCH|DELETE /franchise-owner/outlets/{id}`
- `GET /franchise-owner/documents` — egitim / SOP dosyalari (`?document_type=training|sop|other`)
- `POST /franchise-owner/documents` — multipart: `file`, `title`, `document_type`
- `GET /files/owner-documents/{id}` — indirme (Bearer, sahip owner)
- `GET /franchise-owner/analytics?days=30` — basvuru + envanter zaman serisi

Ornek body (Next.js ile uyumlu):

```json
{
  "name": "Demo Kahve",
  "sector": "Kafe",
  "location": "Istanbul",
  "min_investment_cost": 2000000,
  "max_investment_cost": 3000000,
  "description": "Opsiyonel",
  "support_details": "Opsiyonel"
}
```

Cevaptaki marka nesnesi: `initial_cost` + `min_investment_cost` / `max_investment_cost` (simdilik `initial_cost` ile ayni degerler).

### Basvurular

- `GET /applications/my-brand` — cevap: `{ "items": [ Application, ... ] }`; marka yoksa `items: []`.
- `PATCH /applications/{application_id}` — sadece `approved` / `rejected`.

`PATCH /applications/{application_id}` body:
```json
{
  "status": "approved",
  "notes": "Ilk gorusme olumlu."
}
```

### Mesajlar

- `POST /messages`
- `GET /messages/{application_id}`

`Message` cevabi: `created_at`, `is_from_buyer` (buyer gonderdiyse true), `sender_role`, `sender_id`.

`POST /messages` request:
```json
{
  "application_id": 1,
  "content": "Merhaba, sureci baslatalim."
}
```

## Inventory ve Supply

- `GET /inventory` — cevap `{ "items": [ ... ] }` (`outlet_id`, `low_stock_threshold`, `is_low_stock`)
- `POST /inventory` — opsiyonel `outlet_id`, `low_stock_threshold`
- `PATCH /inventory/{inventory_id}`
- `DELETE /inventory/{inventory_id}`
- `POST /inventory/transfer` — subeler arasi: `inventory_id`, `from_outlet_id`, `to_outlet_id`, `quantity`
- `GET /inventory/low-stock` — esik alti uyari listesi
- `GET /supply-requests` — `{ "items": [ ... ] }`
- `GET /supply-requests/{id}` — detay
- `PATCH /supply-requests/{id}` — `status`: `approved` | `rejected` | `shipped` (kargoda)
- `POST /supply-requests/bulk`
- `GET /supply-requests/pool`

`POST /supply-requests/bulk` request:
```json
{
  "requests": [
    { "product_name": "Karton Bardak", "quantity": 1000 },
    { "product_name": "Kahve Cekirdegi", "quantity": 80 }
  ]
}
```

## Admin Endpoints (Bearer, rol `admin`)

### Kullanicilar ve KPI
- `GET /admin/users` — normalize liste: `items`, `total`, rol sayaclari
- `PATCH /admin/users/{id}` — body: `role` + `is_active` (+ admin icin `authorization_level`, `is_superadmin`)
- `GET /admin/dashboard/summary` — KPI: kullanici, marka, basvuru sayilari

### Basvuru ve markalar
- `GET /admin/applications` — tum basvurular (buyer/marka bilgisi ile)
- `GET /admin/brands` — `?pending_only=true` veya `?is_approved=false`
- `PATCH /admin/brands/{brand_id}/approve`
- `PATCH /admin/applications/{application_id}/override`

### Denetim ve rapor
- `GET /admin/audit-logs` — `?limit=&offset=&action=&resource_type=`
- `GET /admin/reports/export` — `?format=csv` veya `excel` (CSV icerik, Excel uyumlu MIME)

### Sektor sozlugu (CRUD)
- `GET /admin/sectors` — `?active_only=true`
- `POST /admin/sectors` — `{ "name": "Kafe", "slug": "kafe", "is_active": true }`
- `GET /admin/sectors/{id}`
- `PATCH /admin/sectors/{id}`
- `DELETE /admin/sectors/{id}`

`PATCH /admin/brands/{brand_id}/approve` request:
```json
{
  "is_approved": true
}
```

`PATCH /admin/applications/{application_id}/override` request:
```json
{
  "status": "rejected",
  "notes": "Manual quality check."
}
```

## Dosya ve arama

### Genel upload (Bearer — tum roller)
- `POST /files/upload` — multipart `file`; cevap: `file_id`, `url`, `mime_type`
- `GET /files/uploads/{file_id}` — indirme (yukleyen veya admin)

Desteklenen tipler: gorsel (jpeg/png/webp/gif), pdf, doc/docx, plain text.

### Platform arama (sadece admin)
- `GET /search?q=demo&limit=20` — marka, basvuru, kullanici sonuclari

```json
{
  "query": "demo",
  "brands": [{ "id": 1, "name": "...", "is_approved": true }],
  "applications": [{ "id": 1, "status": "pending", "buyer_email": "..." }],
  "users": [{ "id": 1, "role": "buyer", "email": "...", "display_name": "..." }]
}
```

## Bildirimler (web + mobil, Bearer — tum roller)

- `GET /notifications` — `?page=1&page_size=20&unread_only=false`; cevap: `items`, `unread_count`, sayfalama
- `PATCH /notifications/{id}/read`
- `POST /notifications/read-all` — `{ "updated_count": N }`
- `POST /devices` — FCM/APNs token: `{ "token": "...", "platform": "ios" | "android" | "web" }`
- `DELETE /devices/{token}` — token URL-encode edilmeli (uzun tokenlar icin)

Ornek bildirim:
```json
{
  "id": 1,
  "title": "Basvuru onaylandi",
  "body": "Demo Kahve Franchise basvurunuz onaylandi.",
  "notification_type": "application",
  "action_url": "/buyer/applications/1",
  "resource_type": "application",
  "resource_id": 1,
  "is_read": false,
  "created_at": "2026-05-26T12:00:00"
}
```

## Response/Status Rehberi

- `200` basarili
- `201` create basarili
- `204` delete basarili, body yok
- `400` business rule ihlali
- `401` token yok/gecersiz
- `403` role yetkisi yok
- `404` kaynak bulunamadi
- `422` validation hatasi
