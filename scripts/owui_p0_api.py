"""Open WebUI P0 清理：透過官方 API 執行，不直接改資料庫。

API key 只從環境變數 OWUI_API_KEY 讀取（腳本不讀 .env，也不會印出 key）。
由 David 在自己的終端機設定後執行，例如 PowerShell：
    $env:OWUI_API_KEY = "<在 Open WebUI 產生的 key>"

用法（預設只預覽，加 --apply 才真的執行）：
    py -3.10 scripts/owui_p0_api.py delete-orphans [--apply]
    py -3.10 scripts/owui_p0_api.py disable-openai [--apply]
    py -3.10 scripts/owui_p0_api.py pipe-description [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("OWUI_BASE_URL", "http://localhost:3000")
ORPHAN_FILE_IDS = (
    "baa836b1-691d-41c3-96e1-472d6782041a",
    "b85cb0f2-6c74-4aa6-938f-8d84094473a8",
)
PIPE_ID = "claude_gemini"
PIPE_DESCRIPTION = (
    "同時詢問 Groq 與 Google Gemini，並讓兩者互相看到對方的回答進行交叉點評。"
    "⚠️ 對話內容會送到 Groq 與 Google 的外部 API（本專案唯一的外送例外）。"
)


def load_key() -> str:
    key = os.environ.get("OWUI_API_KEY", "").strip()
    if not key:
        sys.exit("找不到環境變數 OWUI_API_KEY。請先在 Open WebUI 產生 API key 並設定。")
    return key


def call(method: str, path: str, key: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:300]


def delete_orphans(key: str, apply: bool) -> None:
    for fid in ORPHAN_FILE_IDS:
        status, info = call("GET", f"/api/v1/files/{fid}", key)
        name = info.get("filename") if isinstance(info, dict) else info
        print(f"[{fid[:8]}] GET {status} {name}")
        if status != 200 or not apply:
            continue
        status, res = call("DELETE", f"/api/v1/files/{fid}", key)
        print(f"[{fid[:8]}] DELETE {status} {res}")


def disable_openai(key: str, apply: bool) -> None:
    status, cfg = call("GET", "/openai/config", key)
    if status != 200:
        sys.exit(f"讀取 OpenAI 設定失敗：{status} {cfg}")
    print("目前 ENABLE_OPENAI_API =", cfg.get("ENABLE_OPENAI_API"))
    if not apply:
        return
    cfg["ENABLE_OPENAI_API"] = False
    status, res = call("POST", "/openai/config/update", key, cfg)
    print("更新", status, "→ ENABLE_OPENAI_API =", res.get("ENABLE_OPENAI_API") if isinstance(res, dict) else res)


def pipe_description(key: str, apply: bool) -> None:
    status, fn = call("GET", f"/api/v1/functions/id/{PIPE_ID}", key)
    if status != 200:
        sys.exit(f"讀取 pipe 失敗：{status} {fn}")
    print("目前描述：", fn["meta"].get("description"))
    print("新描述：  ", PIPE_DESCRIPTION)
    if not apply:
        return
    meta = dict(fn["meta"])
    meta["description"] = PIPE_DESCRIPTION
    form = {"id": fn["id"], "name": fn["name"], "content": fn["content"], "meta": meta}
    status, res = call("POST", f"/api/v1/functions/id/{PIPE_ID}/update", key, form)
    ok = isinstance(res, dict) and res.get("meta", {}).get("description") == PIPE_DESCRIPTION
    print("更新", status, "成功" if ok else res)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["delete-orphans", "disable-openai", "pipe-description"])
    p.add_argument("--apply", action="store_true", help="實際執行；不加只預覽")
    args = p.parse_args()
    key = load_key()
    {"delete-orphans": delete_orphans, "disable-openai": disable_openai,
     "pipe-description": pipe_description}[args.action](key, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
