"""刪除 Open WebUI 刪檔後殘留的向量集合與懸空的 knowledge_file 列。

背景：Open WebUI 0.10.2 刪檔時呼叫 vector delete 沒帶 ids/filter，Chroma 實作會直接略過，
所以 `file-<id>` collection 會殘留；SQLite 也沒有啟用外鍵，knowledge_file 會留下懸空列。

**只能在 open-webui 容器停止時執行**，用同一顆映像的一次性容器跑：
    docker run --rm -v D:/local-ai-agent/open-webui:/app/backend/data \
      -v D:/01_Workflow/local-ai-agent/scripts:/scripts --entrypoint python <image> \
      /scripts/owui_purge_orphans.py [--apply]
不加 --apply 只預覽。
"""
from __future__ import annotations

import argparse
import sqlite3

DATA = "/app/backend/data"
ORPHAN_FILE_IDS = (
    "baa836b1-691d-41c3-96e1-472d6782041a",
    "b85cb0f2-6c74-4aa6-938f-8d84094473a8",
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    apply = p.parse_args().apply

    con = sqlite3.connect(f"{DATA}/webui.db")
    live_files = {r[0] for r in con.execute("select id from file")}
    targets = [f for f in ORPHAN_FILE_IDS if f not in live_files]
    if len(targets) != len(ORPHAN_FILE_IDS):
        raise SystemExit(f"中止：仍有孤兒檔存在於 file 表 {set(ORPHAN_FILE_IDS) - set(targets)}")

    dangling = con.execute(
        "select kf.id, kf.knowledge_id, kf.file_id from knowledge_file kf "
        "left join knowledge k on k.id = kf.knowledge_id where k.id is null"
    ).fetchall()
    print("懸空 knowledge_file：", [(r[0][:8], r[1][:8], r[2][:8]) for r in dangling])

    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=f"{DATA}/vector_db", settings=Settings(anonymized_telemetry=False)
    )
    names = {c if isinstance(c, str) else c.name for c in client.list_collections()}
    cols = [f"file-{f}" for f in targets if f"file-{f}" in names]
    for n in cols:
        print("將刪除 collection：", n, client.get_collection(n).count(), "筆")

    if not apply:
        print("預覽模式，未變更")
        return 0

    for n in cols:
        client.delete_collection(n)
        print("已刪除", n)
    with con:
        con.executemany("delete from knowledge_file where id = ?", [(r[0],) for r in dangling])
    print("已刪除懸空 knowledge_file", len(dangling), "筆")
    remaining = {c if isinstance(c, str) else c.name for c in client.list_collections()}
    print("剩餘 collection：", sorted(remaining))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
