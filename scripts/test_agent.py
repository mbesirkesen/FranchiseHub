#!/usr/bin/env python3
"""Franchise asistanı smoke test — backend hazır mı kontrolü."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8000"
DEFAULT_EMAIL = "buyer1@franchisehub.local"
DEFAULT_PASSWORD = "Buyer12345!"


def _request(
    base: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base}{path}", data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw) if raw else {"detail": exc.reason}
        except json.JSONDecodeError:
            payload = {"detail": raw or exc.reason}
        return exc.code, payload


def login(base: str, email: str, password: str) -> str:
    form = urllib.parse.urlencode({"username": email, "password": password}).encode()
    req = urllib.request.Request(f"{base}/auth/login", data=form, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())["access_token"]


def assert_ok(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {name}")
        return
    msg = f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    raise AssertionError(name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent API smoke test")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    args = parser.parse_args()

    print(f"Base: {args.base}")
    status, _ = _request(args.base, "GET", "/health")
    assert_ok("health", status == 200, f"status={status}")

    token = login(args.base, args.email, args.password)
    assert_ok("login", bool(token))

    cases = [
        ("brand_search", {"query": "500 bin TL altı gıda markaları"}, lambda d: d["intent"] == "brand_search" and len(d.get("brands") or []) > 0),
        ("brand_compare", {"query": "Komagene ile Brew Max karşılaştır"}, lambda d: d["intent"] == "brand_compare" and len(d.get("brands") or []) >= 2),
        ("application_status", {"query": "başvurum ne durumda"}, lambda d: d["intent"] == "application_status"),
        ("favorites_similar", {"query": "favorilerime benzer markalar"}, lambda d: d["intent"] == "favorites_similar"),
        ("match_score_ratio", {"query": "kafe franchise"}, lambda d: bool((d.get("brands") or [{}])[0].get("match_score_ratio") is not None)),
    ]
    for name, body, check in cases:
        status, data = _request(args.base, "POST", "/agent/query", token=token, body=body)
        assert_ok(name, status == 200 and check(data), json.dumps(data, ensure_ascii=False)[:200])

    status, chat1 = _request(
        args.base,
        "POST",
        "/agent/chat",
        token=token,
        body={"query": "kahve markaları", "new_session": True},
    )
    assert_ok("chat_turn_1", status == 200 and chat1.get("intent") == "brand_search")
    sid = chat1.get("session_id")

    status, chat2 = _request(
        args.base,
        "POST",
        "/agent/chat",
        token=token,
        body={"query": "daha ucuz olanlar", "session_id": sid},
    )
    assert_ok(
        "chat_followup_cheaper",
        status == 200 and chat2.get("intent") == "brand_search" and len(chat2.get("brands") or []) > 0,
    )

    status, chat3 = _request(
        args.base,
        "POST",
        "/agent/chat",
        token=token,
        body={"query": "gıda olsun", "session_id": sid},
    )
    assert_ok(
        "chat_followup_sector",
        status == 200 and chat3.get("intent") == "brand_search" and chat3.get("filters_applied", {}).get("sector") == "Gıda",
    )

    print("\nTüm agent smoke testleri geçti.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nHata: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
