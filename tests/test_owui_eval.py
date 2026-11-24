"""scripts/owui_eval.py 的驗收測試：以假的檢索結果驗證指標、頁碼校準、人審分流與可重現檢查。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import owui_eval as ev  # noqa: E402

F = "doc.pdf"


def q(qid, pages, file=F):
    return {"id": qid, "question": f"問題{qid}", "source": {"file": file, "page": pages[0], "pages": pages}}


def res(*chunks):
    """chunks: (檔名, page)，依名次排列。"""
    return {"metadatas": [[{"name": n, "page": p} for n, p in chunks]]}


def test_ranked_chunks_match_name_or_source_and_keep_global_rank():
    r = {"metadatas": [[{"name": "other.pdf", "page": 1}, {"source": "/x/y/doc.pdf", "page": 3}, {"name": F, "page": None}]]}
    assert ev.ranked_chunks(r, F) == [(2, 3), (3, None)]


def test_first_hit_respects_k_and_offset():
    r = res(("a.pdf", 1), ("a.pdf", 2), (F, 4))  # doc.pdf 的第 3 名，page=4（0 起算）
    qq = q("P1", [5])  # 實際第 5 頁（1 起算）
    assert ev.first_hit(r, qq, 5, 1) == 3
    assert ev.first_hit(r, qq, 5, 0) is None
    assert ev.first_hit(r, qq, 2, 1) is None  # k 縮小，名次 3 不算


def test_offset_calibration_picks_zero_or_one_based():
    qs = [q("A", [3]), q("B", [7]), q("C", [10])]
    zero_based = [res((F, 2)), res((F, 6)), res((F, 9))]  # page 比實際頁少 1
    one_based = [res((F, 3)), res((F, 7)), res((F, 10))]
    assert ev.choose_offset(zero_based, qs, 5)[0] == 1
    assert ev.choose_offset(one_based, qs, 5)[0] == 0
    off, rec, tie = ev.choose_offset([res((F, 99))] * 3, qs, 5)
    assert (off, tie) == (0, True) and rec == {0: 0.0, 1: 0.0}  # 全沒中：打平並標示


def test_metrics_recall_mrr_and_percentiles():
    m = ev.metrics_of([1, 2, None, 4], [1.0, 2.0, 3.0, 4.0])
    assert m["recall"] == 0.75
    assert abs(m["mrr"] - (1 + 1 / 2 + 1 / 4) / 4) < 1e-9
    assert (m["p50"], m["p95"]) == (2.0, 4.0)


def test_triage_includes_every_miss_and_is_seeded():
    qs = [q(f"P{i:02d}", [1]) for i in range(1, 21)]
    ranks = [None if i in (3, 8) else 1 for i in range(1, 21)]
    a = ev.triage(qs, ranks, 5, seed=1)
    assert {"P03", "P08"} <= set(a)
    assert len(a) == 7  # 2 題未命中 ＋ 5 題抽樣
    assert a == ev.triage(qs, ranks, 5, seed=1)  # 同 seed 相同
    assert a != ev.triage(qs, ranks, 5, seed=2)  # 換 seed 抽樣會變


def test_wrong_page_in_question_shows_up_as_miss_and_in_triage():
    qs = [q("P1", [4]), q("P2", [9])]  # P2 的頁碼被改錯（實際在第 4 頁）
    search = lambda text, k: res((F, 4))  # noqa: E731
    summary, ranks, need, stable = ev.evaluate(qs, search, 5, 1, 0, 1, 1)
    assert ranks == [1, None] and summary["metrics"]["recall"] == 0.5
    assert "P2" in need and stable


def test_smaller_k_lowers_recall():
    qs = [q("P1", [4])]
    search = lambda text, k: res(("a.pdf", 1), ("a.pdf", 2), (F, 4))  # noqa: E731
    assert ev.evaluate(qs, search, 5, 1, 0, 1, 1)[0]["metrics"]["recall"] == 1.0
    assert ev.evaluate(qs, search, 2, 1, 0, 1, 1)[0]["metrics"]["recall"] == 0.0


def test_repeat_detects_unstable_results():
    qs = [q("P1", [4])]
    calls = {"n": 0}

    def flaky(text, k):
        calls["n"] += 1
        return res((F, 4)) if calls["n"] % 2 else res((F, 5))

    assert ev.evaluate(qs, flaky, 5, 2, 0, 1, 1)[3] is False
    assert ev.evaluate(qs, lambda t, k: res((F, 4)), 5, 2, 0, 1, 1)[3] is True


def test_cli_writes_metrics_and_triage_and_exit_codes(tmp_path):
    jl = tmp_path / "q.jsonl"
    jl.write_text("\n".join(json.dumps(x) for x in [q("P1", [4]), q("P2", [9])]) + "\n", encoding="utf-8")
    out, tri = tmp_path / "m.csv", tmp_path / "t.txt"
    rc = ev.main(["--jsonl", str(jl), "--metrics", str(out), "--triage-out", str(tri), "--repeat", "2", "--page-offset", "0", "--warmup", "0"],
                 search=lambda t, k: res((F, 4)))
    assert rc == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "date,commit,metric,value,command"
    assert any(",eval_baseline_recall@5,0.5," in x for x in lines)
    assert tri.read_text(encoding="utf-8") == "P1,P2"
    n = {"i": 0}

    def flaky(t, k):
        n["i"] += 1
        return res((F, 9 if ((n["i"] - 1) // 2) % 2 == 0 else 4))  # 每 2 次呼叫（一輪）換一種結果

    assert ev.main(["--jsonl", str(jl), "--no-metrics", "--repeat", "2", "--page-offset", "0", "--warmup", "0"], search=flaky) == 2


# ---- 審查後補的測試 ----

def test_ranked_chunks_with_realistic_and_empty_metadata():
    r = {"metadatas": [[{"name": F, "source": F, "file_id": "x", "page": 0}, {"name": F}, None]]}
    assert ev.ranked_chunks(r, F) == [(1, 0), (2, None)]
    for empty in ({"metadatas": [[]]}, {"metadatas": None}, {}, None):
        assert ev.ranked_chunks(empty, F) == []


def test_auto_calibration_path_picks_offset_one():
    qs = [q(f"Q{i}", [i + 3]) for i in range(6)]
    answers = {f"問題Q{i}": res((F, i + 2)) for i in range(6)}  # page 比實際頁少 1（0 起算）
    summary, ranks, _, _ = ev.evaluate(qs, lambda t, k: answers[t], 5, 2, None, 1, 1)
    assert summary["offset"] == 1 and summary["metrics"]["recall"] == 1.0
    assert summary["offset_recall"] == {0: 0.0, 1: 1.0} and summary["offset_close"] is False
    # 只有 2 題時，兩種偏移只差 2 題，要被標為「接近」
    small = ev.evaluate(qs[:2], lambda t, k: answers[t], 5, 1, None, 1, 1)[0]
    assert small["offset"] == 1 and small["offset_close"] is True


def test_warmup_not_counted_in_latency_or_results():
    calls = []
    qs = [q("P1", [4]), q("P2", [4])]
    ev.evaluate(qs, lambda t, k: calls.append(t) or res((F, 4)), 5, 1, 0, 1, 1, warmup=2)
    assert len(calls) == 4  # 2 次暖機 ＋ 2 題


def test_empty_results_exit_without_writing_metrics(tmp_path):
    jl = tmp_path / "q.jsonl"
    jl.write_text(json.dumps(q("P1", [4])) + "\n", encoding="utf-8")
    out = tmp_path / "m.csv"
    import pytest
    for bad in ({"metadatas": [[]]}, res(("other.pdf", 4)), {"metadatas": [[{"name": F}]]}):  # 空、檔名不符、沒有 page
        with pytest.raises(SystemExit) as e:
            ev.main(["--jsonl", str(jl), "--metrics", str(out), "--page-offset", "0", "--warmup", "0"], search=lambda t, k, b=bad: b)
        assert "不寫入 metrics" in str(e.value)
    assert not out.exists()


def test_unstable_run_does_not_write_metrics(tmp_path):
    jl = tmp_path / "q.jsonl"
    jl.write_text(json.dumps(q("P1", [4])) + "\n", encoding="utf-8")
    out = tmp_path / "m.csv"
    n = {"i": 0}

    def flaky(t, k):
        n["i"] += 1
        return res((F, 4 if n["i"] == 1 else 9))

    assert ev.main(["--jsonl", str(jl), "--metrics", str(out), "--repeat", "2", "--page-offset", "0", "--warmup", "0"], search=flaky) == 2
    assert not out.exists()


def test_cli_rejects_non_positive_k_repeat_and_empty_question_set(tmp_path):
    import pytest
    jl = tmp_path / "q.jsonl"
    jl.write_text(json.dumps(q("P1", [4])) + "\n", encoding="utf-8")
    for extra in (["--k", "0"], ["--repeat", "0"], ["--k", "abc"]):
        with pytest.raises(SystemExit):
            ev.main(["--jsonl", str(jl), "--no-metrics"] + extra, search=lambda t, k: res((F, 4)))
    empty = tmp_path / "e.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        ev.main(["--jsonl", str(empty), "--no-metrics"], search=lambda t, k: res((F, 4)))


def test_base_url_whitelist_and_missing_key(tmp_path, monkeypatch, capsys):
    import pytest
    jl = tmp_path / "q.jsonl"
    jl.write_text(json.dumps(q("P1", [4])) + "\n", encoding="utf-8")
    monkeypatch.setenv("OWUI_API_KEY", "SECRET-KEY-123")
    for url in ("http://example.com:3000", "https://localhost:3000", "http://user@localhost:3000"):
        with pytest.raises(SystemExit) as e:
            ev.main(["--jsonl", str(jl), "--collection", "c", "--base-url", url, "--no-metrics"])
        assert "只允許本機位址" in str(e.value) and "SECRET-KEY-123" not in str(e.value)
    monkeypatch.delenv("OWUI_API_KEY")
    with pytest.raises(SystemExit) as e:
        ev.main(["--jsonl", str(jl), "--collection", "c", "--base-url", "http://127.0.0.1:3000", "--no-metrics"])
    assert "OWUI_API_KEY" in str(e.value)


def test_http_layer_request_shape_no_proxy_no_redirect_and_key_not_leaked(monkeypatch, capsys, tmp_path):
    import urllib.request
    seen = {}

    class FakeResp:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self.body).encode()

    class FakeOpener:
        def open(self, req, timeout=None):
            seen.setdefault("reqs", []).append(req)
            if req.full_url.endswith("/api/v1/retrieval/config"):
                return FakeResp({"RAG_EMBEDDING_MODEL": "m", "ENABLE_RAG_HYBRID_SEARCH": False, "RAG_OPENAI_API_KEY": "SECRET-KEY-123", "top_k": 5})
            return FakeResp(res((F, 4)))

    real_opener = ev._opener
    monkeypatch.setattr(ev, "_opener", lambda: FakeOpener())
    monkeypatch.setenv("OWUI_API_KEY", "SECRET-KEY-123")
    jl = tmp_path / "q.jsonl"
    jl.write_text(json.dumps(q("P1", [4])) + "\n", encoding="utf-8")
    out = tmp_path / "m.csv"
    rc = ev.main(["--jsonl", str(jl), "--collection", "kb-1", "--metrics", str(out), "--page-offset", "0", "--warmup", "0"])
    assert rc == 0
    post = [r for r in seen["reqs"] if r.get_method() == "POST"][0]
    body = json.loads(post.data)
    assert post.full_url == "http://127.0.0.1:3000/api/v1/retrieval/query/collection"
    assert body == {"collection_names": ["kb-1"], "query": "問題P1", "k": 5}  # 沒有 hybrid 欄位
    assert post.get_header("Authorization") == "Bearer SECRET-KEY-123"
    text = capsys.readouterr().out + out.read_text(encoding="utf-8")
    assert "SECRET-KEY-123" not in text  # key 不出現在輸出與 metrics（設定中名稱含 key 的欄位也被排除）
    assert "ENABLE_RAG_HYBRID_SEARCH=False" in text and "RAG_EMBEDDING_MODEL=m" in text
    # 真正的 opener：沒有代理、重新導向被拒
    monkeypatch.setenv("HTTP_PROXY", "http://evil-proxy:8080")  # 即使系統設了代理，也不能經過它
    op = real_opener()
    # 空的 ProxyHandler 不會被保留在 handlers 內，但它的存在會阻止預設代理；所以檢查沒有任何帶代理設定的 handler
    assert not any(getattr(h, "proxies", None) for h in op.handlers)
    assert ev._NoRedirect().redirect_request(None, None, 302, "", {}, "http://evil/") is None


def test_http_error_exits_with_status(monkeypatch):
    import urllib.error
    import pytest

    class Boom:
        def open(self, req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 403, "no", {}, __import__("io").BytesIO(b"denied"))

    monkeypatch.setattr(ev, "_opener", lambda: Boom())
    with pytest.raises(SystemExit) as e:
        ev._call("http://127.0.0.1:3000", "k", "POST", "/x", {})
    assert "403" in str(e.value)


def test_review_sheet_subset_header_ids_file_and_empty(tmp_path):
    import pytest
    import make_eval_review_sheet as rs
    txt = tmp_path / "txt"
    txt.mkdir()
    (txt / "doc.txt").write_text("=== page 1 ===\nalpha line\nbeta line\n=== page 2 ===\ngamma line", encoding="utf-8")
    rows = [
        {"id": "P1", "type": "text", "question": "q1", "answer_points": ["a"], "source": {"file": F, "page": 1, "pages": [1], "section": "s", "anchor": "alpha line"}},
        {"id": "P2", "type": "text", "question": "q2", "answer_points": ["b"], "source": {"file": F, "page": 2, "pages": [2], "section": "s", "anchor": "gamma line"}},
    ]
    jl = tmp_path / "q.jsonl"
    jl.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = tmp_path / "o.md"
    assert rs.main(str(jl), str(txt), str(out)) == 0
    assert "全部勾完" in out.read_text(encoding="utf-8")
    ids = tmp_path / "ids.txt"
    ids.write_text("P2\n", encoding="utf-8")  # 換行分隔也要能讀
    assert rs.main(str(jl), str(txt), str(out), str(ids)) == 0
    t = out.read_text(encoding="utf-8")
    assert "這是子集（1/2 題）" in t and "## P2" in t and "## P1" not in t
    ids.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        rs.main(str(jl), str(txt), str(out), str(ids))


def test_replay_mode_uses_recorded_results_latency_and_repeat(tmp_path):
    qs = [q("P1", [4]), q("P2", [9])]
    jl = tmp_path / "q.jsonl"
    jl.write_text("\n".join(json.dumps(x) for x in qs) + "\n", encoding="utf-8")
    run = [{"sec": 1.5, **res((F, 3))}, {"sec": 2.5, **res((F, 8))}]  # page 0 起算：實際第 4、9 頁都命中
    rp = tmp_path / "r.json"
    rp.write_text(json.dumps({"config": {"TOP_K": 5}, "runs": [run, run]}), encoding="utf-8")
    out = tmp_path / "m.csv"
    rc = ev.main(["--jsonl", str(jl), "--replay", str(rp), "--metrics", str(out)])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert ",eval_baseline_recall@5,1.0," in text and ",eval_baseline_page_offset,1," in text
    assert ",eval_baseline_p50_s,1.5," in text and ",eval_baseline_p95_s,2.5," in text  # 用錄製的延遲
    assert "TOP_K=5" in text  # 生效設定記進 command 欄


def test_replay_rejects_wrong_question_count_and_detects_unstable_runs(tmp_path):
    import pytest
    qs = [q("P1", [4])]
    jl = tmp_path / "q.jsonl"
    jl.write_text(json.dumps(qs[0]) + "\n", encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"runs": [[{"sec": 1, **res((F, 3))}, {"sec": 1, **res((F, 3))}]]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        ev.main(["--jsonl", str(jl), "--replay", str(bad), "--no-metrics"])
    unstable = tmp_path / "u.json"
    unstable.write_text(json.dumps({"runs": [[{"sec": 1, **res((F, 3))}], [{"sec": 1, **res((F, 8))}]]}), encoding="utf-8")
    assert ev.main(["--jsonl", str(jl), "--replay", str(unstable), "--no-metrics"]) == 2
