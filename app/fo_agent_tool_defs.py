from __future__ import annotations

FO_AGENT_TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_low_stock",
            "description": "Düşük stoklu envanter kalemlerini listele",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["all", "center", "outlet"],
                        "description": "Merkez deposu veya şube stoğu",
                    },
                    "limit": {"type": "integer", "description": "Max kayıt (varsayılan 10)"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_supply_requests",
            "description": "Tedarik taleplerini listele (bekleyen, onaylı vb.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "approved", "rejected", "shipped", "all"],
                    },
                    "incoming_only": {
                        "type": "boolean",
                        "description": "Yalnızca şubelerden gelen talepler",
                    },
                    "limit": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pending_applications",
            "description": "Markana gelen bekleyen alıcı başvurularını listele",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "owner_dashboard_summary",
            "description": "Panel özeti: başvuru, stok ve tedarik sayıları",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_my_outlets",
            "description": "Franchise şubelerini listele",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fo_general_help",
            "description": "Selam, teşekkür veya FO panel yardımı",
            "parameters": {
                "type": "object",
                "properties": {
                    "tone": {"type": "string", "enum": ["greeting", "thanks", "help"]},
                },
                "required": ["tone"],
                "additionalProperties": False,
            },
        },
    },
]
