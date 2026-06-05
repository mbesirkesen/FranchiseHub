from __future__ import annotations


def normalize_product_name(name: str) -> str:
    return " ".join(name.strip().split())


def product_names_match(left: str, right: str) -> bool:
    return normalize_product_name(left).casefold() == normalize_product_name(right).casefold()
