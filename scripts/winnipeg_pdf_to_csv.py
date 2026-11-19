"""把溫尼伯 Tender 415-2025 附錄 A（I/O List）與附錄 B（Equipment List）的 PDF 抽出文字轉成 CSV。

用途：當作 IO List／BOM 交叉檢查的公開開發語料（真實案場文件之後直接換成 xlsx/csv）。
輸入是 pypdf 逐頁抽出的文字（每個表格儲存格一行），輸出 CSV。

用法：
    py -3.10 -I scripts/winnipeg_pdf_to_csv.py io  <A.txt> <io_list.csv>
    py -3.10 -I scripts/winnipeg_pdf_to_csv.py equip <B.txt> <equipment_list.csv>
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

CTRL = re.compile(r"^(PLC|RIO)-[A-Z0-9]+$")
TYPE = re.compile(r"^(DI|DO|AI|AO)\b")
NUM = re.compile(r"^\d+$")
EQUIP_TAG = re.compile(r"^[A-Z]{1,6}(-[A-Z0-9]+)+(\.[A-Z0-9]+)?$")
DRAWING = re.compile(r"^\d-\d{4}[A-Z]-[A-Z]\d{4}-\d{3}$")
YESNO = {"Yes", "No"}


def tokens(path: str) -> list[str]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("=== page"):
            out.append(s)
    return out


def is_row_start(t: list[str], i: int) -> bool:
    return (
        i + 3 < len(t)
        and CTRL.match(t[i]) is not None
        and all(NUM.match(x) for x in t[i + 1 : i + 4])
    )


SITE_HDR = re.compile(r"^(?P<site>[A-Za-z]+) - .*?(?P<panel>CP-[A-Z0-9]+)\s*$")


def site_at(t: list[str], i: int) -> tuple[str, str]:
    """往回找最近一個「<站點> - … Panel CP-xxxx」表頭。"""
    for k in range(i, -1, -1):
        m = SITE_HDR.match(t[k])
        if m:
            return m["site"], m["panel"]
    return "", ""


def parse_io(t: list[str]) -> list[dict]:
    rows = []
    starts = [i for i in range(len(t)) if is_row_start(t, i)]
    for k, i in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(t)
        cells = t[i:end]
        ctrl, rack, module, point = cells[:4]
        rest = cells[4:]
        ti = next((j for j, c in enumerate(rest) if TYPE.match(c)), None)
        if ti is None:
            continue
        head, sig, tail = rest[:ti], rest[ti], rest[ti + 1 :]
        tag = head[0] if head else ""
        desc = " ".join(head[1:])
        if tag == "SPARE" and not desc:
            desc = "SPARE"
        # 尾端遇到下一頁的表頭就截斷
        for stop in ("Document Code", "PLC", "I/O LIST"):
            if stop in tail:
                tail = tail[: tail.index(stop)]
        fail_safe = tail[0] if tail and tail[0] == "F/S" else ""
        states = tail[1:] if fail_safe else tail
        site, panel = site_at(t, i)
        rows.append(
            {
                "site": site, "panel": panel,
                "controller": ctrl, "rack": rack, "module": module, "point": point,
                "tag": tag, "description": desc, "signal_type": sig,
                "fail_safe": fail_safe,
                "state_0": states[0] if len(states) > 0 else "",
                "state_1": states[1] if len(states) > 1 else "",
            }
        )
    return rows


def parse_equipment(t: list[str]) -> list[dict]:
    """每一列都以圖號結尾：<tag> <描述…> <Yes/No ×3> <圖號>。遇到表頭就清掉暫存。"""
    rows, buf = [], []
    for x in t:
        if x == "Drawing Number":
            buf = []
            continue
        if DRAWING.match(x):
            if len(buf) >= 4 and all(f in YESNO for f in buf[-3:]):
                tag, desc, flags = buf[0], buf[1:-3], buf[-3:]
                rows.append(
                    {
                        "tag": tag,
                        "tagged": "Y" if EQUIP_TAG.match(tag) else "N",
                        "description": " ".join(desc).replace(" ɸ", "ɸ"),
                        "training_required": flags[0], "lamacoid": flags[1],
                        "shop_drawing_required": flags[2], "drawing": x,
                    }
                )
            buf = []
            continue
        buf.append(x)
    return rows


def main() -> int:
    kind, src, dst = sys.argv[1:4]
    t = tokens(src)
    rows = parse_io(t) if kind == "io" else parse_equipment(t)
    with open(dst, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{kind}: {len(rows)} 列 → {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
