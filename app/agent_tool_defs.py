from __future__ import annotations

"""LLM tool şemaları — OpenAI/Groq uyumlu function calling."""

AGENT_TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_brands",
            "description": (
                "Onaylı franchise markalarını ara. Fiyat, sektör, şehir veya serbest metin "
                "ile filtrele. Marka listesi her zaman veritabanından gelir."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Sektör adı (DB'deki gibi)"},
                    "location": {"type": "string", "description": "Şehir"},
                    "max_cost": {"type": "number", "description": "Maksimum yatırım TL"},
                    "min_cost": {"type": "number", "description": "Minimum yatırım TL"},
                    "query_text": {"type": "string", "description": "Marka adı veya anahtar kelime"},
                    "use_profile_budget": {
                        "type": "boolean",
                        "description": "Alıcı profil bütçesini kullan",
                    },
                    "sort": {
                        "type": "string",
                        "enum": ["cost_asc", "cost_desc", "roi_desc"],
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_brands",
            "description": "İki veya daha fazla markayı karşılaştır (maliyet, ROI vb.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "brand_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Karşılaştırılacak marka adları",
                    },
                },
                "required": ["brand_names"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_application_status",
            "description": "Alıcının başvuru durumlarını listele",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "favorites_similar",
            "description": "Favori markalara benzer onaylı markalar öner",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pick_from_list",
            "description": (
                "Son gösterilen marka listesinden birini seç: en ucuz, en pahalı, "
                "en uygun veya sıra numarası"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["cheapest", "expensive", "best_match", "ordinal"],
                    },
                    "index": {
                        "type": "integer",
                        "description": "ordinal modda 0=birinci, 1=ikinci, -1=son",
                    },
                },
                "required": ["mode"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_brand_detail",
            "description": "Tek bir markanın ROI, şube ve bölge özetini getir",
            "parameters": {
                "type": "object",
                "properties": {
                    "brand_name": {"type": "string"},
                    "brand_id": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "general_help",
            "description": "Selam, teşekkür veya genel platform yardımı",
            "parameters": {
                "type": "object",
                "properties": {
                    "tone": {
                        "type": "string",
                        "enum": ["greeting", "thanks", "help"],
                    },
                },
                "required": ["tone"],
                "additionalProperties": False,
            },
        },
    },
]
