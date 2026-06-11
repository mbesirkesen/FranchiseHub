#!/usr/bin/env python3
"""Semantik marka arama (pgvector) smoke testleri.

Kelime eşleşmeyen sorgularda (örn. 'araba tamiri', 'kahvaltı mekanı') chatbot
semantik fallback ile doğru markaları bulmalı; alakasız sorgu (kuyumcu) boş/öneri.
"""

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


def _request(base, method, path, *, token=None, body=None):
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


def login(base, email, password):
    form = urllib.parse.urlencode({"username": email, "password": password}).encode()
    req = urllib.request.Request(f"{base}/auth/login", data=form, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())["access_token"]


def assert_ok(name, cond, detail=""):
    if cond:
        print(f"  OK  {name}")
        return
    msg = f"  FAIL {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    raise AssertionError(name)


def _sectors(data):
    return {(b.get("sector") or "") for b in (data.get("brands") or [])}


def main() -> int:
    parser = argparse.ArgumentParser(description="Semantic search smoke test")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    args = parser.parse_args()

    print(f"Base: {args.base}")
    status, _ = _request(args.base, "GET", "/health")
    assert_ok("health", status == 200, f"status={status}")
    token = login(args.base, args.email, args.password)
    assert_ok("login", bool(token))

    # Kelime tam eşleşmeyen ama anlamca net sorgular → ilgili sektör gelmeli.
    cases = [
        ("araba_tamiri", "araba tamiri ve lastik servisi açmak istiyorum",
         lambda d: len(d.get("brands") or []) > 0 and "Otomotiv" in _sectors(d)),
        ("cocuk_egitimi", "çocuklara yönelik eğitim kursu işletmek istiyorum",
         lambda d: len(d.get("brands") or []) > 0 and "Eğitim" in _sectors(d)),
        ("kahvalti", "güzel bir kahvaltı mekanı açmak istiyorum",
         lambda d: len(d.get("brands") or []) > 0),
    ]
    for name, q, check in cases:
        status, data = _request(args.base, "POST", "/agent/query", token=token, body={"query": q})
        ok = status == 200 and check(data)
        assert_ok(
            name,
            ok,
            f"source={data.get('source')} sectors={_sectors(data)} ans={(data.get('answer') or '')[:80]}",
        )

    # Sistemde olmayan kategori → dürüst davranış (boş ya da no_match/öneri, çökmesin).
    status, data = _request(
        args.base, "POST", "/agent/query", token=token,
        body={"query": "kuyumcu ve mücevher dükkanı bayiliği"},
    )
    assert_ok("nonexistent_category_no_crash", status == 200, json.dumps(data, ensure_ascii=False)[:120])

    print("\nTüm semantik testler geçti.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nHata: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
