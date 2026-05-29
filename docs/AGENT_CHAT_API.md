# Franchise Asistanı — Chat API

## Endpoint'ler

| Method | Path | Açıklama |
|--------|------|----------|
| POST | `/agent/chat` | Sohbet turu (oturum + geçmiş) |
| POST | `/agent/query` | Tek tur, oturumsuz |
| GET | `/agent/sessions` | Oturum listesi |
| GET | `/agent/sessions/{id}` | Oturum + mesajlar |
| DELETE | `/agent/sessions/{id}` | Oturumu sil |

Alias: `POST /buyer/assistant`, `POST /buyer/assistant/query`

## Auth

Bearer token, rol: `buyer`

## POST /agent/chat

```json
{
  "query": "500 bin TL altı gıda markaları",
  "session_id": 12,
  "brand_id": null,
  "brand_context_id": null,
  "new_session": false
}
```

- `session_id` yok → yeni oturum
- `new_session: true` → her zaman yeni oturum
- Rate limit: `AGENT_RATE_LIMIT_PER_MINUTE` (varsayılan 30/dk)

## Response

`AssistantQueryResponse`: `answer`, `reply`, `brands`, `intent`, `source` (`rules` | `hybrid`), `filters_applied`, `suggestions`, `session_id`, `message_id`, `latency_ms`, opsiyonel `compare`.

## Intent'ler

- `brand_search` — NLU + marka listesi (max 4)
- `brand_detail` — `brand_id` + ROI/metrik
- `brand_compare` — marka adlarından karşılaştırma tablosu
- `favorites_similar` — favorilere benzer markalar
- `application_status` — başvuru özeti
- `territory_check` — müsait bölgeler
- `general` / `no_match`

## suggestion action'ları

`open_brand`, `add_favorite`, `start_application`, `refine_search`

## LLM (opsiyonel)

`.env` (Groq örneği):

```env
AGENT_LLM_ENABLED=true
OPENAI_API_KEY=gsk_...
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile
```

LLM yalnızca cevap metnini cilar; marka listesi her zaman veritabanından gelir.

## Migration

```bash
# Neon / psql
psql $DATABASE_URL -f migrations/20260530_agent_chat.sql
```

## Frontend

Öncelik: `POST /agent/chat` + `session_id` ile çok turlu UI. Tek seferlik widget için `POST /agent/query` yeterli.
