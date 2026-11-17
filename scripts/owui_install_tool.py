"""把 owui_tools/dist/iobom_check_tool.py 安裝（或更新）到本機 Open WebUI，透過官方 API，不直接改資料庫。

API key 只從環境變數 OWUI_API_KEY 讀取（腳本不讀 .env，也不會印出 key）。
由 David 在自己的終端機設定後執行，例如 PowerShell：
    $env:OWUI_API_KEY = "<在 Open WebUI 產生的 key>"

用法（預設只預覽，加 --apply 才真的安裝或更新）：
    py -3.10 scripts/build_owui_tool.py
    py -3.10 scripts/owui_install_tool.py [--apply]

安裝後的 Tool 預設只有管理員（建立者）看得到；要給其他人用，在 工作區 → 工具 調整權限。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL_FILE = ROOT / "owui_tools" / "dist" / "iobom_check_tool.py"
TOOL_ID = "iobom_check"

BASE = os.environ.get("OWUI_BASE_URL", "http://localhost:3000")
_u = urllib.parse.urlparse(BASE)
if _u.scheme != "http" or _u.hostname not in ("localhost", "127.0.0.1") or "@" in BASE:
    sys.exit(f"OWUI_BASE_URL 只允許本機位址，避免 API key 送到其他主機：{BASE}")


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
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:500]
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"連不上 {BASE}：{getattr(e, 'reason', e)}（Open WebUI 有在跑嗎？）")
    except json.JSONDecodeError:
        sys.exit(f"{BASE}{path} 回應不是 JSON，請確認 OWUI_BASE_URL 指向 Open WebUI。")


def frontmatter(text: str, field: str) -> str:
    m = re.search(rf"^{field}:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="真的安裝或更新（預設只預覽）")
    args = ap.parse_args()

    if not TOOL_FILE.exists():
        sys.exit(f"找不到 {TOOL_FILE}，請先執行 py -3.10 scripts/build_owui_tool.py")
    content = TOOL_FILE.read_text(encoding="utf-8")
    sha = re.search(r"^# source-sha256: (\w+)", content, re.MULTILINE)
    form = {
        "id": TOOL_ID,
        "name": frontmatter(content, "title"),
        "content": content,
        "meta": {"description": frontmatter(content, "description"), "manifest": {}},
    }
    print(f"Tool 檔：{TOOL_FILE.name}（{len(content.splitlines())} 行，source-sha256 {sha.group(1) if sha else '?'}）")

    key = load_key()
    status, existing = call("GET", f"/api/v1/tools/id/{TOOL_ID}", key)
    exists = status == 200
    if status == 401:
        sys.exit("API key 無效或未啟用 API 金鑰（401）。")
    if status not in (200, 404):
        sys.exit(f"查詢既有 Tool 失敗：{status} {existing}（403 表示這把 key 的帳號沒有管理工具的權限）")
    print("目前狀態：", "已安裝，將更新內容" if exists else "未安裝，將新建")
    if not args.apply:
        print("預覽模式：加 --apply 才會寫入。")
        return 0

    path = f"/api/v1/tools/id/{TOOL_ID}/update" if exists else "/api/v1/tools/create"
    status, res = call("POST", path, key, form)
    if status != 200:
        sys.exit(f"失敗：{status} {res}")
    print(f"完成：{status} id={res.get('id') if isinstance(res, dict) else res}")

    status, spec = call("GET", f"/api/v1/tools/id/{TOOL_ID}/valves/spec", key)
    if status == 200 and isinstance(spec, dict):
        print("Valves 欄位：", "、".join(spec.get("properties", {})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
