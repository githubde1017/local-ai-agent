"""把評測題草稿（jsonl）做成審查表（Markdown）：每題附出處頁的原文段落，審查者只需勾選。

用法：py -3.10 -I scripts/make_eval_review_sheet.py <評測題 jsonl> <pdf_to_txt.py 的輸出資料夾> <輸出 .md> [題號清單]
題號清單可選：逗號分隔的題號，或存有題號的檔案（scripts/owui_eval.py --triage-out 的輸出），只留這些題。

自動檢查（任何一項失敗就列在審查表開頭，並以結束碼 1 結束；表仍會產生）：
  - source.pages 內每一頁都存在
  - source.anchor 確實出現在 source.page 的文字中
數字比對只是提示：從答案要點取出數字，看有沒有出現在出處頁，不能取代人工判斷。
審查表含公開語料的原文片段，不要放進 git（預設輸出在 repo 外）。
"""
import json
import re
import sys
from pathlib import Path

CONTEXT = 6  # 錨點前後各取幾行
NUM = re.compile(r"\d[\d,.:]*\d|\d")


def load_pages(txt: Path) -> dict[int, list[str]]:
    pages, cur = {}, None
    for line in txt.read_text(encoding="utf-8").splitlines():
        m = re.match(r"=== page (\d+) ===", line)
        if m:
            cur = int(m.group(1))
            pages[cur] = []
        elif cur is not None:
            pages[cur].append(line.replace("\f", ""))
    return pages


def excerpt(lines: list[str], anchor: str) -> str | None:
    for i, line in enumerate(lines):
        if anchor and anchor in line.strip():
            lo, hi = max(0, i - CONTEXT), min(len(lines), i + CONTEXT + 1)
            return "\n".join(("▶ " if k == i else "  ") + lines[k] for k in range(lo, hi))
    return None


def number_hints(points: list[str], page_text: str) -> str:
    flat = page_text.replace(",", "")
    toks = sorted({t.replace(",", "") for p in points for t in NUM.findall(p) if len(t.replace(",", "")) >= 2})
    if not toks:
        return "答案要點沒有數字"
    found = [t for t in toks if t in flat]
    miss = [t for t in toks if t not in flat]
    return f"出處頁找得到：{', '.join(found) or '（無）'}｜找不到：{', '.join(miss) or '（無）'}（日期或換算過的數字找不到是正常的）"


def main(jsonl: str, txt_dir: str, out: str, only: str | None = None) -> int:
    qs = [json.loads(x) for x in Path(jsonl).read_text(encoding="utf-8").splitlines() if x.strip()]
    total = len(qs)
    if only:
        raw = Path(only).read_text(encoding="utf-8") if Path(only).is_file() else only
        ids = {i for i in re.split(r"[,\s]+", raw) if i}
        if not ids:
            raise SystemExit("題號清單是空的，沒有題目需要審（或清單檔沒寫入）。")
        unknown = ids - {x["id"] for x in qs}
        if unknown:
            raise SystemExit(f"題號不存在：{sorted(unknown)}")
        qs = [x for x in qs if x["id"] in ids]
    cache: dict[str, dict[int, list[str]]] = {}
    problems, body = [], []
    for q in qs:
        s = q["source"]
        pages = cache.setdefault(s["file"], load_pages(Path(txt_dir) / s["file"].replace(".pdf", ".txt")))
        missing = [p for p in s["pages"] if p not in pages]
        ex = excerpt(pages.get(s["page"], []), s["anchor"])
        if missing:
            problems.append(f"{q['id']}：pages 含不存在的頁 {missing}")
        if ex is None:
            problems.append(f"{q['id']}：錨點不在 page {s['page']} 的文字中")
        page_text = "\n".join(pages.get(s["page"], []))
        body.append(
            f"## {q['id']}｜{q['type']}｜{s['file']} p.{s['page']}"
            + (f"（其他算對的頁：{[p for p in s['pages'] if p != s['page']]}）" if len(s["pages"]) > 1 else "")
            + f"\n\n**問題**：{q['question']}\n\n**答案要點（草稿）**\n"
            + "".join(f"- {a}\n" for a in q["answer_points"])
            + f"\n章節：{s['section']}\n\n數字比對：{number_hints(q['answer_points'], page_text)}\n\n"
            + "**原文（▶ 為錨點行）**\n\n```text\n" + (ex or "【找不到錨點，這題的頁碼或錨點有問題】") + "\n```\n\n"
            + "- [ ] 答案正確　- [ ] 頁碼正確　- [ ] 題目合理（不是只能靠背答案）\n"
            + "- 修改意見：\n\n---\n"
        )
    head = (
        f"# 評測題審查表（{len(qs)} 題）\n\n來源：`{Path(jsonl).name}`。"
        + (
            f"**這是子集（{len(qs)}/{total} 題），不能據此把整份標成 reviewed**；其餘題目尚未審查。\n"
            if len(qs) < total
            else "全部勾完、沒問題的題目，才把 jsonl 的 `reviewed` 改成 true。\n"
        )
        + "審查表含公開語料原文片段，僅供本機審查，不進 git。\n\n"
    )
    if problems:
        head += "## ⚠ 自動檢查失敗\n" + "".join(f"- {p}\n" for p in problems) + "\n---\n\n"
    else:
        head += f"自動檢查：{len(qs)} 題的頁碼都存在、錨點都在出處頁。\n\n---\n\n"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(head + "\n".join(body), encoding="utf-8", newline="\n")
    print(f"{len(qs)} 題，問題 {len(problems)} 項 → {out}")
    for p in problems:
        print("FAIL", p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:5]))
