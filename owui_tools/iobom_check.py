"""IO List 與 BOM（設備清單）交叉檢查：純 Python、無外部相依（xlsx 需要 openpyxl）。

檢查項目：
- io_unmatched：IO List 參照的設備在 BOM 找不到（缺漏）
- bom_without_io：BOM 有 tag、但沒有任何 IO 點參照（多出或不需 IO 的設備，屬資訊）
- duplicate_io_tags：IO tag 重複（SPARE 除外）
- duplicate_addresses：同一個 PLC 位址（控制器／機架／模組／點）被用兩次
- naming_violations：tag 不符命名規則
- format_issues：tag 前後有空白或大小寫不一致（正規化後仍可比對）
- mixed_notation：同一台設備在 IO List 同時出現點號與連字號兩種寫法（資訊）

比對 IO tag 與 BOM tag 的順序：完整 tag → 去掉點號後綴 → 點號前綴轉連字號（XV.C6701 → XV-C6701）
→ 同一儀表迴路（AAH-C6903-1 對到 AIT-C6903-1）。每一筆都記錄是用哪一種方式對上的。
「同迴路」只限帶儀表序號的迴路號（C6903-1 這種，結尾 -數字），而且 BOM 中該迴路只有唯一一個品項；
設備編號（C6701）不做同迴路比對，避免 SCBR-C6701 被對到接線盒 JBA-C6701 而漏報。
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

class InputError(ValueError):
    """輸入表格的欄位設定不對（找不到欄位、沒有任何資料）。"""


INSTRUMENT_LOOP = re.compile(r"^[A-Z]{0,2}\d{3,5}-\d+$")
DESC_TAG = re.compile(r"\b[A-Z]{1,6}-[A-Z]{0,2}\d{3,5}(?:-\d+)?\b")


def normalize_desc(s: str) -> str:
    return re.sub(r"\s+", " ", s).upper()


DEFAULT_TAG_PATTERN =r"^[A-Z]{1,6}(-[A-Z0-9]+)+(\.[A-Za-z0-9]+)*$|^[A-Z]{1,6}\.[A-Z0-9]+(\.[A-Za-z0-9]+)*$"


@dataclass
class Config:
    io_tag_col: str = "tag"
    io_desc_col: str = "description"
    io_addr_cols: tuple[str, ...] = ("controller", "rack", "module", "point")
    # 分組欄位：重複 tag／位址只在同一組（例如同一站點）內才算重複；欄位不存在時視為同一組
    io_scope_cols: tuple[str, ...] = ("site",)
    # 比對「兩張 IO 表內容完全相同」時的分組（一張表＝一個盤／控制器）
    io_table_cols: tuple[str, ...] = ("site", "panel", "controller")
    bom_tag_col: str = "tag"
    bom_tagged_col: str | None = "tagged"  # 欄位值為 N 的列（無 tag 品項）不參與比對
    spare_values: frozenset[str] = frozenset({"SPARE"})
    tag_pattern: str = DEFAULT_TAG_PATTERN


@dataclass
class Result:
    io_count: int = 0
    bom_count: int = 0
    matched: dict[str, tuple[str, str]] = field(default_factory=dict)  # io_tag -> (bom_tag, method)
    io_unmatched: list[str] = field(default_factory=list)
    bom_without_io: list[str] = field(default_factory=list)
    duplicate_io_tags: dict[str, int] = field(default_factory=dict)
    duplicate_addresses: dict[str, list[str]] = field(default_factory=dict)
    naming_violations: list[str] = field(default_factory=list)
    format_issues: list[str] = field(default_factory=list)
    mixed_notation: dict[str, list[str]] = field(default_factory=dict)
    identical_scopes: list[tuple[str, str]] = field(default_factory=list)
    desc_mismatch: list[tuple[str, str]] = field(default_factory=list)  # (io_tag, 描述中的設備編號)
    desc_tags_not_in_bom: list[str] = field(default_factory=list)  # 資訊

    def findings(self) -> dict[str, object]:
        """需要處理的問題（不含資訊類），供測試與摘要使用。"""
        return {
            "io_unmatched": self.io_unmatched,
            "desc_mismatch": self.desc_mismatch,
            "duplicate_io_tags": self.duplicate_io_tags,
            "duplicate_addresses": self.duplicate_addresses,
            "naming_violations": self.naming_violations,
            "format_issues": self.format_issues,
        }


def load_rows(path: str | Path, sheet: str | None = None) -> list[dict[str, str]]:
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(p, read_only=True, data_only=True)
        try:
            ws = wb[sheet] if sheet else wb.active
            it = ws.iter_rows(values_only=True)
            header = [str(h).strip() if h is not None else "" for h in next(it, [])]
            return [
                {h: ("" if v is None else str(v)) for h, v in zip(header, row)}
                for row in it
                if any(v not in (None, "") for v in row)
            ]
        finally:
            wb.close()
    with open(p, newline="", encoding="utf-8-sig") as f:
        # 欄位不足的短列：DictReader 給 None，一律換成空字串
        return [{k: (v or "") for k, v in row.items() if k is not None} for row in csv.DictReader(f)]


def normalize(tag: str) -> str:
    return re.sub(r"\s+", "", tag).upper()


def _loop(tag: str) -> str | None:
    """ISA 風格儀表 tag 的迴路號：去掉功能字母前綴與點號後綴，例如 AAH-C6903-1 → C6903-1。
    只有帶儀表序號（結尾 -數字）的才算；設備編號（SCBR-C6701 → C6701）回傳 None。"""
    base = tag.split(".")[0]
    if "-" not in base:
        return None
    lp = base.split("-", 1)[1]
    return lp if INSTRUMENT_LOOP.match(lp) else None


def _candidates(tag: str) -> list[tuple[str, str]]:
    out = [(tag, "完整")]
    if "." in tag:
        head, *rest = tag.split(".")
        out.append((head, "去後綴"))
        if "-" not in head and rest:
            out.append((f"{head}-{rest[0]}", "點號轉連字號"))
    return out


def check(io_rows: list[dict[str, str]], bom_rows: list[dict[str, str]], cfg: Config | None = None) -> Result:
    cfg = cfg or Config()
    pat = re.compile(cfg.tag_pattern)
    spares = {normalize(s) for s in cfg.spare_values}
    r = Result()
    _require_col(io_rows, cfg.io_tag_col, "IO List", "io_tag_col")
    _require_col(bom_rows, cfg.bom_tag_col, "BOM", "bom_tag_col")

    bom_tags_raw = [
        row.get(cfg.bom_tag_col, "") for row in bom_rows
        if not (cfg.bom_tagged_col and row.get(cfg.bom_tagged_col, "Y").strip().upper() == "N")
    ]
    bom_tags_raw = [t for t in bom_tags_raw if t.strip()]
    r.bom_count = len(bom_tags_raw)
    bom_set = {normalize(t) for t in bom_tags_raw}
    loop_members: dict[str, list[str]] = defaultdict(list)
    for t in sorted(bom_set):
        lp = _loop(t)
        if lp:
            loop_members[lp].append(t)
    # 同一迴路在 BOM 有多個品項時無法判斷是哪一個，不做同迴路比對
    bom_by_loop = {lp: ts[0] for lp, ts in loop_members.items() if len(ts) == 1}

    io_tags_raw = [row.get(cfg.io_tag_col, "") for row in io_rows]
    live = [(raw, normalize(raw)) for raw in io_tags_raw if raw.strip() and normalize(raw) not in spares]
    r.io_count = len(live)
    if not live:
        raise InputError(f"IO List 的「{cfg.io_tag_col}」欄位沒有任何 tag（SPARE 除外），請確認欄位設定。")
    if not bom_tags_raw:
        raise InputError(f"BOM 的「{cfg.bom_tag_col}」欄位沒有任何 tag，請確認欄位設定。")

    # 格式與命名
    for raw in [t for t, _ in live] + bom_tags_raw:
        # 空白、設備部分小寫：屬格式問題，正規化後再判斷命名，避免同一筆重複計算
        # 同一個 tag 在多站重複出現時只列一次
        if (re.search(r"\s", raw) or _has_lower_prefix(raw)) and raw not in r.format_issues:
            r.format_issues.append(raw)
        if not pat.match(_fix_case(re.sub(r"\s+", "", raw))) and raw not in r.naming_violations:
            r.naming_violations.append(raw)

    def scope(row: dict[str, str]) -> str:
        parts = [row.get(c, "").strip() for c in cfg.io_scope_cols if c in row]
        return "/".join(p for p in parts if p)

    # 重複 tag（同一組內）
    cnt: Counter[str] = Counter()
    for row in io_rows:
        raw = row.get(cfg.io_tag_col, "")
        n = normalize(raw)
        if raw.strip() and n not in spares:
            cnt[f"{scope(row)}:{n}" if scope(row) else n] += 1
    r.duplicate_io_tags = {t: c for t, c in cnt.items() if c > 1}

    # 重複位址（同一組內）
    addr_map: dict[str, list[str]] = defaultdict(list)
    for row in io_rows:
        if all(row.get(c, "").strip() for c in cfg.io_addr_cols):
            addr = "/".join(row[c].strip() for c in cfg.io_addr_cols)
            key = f"{scope(row)}:{addr}" if scope(row) else addr
            addr_map[key].append(row.get(cfg.io_tag_col, "").strip() or "(空白)")
    r.duplicate_addresses = {a: tags for a, tags in addr_map.items() if len(tags) > 1}

    # 不同組之間內容完全相同（可能是複製貼上）：資訊
    by_scope: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    for row in io_rows:
        table = "/".join(row.get(c, "").strip() for c in cfg.io_table_cols if row.get(c, "").strip())
        by_scope[table].append(
            tuple(row.get(c, "").strip() for c in cfg.io_addr_cols) + (normalize(row.get(cfg.io_tag_col, "")),)
        )
    keys = [k for k in by_scope if k]
    r.identical_scopes = [
        (a, b) for i, a in enumerate(keys) for b in keys[i + 1:]
        if len(by_scope[a]) > 5 and sorted(by_scope[a]) == sorted(by_scope[b])
    ]

    # tag 與描述不一致：描述中提到同功能代碼、但編號不同的設備（例如 tag XV-X6111、描述寫 XV-C6111）
    def base_of(n: str) -> str:
        return _candidates(n)[-1][0] if "." in n else n

    io_bases = {base_of(n) for _, n in live}
    seen_mm: set[tuple[str, str]] = set()
    for row in io_rows:
        raw = row.get(cfg.io_tag_col, "")
        n = normalize(raw)
        if not raw.strip() or n in spares:
            continue
        base = base_of(n)
        prefix = base.split("-")[0]
        mentioned = set(DESC_TAG.findall(normalize_desc(row.get(cfg.io_desc_col, ""))))
        same_func = {m for m in mentioned if m.split("-")[0] == prefix}
        if not same_func or base in same_func:
            continue
        # 母設備＋子件（U-C530 的流量開關 U-C5301）：只有母設備本身也被其他點直接使用時，才視為多打一碼
        parents = {m for m in same_func if base.startswith(m)}
        if parents and not (parents & io_bases):
            continue
        key = (f"{scope(row)}:{raw.strip()}" if scope(row) else raw.strip(), "、".join(sorted(same_func)))
        if key not in seen_mm:
            seen_mm.add(key)
            r.desc_mismatch.append(key)

    desc_of: dict[str, str] = {}
    for row in io_rows:
        desc_of.setdefault(normalize(row.get(cfg.io_tag_col, "")), normalize_desc(row.get(cfg.io_desc_col, "")))
    # 描述提到、但 BOM 沒有的 tag（資訊）：例如描述寫 AIT-C6903-2，BOM 沒有這台
    r.desc_tags_not_in_bom = sorted(
        {m for d in desc_of.values() for m in DESC_TAG.findall(d)} - bom_set
    )

    # IO → BOM 比對
    used_bom: set[str] = set()
    notation: dict[str, set[str]] = defaultdict(set)
    for raw, n in live:
        hit = None
        for cand, method in _candidates(n):
            if cand in bom_set:
                hit = (cand, method)
                break
        if hit is None:
            lp = _loop(n)
            if lp and lp in bom_by_loop:
                hit = (bom_by_loop[lp], "同迴路")
            elif lp and lp in loop_members:
                # 迴路有多個品項：描述中只指名其中一台時才對上（例如「DETECTOR AIT-C6903-1 CONTROLLER FAIL」）
                named = set(DESC_TAG.findall(desc_of.get(n, ""))) & set(loop_members[lp])
                if len(named) == 1:
                    hit = (named.pop(), "描述指名")
        if hit is None:
            if n not in r.io_unmatched:
                r.io_unmatched.append(n)
            continue
        r.matched[n] = hit
        used_bom.add(hit[0])
        head = n.split(".")[0]
        notation[hit[0]].add("點號" if "-" not in head else "連字號")

    # 儀表迴路：IO 參照了迴路中任一點，就視為 BOM 中該迴路的唯一品項有被參照
    used_loops = {_loop(n) for _, n in live} & set(bom_by_loop)
    r.bom_without_io = sorted(t for t in bom_set if t not in used_bom and _loop(t) not in used_loops)
    r.mixed_notation = {
        t: sorted(s) for t, s in notation.items() if len(s) > 1
    }
    # 也收錄只用點號、但 BOM 用連字號的設備（同樣算寫法不一）
    for n, (bom_tag, method) in r.matched.items():
        if method == "點號轉連字號":
            r.mixed_notation.setdefault(bom_tag, ["點號"])
    return r


def _require_col(rows: list[dict[str, str]], col: str, label: str, valve: str) -> None:
    if not rows:
        raise InputError(f"{label} 沒有任何資料列。")
    if col not in rows[0]:
        raise InputError(
            f"{label} 找不到欄位「{col}」（設定 {valve}）。現有欄位：" + "、".join(k for k in rows[0] if k)
        )


def _has_lower_prefix(raw: str) -> bool:
    """tag 的設備部分（第一個點號前）出現小寫字母；點號後綴（如 .Run）允許大小寫混用。"""
    return any(ch.islower() for ch in raw.strip().split(".")[0])


def _fix_case(raw: str) -> str:
    head, dot, tail = raw.partition(".")
    return head.upper() + dot + tail


def format_report(r: Result, top: int = 30) -> str:
    def lst(items) -> str:
        items = list(items)
        more = f"（另有 {len(items) - top} 筆）" if len(items) > top else ""
        return "、".join(f"`{x}`" for x in items[:top]) + more if items else "無"

    lines = [
        "## IO List × BOM 交叉檢查",
        f"- IO 點（不含 SPARE）：{r.io_count}；BOM 有 tag 的品項：{r.bom_count}；"
        f"不重複 IO tag 中對到 BOM 的：{len(r.matched)}／{len(r.matched) + len(r.io_unmatched)}",
        "",
        "### 需要處理",
        f"- **IO List 有、BOM 找不到**（{len(r.io_unmatched)}）：{lst(r.io_unmatched)}",
        f"- **tag 與描述的設備編號不一致**（{len(r.desc_mismatch)}）：{lst(t + ' ↔ 描述寫 ' + d for t, d in r.desc_mismatch)}",
        f"- **重複的 IO tag**（{len(r.duplicate_io_tags)}）：{lst(f'{t}×{c}' for t, c in r.duplicate_io_tags.items())}",
        f"- **重複的 PLC 位址**（{len(r.duplicate_addresses)}）：{lst(a + '→' + '/'.join(t) for a, t in r.duplicate_addresses.items())}",
        f"- **不符命名規則**（{len(r.naming_violations)}）：{lst(r.naming_violations)}",
        f"- **空白或大小寫問題**（{len(r.format_issues)}）：{lst(repr(x) for x in r.format_issues)}",
        "",
        "### 資訊（請人工判斷）",
        f"- **BOM 有、IO List 沒參照**（{len(r.bom_without_io)}，斷路器、燈具等本來就可能沒有 IO）：{lst(r.bom_without_io)}",
        f"- **IO 描述提到、但 BOM 沒有的 tag**（{len(r.desc_tags_not_in_bom)}）：{lst(r.desc_tags_not_in_bom)}",
        f"- **同一設備寫法不一**（{len(r.mixed_notation)}）：{lst(t + '（' + '/'.join(s) + '）' for t, s in r.mixed_notation.items())}",
        f"- **兩組 IO 表內容完全相同**（{len(r.identical_scopes)}，可能是複製貼上，請確認）：{lst(a + ' ＝ ' + b for a, b in r.identical_scopes)}",
        "",
        "比對方式統計：" + "、".join(
            f"{m} {c}" for m, c in Counter(m for _, m in r.matched.values()).most_common()
        ),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    io_path, bom_path = sys.argv[1:3]
    sys.stdout.reconfigure(encoding="utf-8")
    print(format_report(check(load_rows(io_path), load_rows(bom_path))))
