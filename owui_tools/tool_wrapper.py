

# ======================= 以下為 Open WebUI Tool 外殼 =======================
import os  # noqa: E402
from typing import Optional  # noqa: E402

from pydantic import BaseModel, Field  # noqa: E402


class Tools:
    class Valves(BaseModel):
        io_tag_col: str = Field("tag", description="IO List 的 tag 欄位名稱")
        io_desc_col: str = Field("description", description="IO List 的描述欄位名稱")
        io_addr_cols: str = Field("controller,rack,module,point", description="PLC 位址欄位（逗號分隔）")
        io_scope_cols: str = Field("site", description="分組欄位（逗號分隔，例如站點）；重複只在同組內計算")
        io_table_cols: str = Field("site,panel,controller", description="一張 IO 表的識別欄位（逗號分隔）")
        bom_tag_col: str = Field("tag", description="BOM／設備清單的 tag 欄位名稱")
        bom_tagged_col: str = Field("tagged", description="標示是否有 tag 的欄位（值為 N 的列略過）；不用就留空")
        spare_values: str = Field("SPARE", description="備用點的 tag 值（逗號分隔）")
        tag_pattern: str = Field(DEFAULT_TAG_PATTERN, description="tag 命名規則（正規表示式）")
        show_report_card: bool = Field(
            True, description="把完整報告以卡片直接顯示在回覆中（模型只負責摘要）；關閉則只回傳文字給模型"
        )

    def __init__(self):
        self.valves = self.Valves()

    def _cfg(self) -> Config:
        v = self.valves
        split = lambda s: tuple(x.strip() for x in s.split(",") if x.strip())  # noqa: E731
        return Config(
            io_tag_col=v.io_tag_col, io_desc_col=v.io_desc_col,
            io_addr_cols=split(v.io_addr_cols), io_scope_cols=split(v.io_scope_cols),
            io_table_cols=split(v.io_table_cols), bom_tag_col=v.bom_tag_col,
            bom_tagged_col=v.bom_tagged_col or None,
            spare_values=frozenset(split(v.spare_values)), tag_pattern=v.tag_pattern,
        )

    @staticmethod
    def _paths(files: list) -> list[tuple[str, str]]:
        """取出附件的本機路徑。在 Open WebUI 內執行時，只接受上傳目錄（UPLOAD_DIR）底下的檔案，
        避免請求中夾帶的任意路徑讓 Tool 讀到主機上其他檔案。"""
        try:
            from open_webui.config import UPLOAD_DIR
            from open_webui.storage.provider import Storage
        except ImportError:  # 不在 Open WebUI 內（本機測試）
            UPLOAD_DIR, Storage = None, None
        root = os.path.realpath(UPLOAD_DIR) if UPLOAD_DIR else None
        out, seen = [], set()
        for item in files or []:
            f = item.get("file", item) if isinstance(item, dict) else {}
            path = f.get("path") or (f.get("meta") or {}).get("path")
            name = f.get("filename") or item.get("name") or path
            if not path or not str(path).lower().endswith((".csv", ".xlsx", ".xlsm")):
                continue
            if Storage is not None:
                path = Storage.get_file(path)
            real = os.path.realpath(path)
            if root and os.path.commonpath([real, root]) != root:
                continue
            if real not in seen:
                seen.add(real)
                out.append((name, real))
        return out

    def check_io_bom(self, __files__: Optional[list] = None):
        """
        交叉檢查對話中附上的 IO List 與 BOM（設備清單）。附件需為 csv 或 xlsx，兩個檔案各一，
        由工具自動讀取，不需要任何參數。會自動以欄位判斷哪個是 IO List（含 PLC 位址欄位者）。
        成功時完整報告會直接顯示給使用者，回傳給你的是同一份報告供摘要。
        """
        cfg = self._cfg()
        files = self._paths(__files__)
        if len(files) != 2:
            return "請在同一則訊息附上兩個不同的檔案：IO List 與 BOM（csv 或 xlsx）。目前找到：" + (
                "、".join(clean_text(n) for n, _ in files) or "沒有可讀的附件"
            )
        tables = [(n, load_rows(p)) for n, p in files]
        is_io = [bool(rows) and all(c in rows[0] for c in cfg.io_addr_cols) for _, rows in tables]
        if is_io.count(True) != 1:
            return (
                "無法判斷哪個是 IO List：IO List 必須含有位址欄位 "
                + "、".join(cfg.io_addr_cols)
                + "（可在 Tool 設定的 io_addr_cols 調整欄位名稱）。"
            )
        (io_name, io_rows), (bom_name, bom_rows) = (
            (tables[0], tables[1]) if is_io[0] else (tables[1], tables[0])
        )
        try:
            report = format_report(check(io_rows, bom_rows, cfg))
        except InputError as e:
            return f"無法檢查：{clean_text(e)}（可在 Tool 設定調整欄位名稱）"
        text = (
            f"IO List：`{clean_text(io_name)}`（{len(io_rows)} 列）｜BOM：`{clean_text(bom_name)}`（{len(bom_rows)} 列）\n\n"
            + report
        )
        if not self.valves.show_report_card:
            return text
        try:
            from fastapi.responses import HTMLResponse
        except ImportError:  # 不在 Open WebUI 內（本機測試）
            return text
        card = HTMLResponse(report_to_html(text), headers={"Content-Disposition": "inline"})
        note = (
            "【完整報告已以卡片顯示給使用者，不要逐條重抄】請用 2～4 句繁體中文摘要：需要處理的項目各有幾筆、"
            "最值得先查的是哪些，並提醒資訊類需人工判斷。以下是同一份報告：\n\n"
        )
        return card, note + text
