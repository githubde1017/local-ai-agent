"""Open WebUI 資料盤點（唯讀）。

把 webui.db（含 WAL）複製到暫存目錄再查詢，不碰正在執行中的資料庫；
chroma.sqlite3 以唯讀模式開啟。輸出 JSON，供驗收比對。

用法：
    py -3.10 scripts/owui_audit.py [--data D:/local-ai-agent/open-webui] [--knowledge 噪音]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ORPHAN_FILE_PREFIXES = ("baa836b1", "b85cb0f2")


def copy_db(data_dir: Path, tmp: Path) -> Path:
    for suffix in ("", "-wal", "-shm"):
        src = data_dir / f"webui.db{suffix}"
        if src.exists():
            shutil.copy2(src, tmp / src.name)
    return tmp / "webui.db"


def config_value(con: sqlite3.Connection, key: str):
    row = con.execute("select value from config where key=?", (key,)).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except json.JSONDecodeError:
        return row[0]


def audit(data_dir: Path, knowledge_name: str) -> dict:
    with tempfile.TemporaryDirectory() as t:
        con = sqlite3.connect(copy_db(data_dir, Path(t)))
        files = [
            {"id": fid, "filename": name}
            for fid, name in con.execute("select id, filename from file")
        ]
        knowledge = {kid: name for kid, name in con.execute("select id, name from knowledge")}
        kf_rows = con.execute("select knowledge_id, file_id from knowledge_file").fetchall()
        target_ids = [kid for kid, name in knowledge.items() if name == knowledge_name]
        func = con.execute(
            "select id, name, is_active, meta from function where id='claude_gemini'"
        ).fetchone()
        result = {
            "file_count": len(files),
            "orphan_files_present": [
                f["id"] for f in files if f["id"].startswith(ORPHAN_FILE_PREFIXES)
            ],
            "knowledge_file_dangling": [
                {"knowledge_id": k, "file_id": f} for k, f in kf_rows if k not in knowledge
            ],
            "knowledge": {
                knowledge_name: {
                    "id": target_ids[0] if target_ids else None,
                    "file_count": sum(1 for k, _ in kf_rows if k in target_ids),
                }
            },
            "config": {
                k: config_value(con, k)
                for k in (
                    "openai.enable",
                    "rag.embedding_engine",
                    "rag.embedding_model",
                    "rag.enable_hybrid_search",
                    "rag.reranking_model",
                    "rag.top_k",
                    "rag.chunk_size",
                )
            },
            "pipe_claude_gemini": None
            if func is None
            else {
                "name": func[1],
                "is_active": bool(func[2]),
                "description": (json.loads(func[3] or "{}") or {}).get("description"),
            },
        }
        con.close()

    chroma = data_dir / "vector_db" / "chroma.sqlite3"
    ccon = sqlite3.connect(f"file:{chroma.as_posix()}?mode=ro", uri=True)
    collections = [
        {"name": name, "dimension": dim, "rows": rows}
        for name, dim, rows in ccon.execute(
            "select c.name, c.dimension, count(e.id) from collections c "
            "left join segments s on s.collection = c.id "
            "left join embeddings e on e.segment_id = s.id group by c.id"
        )
    ]
    ccon.close()
    result["chroma_collections"] = collections
    result["chroma_384_with_rows"] = [
        c["name"] for c in collections if c["dimension"] == 384 and c["rows"] > 0
    ]
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="D:/local-ai-agent/open-webui")
    p.add_argument("--knowledge", default="噪音")
    args = p.parse_args()
    out = audit(Path(args.data), args.knowledge)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
