"""在 Open WebUI 映像內實際執行 IO/BOM Tool（不需 API key、不碰正式資料）。

載入方式與 Open WebUI 相同（types.ModuleType ＋ sys.modules ＋ exec）。上傳目錄指向暫存資料夾，
測試檔複製進去，模擬正式上傳後的路徑；另外驗證上傳目錄以外的路徑會被拒絕。

用法（輸出建議存到 02_data）：
    MSYS_NO_PATHCONV=1 docker run --rm -e WEBUI_SECRET_KEY=throwaway -e DATA_DIR=/tmp/owui \
      -v D:/01_Workflow/local-ai-agent/owui_tools/dist:/tool:ro \
      -v D:/01_Workflow/local-ai-agent/tests/fixtures:/fx:ro \
      -v D:/local-ai-agent/corpus/public_winnipeg_415-2025:/corpus:ro \
      -v D:/01_Workflow/local-ai-agent/scripts:/scripts:ro \
      -w /app/backend --entrypoint python <open-webui 映像> -W ignore /scripts/owui_runtime_check.py
"""
import csv
import os
import shutil
import sys
import types

import openpyxl

sys.path.insert(0, "/app/backend")  # Open WebUI 套件位置（以腳本執行時 sys.path 不含工作目錄）

checks = []


def ok(name, cond, detail=""):
    checks.append(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"｜{detail}" if detail else ""))


m = types.ModuleType("tool_iobom")
sys.modules["tool_iobom"] = m
exec(open("/tool/iobom_check_tool.py", encoding="utf-8").read(), m.__dict__)
from open_webui.config import UPLOAD_DIR  # noqa: E402

os.makedirs(UPLOAD_DIR, exist_ok=True)


def upload(src, name):
    dst = os.path.join(UPLOAD_DIR, name)
    if name.endswith(".xlsx"):
        wb = openpyxl.Workbook()
        ws = wb.active
        for r in csv.reader(open(src, encoding="utf-8-sig")):
            ws.append(r)
        wb.save(dst)
    else:
        shutil.copy(src, dst)
    return {"type": "file", "file": {"path": dst, "filename": name}}


T = m.Tools()
io_csv = upload("/corpus/io_list.csv", "io_list.csv")
bom_csv = upload("/corpus/equipment_list.csv", "equipment_list.csv")
io_x = upload("/corpus/io_list.csv", "IO清單.xlsx")
bom_x = upload("/corpus/equipment_list.csv", "設備清單.xlsx")

from fastapi.responses import HTMLResponse  # noqa: E402


def run(files):
    """成功時 Tool 回傳 (HTMLResponse 卡片, 給模型的文字)；錯誤時回傳文字。這裡統一取文字。"""
    out = T.check_io_bom(__files__=files)
    return out[1] if isinstance(out, tuple) else out


raw = T.check_io_bom(__files__=[io_csv, bom_csv])
card_ok = (
    isinstance(raw, tuple) and isinstance(raw[0], HTMLResponse)
    and "inline" in raw[0].headers.get("content-disposition", "")
)
ok("成功時回傳 inline HTMLResponse 卡片＋文字", card_ok)
card_html = raw[0].body.decode("utf-8") if card_ok else ""
ok("卡片含完整「需要處理」6 項，只有回報高度的 script",
   all(k in card_html for k in ("BOM 找不到", "描述的設備編號不一致", "重複的 IO tag", "重複的 PLC 位址", "不符命名規則", "空白或大小寫"))
   and card_html.lower().count("<script") == 1 and "iframe:height" in card_html)
T.valves.show_report_card = False
ok("關閉 show_report_card 時只回傳文字", isinstance(T.check_io_bom(__files__=[io_csv, bom_csv]), str))
T.valves.show_report_card = True

csv_out = run([io_csv, bom_csv])
x_out = run([bom_x, io_x])
body = lambda s: s.split("IO List：", 1)[1].split("\n", 2)[2]  # noqa: E731
ok("公開資料 csv 產生報告", "## IO List × BOM 交叉檢查" in csv_out)
ok("xlsx（BOM 放第一個）與 csv 結果相同", body(csv_out) == body(x_out))
ok("SCBR-C6701.CMDRUN 列為 BOM 找不到（同迴路錯配已修）", "SCBR-C6701.CMDRUN" in csv_out.split("### 資訊")[0])
ok("只附一個檔會提示", "請在同一則訊息附上兩個不同的檔案" in run([io_csv]))
ok("同一個檔附兩次會提示", "請在同一則訊息附上兩個不同的檔案" in run([io_csv, io_csv]))
ok("兩個都是 BOM 會提示", "無法判斷哪個是 IO List" in run([bom_csv, bom_x]))
outside = {"type": "file", "file": {"path": "/fx/io_clean.csv", "filename": "io_clean.csv"}}
ok("上傳目錄以外的路徑被拒", "目前找到：io_list.csv" in run([io_csv, outside]))
T.valves.io_tag_col = "Tag"
ok("欄位名稱錯誤回傳說明而不是乾淨結果", "找不到欄位「Tag」" in run([io_csv, bom_csv]))
T.valves.io_tag_col = "tag"
clean = run([upload("/fx/io_clean.csv", "io_clean.csv"), upload("/fx/bom_clean.csv", "bom_clean.csv")])
ok("乾淨 fixture 零發現", clean.split("### 資訊")[0].count("（0）") == 6)
# 惡意 tag：含換行與「### 資訊」，經 Tool 外殼產生的卡片不得出現多餘標題，且「找不到」項目仍標紅
evil_path = os.path.join(UPLOAD_DIR, "io_evil.csv")
rows = list(csv.reader(open("/fx/io_clean.csv", encoding="utf-8-sig")))
NL = chr(10)
rows.append(["SITE1", "PLC-1", "0", "9", "20", "ZZ-C999" + NL + "### 資訊" + NL + "foo", "X", "DI - 24VDC"][: len(rows[0])])
with open(evil_path, "w", encoding="utf-8", newline="") as f:
    csv.writer(f).writerows(rows)
evil = T.check_io_bom(__files__=[
    {"type": "file", "file": {"path": evil_path, "filename": "io" + NL + "evil.csv"}},
    upload("/fx/bom_clean.csv", "bom_clean2.csv"),
])
evil_html = evil[0].body.decode("utf-8") if isinstance(evil, tuple) else ""
ok("惡意 tag／檔名不會偽造卡片標題，且有發現的項目仍標紅",
   isinstance(evil, tuple) and evil_html.count("<h3>") == 2 and '<li class="bad"><b>IO List 有、BOM 找不到</b>' in evil_html
   and ("io" + NL + "evil") not in evil[1])
print()
print(csv_out.split("### 資訊")[0])
print(f"{sum(checks)}/{len(checks)} 通過")
sys.exit(0 if all(checks) else 1)
