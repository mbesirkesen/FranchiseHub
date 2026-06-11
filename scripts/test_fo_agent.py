#!/usr/bin/env python3
"""Franchise sahibi asistanı smoke testleri."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8000"
DEFAULT_EMAIL = "owner.komagene-hub@franchisehub.local"
DEFAULT_PASSWORD = "Owner12345!"


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
    parser = argparse.ArgumentParser(description="FO Agent API smoke test")
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
        ("low_stock", {"query": "düşük stoklar neler"}, lambda d: d["intent"] == "low_stock"),
        ("supply_requests", {"query": "bekleyen tedarik talepleri"}, lambda d: d["intent"] == "supply_requests"),
        ("pending_applications", {"query": "bekleyen başvurular"}, lambda d: d["intent"] == "pending_applications"),
        ("dashboard", {"query": "panel özeti"}, lambda d: d["intent"] == "dashboard"),
        ("outlets", {"query": "şubelerim"}, lambda d: d["intent"] == "outlets"),
        ("greeting", {"query": "merhaba"}, lambda d: d["intent"] == "general"),
    ]
    for name, body, check in cases:
        status, data = _request(args.base, "POST", "/agent/fo/query", token=token, body=body)
        assert_ok(name, status == 200 and check(data), json.dumps(data, ensure_ascii=False)[:200])

    status, chat1 = _request(
        args.base,
        "POST",
        "/agent/fo/chat",
        token=token,
        body={"query": "düşük stok durumu", "new_session": True},
    )
    assert_ok("fo_chat_turn_1", status == 200 and chat1.get("intent") == "low_stock")
    sid = chat1.get("session_id")

    status, chat2 = _request(
        args.base,
        "POST",
        "/agent/fo/chat",
        token=token,
        body={"query": "teşekkürler", "session_id": sid},
    )
    assert_ok("fo_chat_thanks", status == 200 and chat2.get("intent") == "general")

    print("\nTüm FO agent testleri geçti.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nHata: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
