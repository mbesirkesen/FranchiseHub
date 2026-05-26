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
  "token_type": "bearer"
}
```

## Buyer Endpoints

- `GET /brands`
- `GET /brands/{brand_id}`
- `POST /brands/compare`
- `POST /applications`

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

- `GET /inventory` — cevap `{ "items": [ ... ] }`
- `POST /inventory`
- `PATCH /inventory/{inventory_id}`
- `DELETE /inventory/{inventory_id}`
- `GET /supply-requests` — `{ "items": [ ... ] }`
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

## Admin Endpoints

- `GET /admin/users`
- `PATCH /admin/brands/{brand_id}/approve`
- `PATCH /admin/applications/{application_id}/override`

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

## Response/Status Rehberi

- `200` basarili
- `201` create basarili
- `204` delete basarili, body yok
- `400` business rule ihlali
- `401` token yok/gecersiz
- `403` role yetkisi yok
- `404` kaynak bulunamadi
- `422` validation hatasi
