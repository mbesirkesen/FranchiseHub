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

LLM iki modda çalışır:
- **Tool routing** (`AGENT_LLM_ROUTING_ENABLED=true`): LLM tool seçer → sonuç DB'den (`source: llm_tools`)
- **Metin cilası**: Taslak cevabı Türkçeleştirir (`source: hybrid`)

Marka listesi ve fiyatlar her zaman veritabanından gelir; LLM uydurmaz.

## Semantik arama (pgvector / RAG)

Kelime tam eşleşmeyen sorgularda (ör. "araba tamiri", "çocuk eğitimi", "kahvaltı mekanı")
kural-tabanlı arama boş kalır veya alakasız genel listeye düşerse, semantik fallback
devreye girer (`source: semantic`).

- Vektör deposu: Neon PostgreSQL + `pgvector` (`brand_embeddings` tablosu, `vector(384)`).
- Embedding: yerel `fastembed` / `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Markalar lazy indexlenir; toplu indexleme: `python scripts/reindex_brands.py`.
- `.env`: `AGENT_EMBEDDING_ENABLED` (varsayılan true), `AGENT_EMBEDDING_MODEL`,
  `AGENT_SEMANTIC_MAX_DISTANCE` (varsayılan 0.55).
- Model yüklenemezse semantik arama sessizce devre dışı kalır; chatbot kural+DB ile çalışır.

Migration: `migrations/20260611_brand_embeddings.sql`.

`source` değerleri: `rules` | `hybrid` | `llm_tools` | `semantic`.

`GET /agent/metrics` — intent / no_match istatistikleri (geliştirme).

## Migration

```bash
# Neon / psql
psql $DATABASE_URL -f migrations/20260530_agent_chat.sql
```

## Frontend

Öncelik: `POST /agent/chat` + `session_id` ile çok turlu UI. Tek seferlik widget için `POST /agent/query` yeterli.
