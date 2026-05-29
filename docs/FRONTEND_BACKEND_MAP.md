# Frontend ↔ Backend eşleme rehberi

Bu doküman, web/mobil arayüzdeki her özelliğin hangi API’ye bağlanacağını tanımlar.  
**Kaynak şema:** http://127.0.0.1:8000/openapi.json · **Swagger:** http://127.0.0.1:8000/docs

**Roller:** `buyer` | `franchise_owner` (admin kaldırıldı)

**Proxy (Next.js):** İstemci `/api/proxy/...` çağırıyorsa hedef `http://127.0.0.1:8000/...` olmalı; `Authorization: Bearer <access_token>` aynen iletilmeli.

---

## 1. Kimlik doğrulama

| Frontend | Method | Path | Auth |
|----------|--------|------|------|
| Kayıt (yatırımcı) | POST | `/auth/register/buyer` | — |
| Kayıt (franchise sahibi) | POST | `/auth/register/franchise-owner` | — |
| Giriş | POST | `/auth/login` | — |
| Token yenileme | POST | `/auth/refresh` | — |
| E-posta doğrulama | POST | `/auth/verify-email` | — |
| Şifremi unuttum | POST | `/auth/forgot-password` | — |
| Şifre sıfırla | POST | `/auth/reset-password` | — |
| Profil oku | GET | `/auth/me` | Bearer |
| Profil güncelle | PATCH | `/auth/me` | Bearer |
| Şifre değiştir | POST | `/auth/change-password` | Bearer |

---

## 2. Yatırımcı (buyer)

| Ekran / özellik | Method | Path | Notlar |
|-----------------|--------|------|--------|
| Marka keşfi | GET | `/brands` | `q`, `sector`, `region`, `page`, `sort` |
| Bölge listesi (dropdown) | GET | `/regions` | Marmara, Ege, … |
| Marka detay | GET | `/brands/{id}` | Public |
| ROI / sparkline | GET | `/brands/{id}/metrics` | `estimated_roi_percent`, `growth_series` |
| Karşılaştırma | POST | `/brands/compare` | `brands`, `comparison_table`, `financial_summaries` |
| Favoriler | GET | `/buyer/favorites` | `items` + alias `brand_ids` |
| Favori ekle/sil | POST/DELETE | `/buyer/favorites/{brand_id}` | |
| Başvurularım | GET | `/buyer/applications` | Sayfalı |
| Başvuru detay | GET | `/buyer/applications/{id}` | |
| Dashboard özet | GET | `/buyer/dashboard/summary` | |
| Uygunluk / discover | POST | `/buyer/qualification` | `match_score`, `match_reasons` |
| **Franchise Asistanı (sohbet)** | POST | `/agent/chat` | `session_id`, `message_id`, `answer`, `brands`, `suggestions` |
| **Franchise Asistanı (tek tur)** | POST | `/agent/query` veya `/buyer/assistant` | `reply`, `brands`, `filters_applied`, `compare` |
| **Asistan oturumları** | GET/DELETE | `/agent/sessions`, `/agent/sessions/{id}` | Mesaj geçmişi |
| Başvuru oluştur | POST | `/applications` | |
| Başvurularım (mesajlı) | GET | `/applications/mine` | `unread_count` |
| Başvuru detay | GET | `/applications/{id}` | `extended_status` |
| **Timeline 5 aşama** | GET | `/applications/{id}/timeline` | `steps[]`: done/active/pending/failed |
| Global arama | GET | `/search?q=` | buyer: marka + kendi başvuruları |
| Bildirimler | GET | `/notifications` | `read`↔`is_read`, `link`↔`action_url` |
| Bildirim okundu | PATCH | `/notifications/{id}/read` | |
| Tümünü okundu | POST | `/notifications/read-all` | |
| Push cihaz | POST/DELETE | `/devices`, `/devices/{token}` | |
| Dosya yükle | POST | `/files/upload` | |

---

## 3. Franchise sahibi (franchise_owner)

| Ekran / özellik | Method | Path | Notlar |
|-----------------|--------|------|--------|
| Dashboard özet | GET | `/franchise-owner/dashboard/summary` | `supply_requests_total` + alias `supply_request_total` |
| Markam | GET | `/franchise-owner/my-brand` | `null` olabilir |
| Marka oluştur/güncelle | POST/PATCH | `/franchise-owner/brand` | |
| Logo / galeri | POST | `/franchise-owner/brand/media` | multipart |
| FDD yükle | POST | `/franchise-owner/brand/fdd` | PDF multipart |
| Gelen başvurular | GET | `/applications/my-brand` | Sayfalı |
| Başvuru onay/red | PATCH | `/applications/{id}` | `approved` \| `rejected` |
| Mesajlar | GET/POST | `/messages/{application_id}`, `/messages` | |
| Konuşma listesi | GET | `/conversations` | |
| Mesaj okundu | PATCH | `/messages/{message_id}/read` | |
| Sohbet tümü okundu | POST | `/messages/{application_id}/read-all` | |
| Şubeler CRUD | GET/POST/PATCH/DELETE | `/franchise-owner/outlets`, `.../{id}` | |
| Dokümanlar | GET/POST | `/franchise-owner/documents` | |
| **Bölge yönetimi** | GET/POST/PATCH/DELETE | `/franchise-owner/territories`, `.../{id}` | |
| Analitik rapor | GET | `/franchise-owner/analytics?days=30` | `applications_by_month`, `supply_requests_by_status`, … |
| **Isı haritası** | GET | `/franchise-owner/analytics/geography` | Şehir yoğunluğu |
| **Ekosistem grafiği** | GET | `/franchise-owner/ecosystem` | `nodes`, `edges` |
| Envanter / tedarik | `/inventory`, `/supply-requests` | Ayrı modül |
| Global arama | GET | `/search?q=` | Kendi markası + başvurular |

---

## 4. Ortak (public / dosya)

| Özellik | Method | Path |
|---------|--------|------|
| Health | GET | `/health` |
| Marka medya | GET | `/files/media/{media_id}` |
| FDD indir (token) | GET | `/files/fdd/download?token=` |
| FDD signed URL | GET | `/brands/{id}/fdd/{fdd_id}/download` |
| Owner doküman | GET | `/files/owner-documents/{id}` |
| Bölge listesi (public) | GET | `/brands/{id}/territories` |

---

## 5. Frontend alan eşlemeleri (kritik)

### Bildirimler
| Frontend | Backend | Alias var mı? |
|----------|---------|---------------|
| `read` | `is_read` | Evet (`read`) |
| `link` | `action_url` | Evet (`link`) |
| `type` | `notification_type` | Evet (`type`) |
| `message` | `body` | Evet (`message`) |

### Dashboard (FO)
| Frontend | Backend |
|----------|---------|
| `supply_request_total` | `supply_requests_total` (computed alias) |

### Analitik (FO)
| Frontend | Backend |
|----------|---------|
| `applications_by_month` | `applications_by_month[]` |
| `inventory_total_quantity` | `inventory_total_quantity` |
| `supply_requests_by_status` | `{ pending, approved, rejected, shipped }` |

### Asistan
| Frontend | Backend |
|----------|---------|
| `reply` | `answer` (alias `reply`) |
| `brands` | `related_brands` (alias `brands`) |

### Karşılaştırma
`POST /brands/compare` → `brands[]` **ve** `comparison_table` **ve** `financial_summaries` — tablo için `comparison_table` kullanın.

---

## 6. Henüz yok (bilinçli sınır)

| Özellik | Durum |
|---------|--------|
| WebSocket / SSE (asistan stream, canlı mesaj) | Planlanmadı |
| FCM push gönderimi | Sadece token kaydı |
| Admin paneli | Kaldırıldı |
| DB’de 5+ application status enum | Timeline `steps` ile simüle |

---

## 7. Demo hesaplar

```text
buyer1@franchisehub.local / Buyer12345!
owner1@franchisehub.local / Owner12345!
```

Seed: `.venv/bin/python scripts/seed_test_users.py`
