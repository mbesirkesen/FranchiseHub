# Web paneli — backend sözleşme uyumu

Frontend proxy: `Authorization: Bearer` → `BACKEND_API_BASE_URL`

## Öncelik 1 — Mesajlaşma ✅

| Metot | Path | Durum |
|-------|------|--------|
| GET | `/conversations` | ✅ `{ "items": [...] }` (frontend dizi de normalize ediyor) |
| GET | `/messages/{application_id}` | ✅ Kronolojik `MessageRead[]` |
| POST | `/messages` | ✅ `{ application_id, content }` |
| PATCH | `/messages/{application_id}/read-all` | ✅ (POST alias da var) |

**Onay kuralı:** `application.status !== "approved"` → **403** Türkçe mesaj:

```json
{
  "detail": "Mesajlaşma yalnızca onaylanmış (approved) başvurularda açıktır. Bu başvurunun durumu: beklemede (pending)."
}
```

**Yetki:** Alıcı → kendi başvurusu; marka sahibi → kendi marka(lar)ına gelen başvurular.

**Deep link (bildirim + panel):**

- Alıcı: `/buyer/messages/{applicationId}`
- Marka sahibi: `/franchise-owner/messages/{applicationId}`

## Öncelik 2 — Bildirimler ✅

| Metot | Path | Durum |
|-------|------|--------|
| GET | `/notifications` | ✅ `items`, `unread_count`, alias `read` + `link` |
| PATCH | `/notifications/{id}/read` | ✅ |
| POST | `/notifications/read-all` | ✅ |

**Olay tetikleyicileri** (`app/notification_events.py`):

| Olay | `type` | `link` |
|------|--------|--------|
| Yeni başvuru | `application_pending` | `/franchise-owner/applications/{id}` |
| Onaylandı | `application_approved` | `/buyer/applications/{id}` |
| Reddedildi | `application_rejected` | `/buyer/applications/{id}` |
| Yeni mesaj | `message` | `/buyer/messages/{id}` veya `/franchise-owner/messages/{id}` |
| Düşük stok | `stock` | `/franchise-owner/stock` |

Örnek cevap alanı:

```json
{
  "id": 1,
  "title": "Yeni başvuru",
  "body": "...",
  "read": false,
  "is_read": false,
  "created_at": "2026-05-26T12:00:00Z",
  "type": "application_pending",
  "link": "/franchise-owner/applications/12"
}
```

## Öncelik 3 — AI asistan ✅

| Metot | Path | Durum |
|-------|------|--------|
| POST | `/agent/chat` | ✅ Oturum + cevap |
| GET | `/agent/sessions` | ✅ Liste (opsiyonel) |
| GET | `/agent/sessions/{id}` | ✅ `{ "session", "messages" }` |
| DELETE | `/agent/sessions/{id}` | ✅ 204 |
| POST | `/agent/query` | ✅ Tek tur (oturumsuz) |

**POST /agent/chat** body: `query`, `session_id`, `new_session`, `brand_id`, `brand_context_id`

**Cevap:** `answer`, `reply` (alias), `session_id`, `suggestions`, `brands` (`match_score` 0–100, `match_score_ratio` 0–1)

## Öncelik 4 — Opsiyonel (mevcut)

- `GET /brands/{id}/media`, `/fdd`, `/territories` ✅
- `GET /franchise-owner/analytics` ✅
- `GET /inventory/low-stock` ✅ (franchise-owner envanter)
- `GET /buyer/favorites` ✅

## Demo veri

```bash
python scripts/reset_database.py -y
python scripts/seed_test_users.py --reset --buyers 30 --owners 30
```

Test: `buyer1@franchisehub.local` / `Buyer12345!`
