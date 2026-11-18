"""把 owui_tools/iobom_check.py（檢查邏輯，單一來源）與 tool_wrapper.py（Tool 外殼）合成一個 Open WebUI Tool 檔。

輸出：owui_tools/dist/iobom_check_tool.py
用法：py -3.10 -I scripts/build_owui_tool.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "owui_tools" / "iobom_check.py"
WRAP = ROOT / "owui_tools" / "tool_wrapper.py"
OUT = ROOT / "owui_tools" / "dist" / "iobom_check_tool.py"

HEADER = '''"""
title: IO List × BOM 交叉檢查
author: local-ai-agent
version: 0.2.0
requirements: openpyxl
description: 交叉檢查附件中的 IO List 與 BOM（設備清單）：缺漏、重複 tag／位址、命名、空白大小寫、tag 與描述不一致。全部在本機執行。
"""
from __future__ import annotations

# 本檔由 scripts/build_owui_tool.py 自動產生，請改 owui_tools/iobom_check.py 或 tool_wrapper.py，不要直接改這裡。
# source-sha256: {sha}
'''


def build() -> str:
    core = SRC.read_text(encoding="utf-8")
    core = core.split('\nif __name__ == "__main__":')[0].rstrip() + "\n"
    # 去掉核心模組自己的 docstring 與 __future__（Tool 檔頭已有）
    core = core.split("from __future__ import annotations\n", 1)[1]
    wrap = WRAP.read_text(encoding="utf-8")
    sha = hashlib.sha256((core + wrap).encode()).hexdigest()[:16]
    return HEADER.format(sha=sha) + core + wrap


def main() -> int:
    OUT.parent.mkdir(exist_ok=True)
    text = build()
    OUT.write_text(text, encoding="utf-8")
    compile(text, str(OUT), "exec")
    print(f"已產生 {OUT.relative_to(ROOT)}（{len(text.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
