"""Open WebUI 檢索評測：對知識庫逐題查詢，量 recall@k、MRR、延遲，並挑出需要人審的題。

API key 只從環境變數 OWUI_API_KEY 讀取（腳本不讀 .env，也不會印出 key），由 David 在自己的終端機設定：
    $env:OWUI_API_KEY = "<在 Open WebUI 產生的 key>"

用法：
    py -3.10 -I scripts/owui_eval.py --jsonl 03_docs/eval/public_415-2025_draft.jsonl \
        --collection <知識庫 id> --config baseline --triage-out D:/local-ai-agent/_review/triage_ids.txt

做的事：
  1. 每題呼叫 /api/v1/retrieval/query/collection（k 預設 5），記錄延遲；先暖機 2 題不計入。
     檢索設定一律用 Open WebUI 全域設定（沒有 --hybrid 旗標：0.13.4 的 per-request hybrid 不可靠，審查已指出）。
     執行時會印出目前生效的設定並寫進 metrics 的 command 欄；要比較設定，先在 UI 改全域設定再跑。
     請求不走系統代理、不跟隨重新導向，避免 key 外送。
  2. 頁碼基準校準：Open WebUI 的 page 可能從 0 或 1 起算，兩種都算一次，取 recall 較高者並印出兩者。
     這是用同一批題挑的，分數會略為樂觀；確定基準後請用 --page-offset 固定。
  3. recall@k = 前 k 筆內有出處檔且頁碼落在 source.pages 的題數比例；MRR 取第一個命中的名次倒數。
  4. --repeat N 重跑 N 次，逐題比對命中名次，不一致就結束碼 2（驗證可重現）。
  5. 需人審清單 = 全部未命中題 ＋ 固定 seed 抽樣的命中題；--triage-out 寫成逗號分隔的題號，
     可交給 scripts/make_eval_review_sheet.py 的第 4 個參數，審查表只留這些題。
  6. 指標追加到 --metrics（預設 02_data/metrics.csv）。

沒有可比對結果（空回傳、檔名對不上、沒有 page）或重跑不一致時，不寫入 metrics。
未驗證（第一次實跑時確認）：實際回傳的 metadatas 內容、/retrieval/config 的欄位名（腳本以關鍵字挑選）。
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ranked_chunks(result: dict, filename: str) -> list[tuple[int, int | None]]:
    """回傳出自 filename 的 chunk：[(名次 1 起算, page 或 None)]。名次依整個結果列表的位置，不是只算該檔。"""
    mds = ((result or {}).get("metadatas") or [[]])[0] or []
    out = []
    for rank, md in enumerate(mds, 1):
        md = md or {}
        names = {md.get("name"), md.get("source"), os.path.basename(str(md.get("source") or ""))}
        if filename in names:
            page = md.get("page")
            out.append((rank, page if isinstance(page, int) else None))
    return out


def first_hit(result: dict, q: dict, k: int, offset: int) -> int | None:
    """前 k 筆內第一個命中（檔名相符且 page+offset 在 source.pages）的名次；沒有回傳 None。"""
    s = q["source"]
    for rank, page in ranked_chunks(result, s["file"]):
        if rank > k:
            break
        if page is not None and page + offset in s["pages"]:
            return rank
    return None


def choose_offset(results: list[dict], qs: list[dict], k: int) -> tuple[int, dict[int, float], bool]:
    """在 0、1 之間挑 recall 較高的頁碼偏移。回傳 (偏移, {偏移: recall}, 是否打平)。打平時取 0。"""
    rec = {}
    for off in (0, 1):
        rec[off] = sum(first_hit(r, q, k, off) is not None for r, q in zip(results, qs)) / len(qs)
    tie = rec[0] == rec[1]
    return (1 if rec[1] > rec[0] else 0), rec, tie


def percentile(vals: list[float], p: float) -> float:
    s = sorted(vals)
    return s[max(0, math.ceil(p * len(s)) - 1)]


def metrics_of(ranks: list[int | None], latencies: list[float]) -> dict[str, float]:
    n = len(ranks)
    return {
        "recall": sum(r is not None for r in ranks) / n,
        "mrr": sum(1 / r for r in ranks if r) / n,
        "p50": percentile(latencies, 0.50),
        "p95": percentile(latencies, 0.95),
    }


def triage(qs: list[dict], ranks: list[int | None], sample: int, seed: int) -> list[str]:
    """全部未命中題 ＋ 固定 seed 抽樣的命中題（依題號排序，同一 seed 結果相同）。"""
    misses = [q["id"] for q, r in zip(qs, ranks) if r is None]
    hits = sorted(q["id"] for q, r in zip(qs, ranks) if r is not None)
    picked = random.Random(seed).sample(hits, min(sample, len(hits)))
    return sorted(set(misses) | set(picked))


def run_once(qs: list[dict], search, k: int, warmup: int = 0) -> tuple[list[dict], list[float]]:
    results, lats = [], []
    for q in qs[:warmup]:  # 暖機（embedding／reranker 冷啟動），結果與延遲都不計
        search(q["question"], k)
    for q in qs:
        t0 = time.perf_counter()
        results.append(search(q["question"], k))
        lats.append(time.perf_counter() - t0)
    return results, lats


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # 帶 Authorization 的請求不跟隨重新導向
        return None


def _opener():
    """不走系統代理（避免 Bearer key 先送到代理伺服器）、不跟隨重新導向。"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _call(base: str, key: str, method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with _opener().open(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"{path} 失敗 HTTP {e.code}：{e.read().decode(errors='replace')[:200]}")
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"連不上 {base}：{getattr(e, 'reason', e)}（Open WebUI 有在跑嗎？）")


def make_search(base: str, key: str, collection: str):
    """檢索設定（hybrid、reranker、embedding…）一律用 Open WebUI 的全域設定：
    0.13.4 的 /query/collection 對 per-request 的 hybrid 參數不可靠，所以不提供該旗標。要比較設定，先在 UI 改全域設定再跑。"""
    def search(query: str, k: int) -> dict:
        return _call(base, key, "POST", "/api/v1/retrieval/query/collection",
                     {"collection_names": [collection], "query": query, "k": k})

    return search


_CFG_WORDS = ("hybrid", "embedding_model", "reranking_model", "top_k", "relevance", "chunk")


def effective_config(base: str, key: str) -> dict:
    """盡力讀取目前生效的檢索設定（需管理員 key；讀不到就回傳空）。欄位以關鍵字挑，未對照 0.13.4 實際欄位名。"""
    try:
        cfg = _call(base, key, "GET", "/api/v1/retrieval/config")
    except SystemExit:
        return {}
    flat = {}

    def walk(d, prefix=""):
        for k_, v in (d or {}).items() if isinstance(d, dict) else []:
            if isinstance(v, dict):
                walk(v, f"{prefix}{k_}.")
            elif any(w in k_.lower() for w in _CFG_WORDS) and not any(s in k_.lower() for s in ("key", "secret", "token", "url")):
                flat[prefix + k_] = v

    walk(cfg)
    return flat


def git_commit() -> str:
    """HEAD 短雜湊；工作區有未 commit 的變更時加「-dirty」，指標與程式碼版本才對得上。"""
    base = ["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT)]
    try:
        h = subprocess.run(base + ["rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=20).stdout.strip()
        dirty = subprocess.run(base + ["status", "--porcelain"], capture_output=True, text=True, timeout=20).stdout.strip()
        return (h or "unknown") + ("-dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def append_metrics(path: Path, config: str, k: int, m: dict[str, float], offset: int, command: str) -> None:
    new = not path.exists()
    today, commit = datetime.date.today().isoformat(), git_commit()
    rows = [
        (f"eval_{config}_recall@{k}", m["recall"]), (f"eval_{config}_mrr", m["mrr"]),
        (f"eval_{config}_p50_s", m["p50"]), (f"eval_{config}_p95_s", m["p95"]),
        (f"eval_{config}_page_offset", offset),
    ]
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(["date", "commit", "metric", "value", "command"])
        for name, val in rows:
            w.writerow([today, commit, name, round(val, 4), command])


def diagnostics(results: list[dict], qs: list[dict]) -> dict[str, int]:
    """收到幾個 chunk、其中幾個出自指定檔、幾個有整數 page；用來分辨「真的沒命中」和「格式對不上」。"""
    total = named = paged = 0
    for r, q in zip(results, qs):
        mds = ((r or {}).get("metadatas") or [[]])[0] or []
        total += len(mds)
        ch = ranked_chunks(r, q["source"]["file"])
        named += len(ch)
        paged += sum(p is not None for _, p in ch)
    return {"chunks": total, "named": named, "paged": paged}


def evaluate(qs, search, k, repeat, page_offset, sample, seed, warmup=0):
    """回傳 (摘要 dict, 逐題名次, 需人審題號, 各次重跑是否一致)。search(query, k) 回傳 API 結果 dict。"""
    runs = []
    for i in range(repeat):
        results, lats = run_once(qs, search, k, warmup if i == 0 else 0)
        off, rec, tie = (page_offset, {}, False) if page_offset is not None else choose_offset(results, qs, k)
        ranks = [first_hit(r, q, k, off) for r, q in zip(results, qs)]
        runs.append((ranks, lats, off, rec, tie, diagnostics(results, qs)))
    stable = all(r[0] == runs[0][0] for r in runs) and all(r[2] == runs[0][2] for r in runs)
    ranks, lats, off, rec, tie, diag = runs[0]
    m = metrics_of(ranks, [x for r in runs for x in r[1]])
    close = bool(rec) and abs(rec[0] - rec[1]) * len(qs) <= 2  # 兩種偏移只差 2 題以內
    summary = {"metrics": m, "offset": off, "offset_recall": rec, "offset_tie": tie, "offset_close": close, "diag": diag}
    return summary, ranks, triage(qs, ranks, sample, seed), stable


def _positive(s: str) -> int:
    try:
        v = int(s)
    except ValueError:
        v = 0
    if v < 1:
        raise argparse.ArgumentTypeError("需為正整數")
    return v


def main(argv=None, search=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--collection", help="知識庫 id（正式環境用）；測試時可省略")
    ap.add_argument("--config", default="baseline", help="設定名，會寫進 metrics 的指標名稱")
    ap.add_argument("--k", type=_positive, default=5)
    ap.add_argument("--page-offset", type=int, choices=[0, 1], help="固定頁碼偏移；不指定就自動校準（只有第一次用，之後請固定）")
    ap.add_argument("--repeat", type=_positive, default=1)
    ap.add_argument("--warmup", type=int, default=2, help="先送幾題暖機（不計入）；0 表示不暖機")
    ap.add_argument("--sample", type=int, default=5, help="命中題的抽樣數")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--metrics", default=str(ROOT / "02_data" / "metrics.csv"))
    ap.add_argument("--no-metrics", action="store_true", help="不寫 metrics.csv")
    ap.add_argument("--triage-out")
    ap.add_argument("--base-url", default=os.environ.get("OWUI_BASE_URL", "http://127.0.0.1:3000"))
    a = ap.parse_args(argv)

    qs = [json.loads(x) for x in Path(a.jsonl).read_text(encoding="utf-8").splitlines() if x.strip()]
    if not qs:
        sys.exit(f"{a.jsonl} 沒有任何題目。")
    cfg: dict = {}
    if search is None:
        u = urllib.parse.urlparse(a.base_url)
        if u.scheme != "http" or u.hostname not in ("localhost", "127.0.0.1") or "@" in a.base_url:
            sys.exit(f"--base-url 只允許本機位址，避免 API key 送到其他主機：{a.base_url}")
        key = os.environ.get("OWUI_API_KEY", "").strip()
        if not key:
            sys.exit("找不到環境變數 OWUI_API_KEY。請先在 Open WebUI 產生 API key 並設定。")
        if not a.collection:
            sys.exit("請用 --collection 指定知識庫 id。")
        search = make_search(a.base_url, key, a.collection)
        cfg = effective_config(a.base_url, key)
        print("目前生效的檢索設定：" + (", ".join(f"{k_}={v}" for k_, v in sorted(cfg.items())) or "讀不到（需管理員 key，或欄位名不同）"))

    summary, ranks, need_review, stable = evaluate(qs, search, a.k, a.repeat, a.page_offset, a.sample, a.seed, a.warmup)
    d = summary["diag"]
    print(f"診斷：共收到 {d['chunks']} 個 chunk，其中 {d['named']} 個出自題目指定的檔案，{d['paged']} 個帶整數 page")
    if d["chunks"] == 0 or d["named"] == 0 or d["paged"] == 0:
        sys.exit("沒有任何可比對的結果（知識庫 id 錯、檔名對不上或回傳沒有 page）。這不是檢索分數 0，不寫入 metrics。")
    m = summary["metrics"]
    if summary["offset_recall"]:
        tie = "，兩者打平，請人工確認基準" if summary["offset_tie"] else ("，兩者只差 2 題以內，請人工確認基準" if summary["offset_close"] else "")
        how = f"（recall 偏移0={summary['offset_recall'][0]:.3f}、偏移1={summary['offset_recall'][1]:.3f}{tie}）"
    else:
        how = "（已固定）"
    print(f"題數 {len(qs)}｜k={a.k}｜頁碼偏移 {summary['offset']}{how}")
    print(f"recall@{a.k} = {m['recall']:.3f}｜MRR = {m['mrr']:.3f}｜p50 = {m['p50']:.2f}s｜p95 = {m['p95']:.2f}s")
    for q, r in zip(qs, ranks):
        print(f"  {q['id']} {'命中 第%d名' % r if r else '未命中'}")
    print(f"需人審 {len(need_review)} 題：{','.join(need_review)}")
    if a.repeat > 1:
        print("重跑一致" if stable else "⚠ 重跑結果不一致（同設定逐題命中名次不同）")
    if a.triage_out:
        Path(a.triage_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.triage_out).write_text(",".join(need_review), encoding="utf-8")
    if not stable:
        return 2  # 不穩定的結果不寫入 metrics
    if not a.no_metrics:
        cmd = "py -3.10 -I scripts/owui_eval.py " + " ".join(argv or sys.argv[1:])
        if cfg:
            cmd += " # 生效設定：" + ";".join(f"{k_}={v}" for k_, v in sorted(cfg.items()))
        append_metrics(Path(a.metrics), a.config, a.k, m, summary["offset"], cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
