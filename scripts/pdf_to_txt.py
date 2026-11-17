"""把 PDF 逐頁抽成純文字，每頁以「=== page N ===」分隔（N 為 PDF 實體頁，從 1 起算）。

本機 py -3.10 沒有 pypdf，用 Open WebUI 映像（內含 pypdf）跑一次性容器，PDF 唯讀掛載：
    MSYS_NO_PATHCONV=1 docker run --rm --entrypoint python \
      -v D:/local-ai-agent/corpus/public_winnipeg_415-2025:/in:ro -v <輸出資料夾>:/out \
      -v D:/01_Workflow/local-ai-agent/scripts:/scripts:ro <open-webui 映像> -I /scripts/pdf_to_txt.py /in /out
"""
import sys
from pathlib import Path

from pypdf import PdfReader


def main(src: str, dst: str) -> int:
    out = Path(dst)
    out.mkdir(parents=True, exist_ok=True)
    for pdf in sorted(Path(src).glob("*.pdf")):
        parts = [f"=== page {i} ===\n{page.extract_text() or ''}" for i, page in enumerate(PdfReader(pdf).pages, 1)]
        # 頁與頁之間以換行＋換頁字元（\f）分隔，檔尾不加換行
        (out / (pdf.stem + ".txt")).write_text("\n\f".join(parts), encoding="utf-8", newline="\n")
        print(pdf.name, len(parts), "頁")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:3]))
