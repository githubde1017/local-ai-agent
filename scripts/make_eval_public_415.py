"""產生公開語料（Winnipeg Tender 415-2025）的評測題草稿；頁碼由錨點在抽出文字中定位，找不到就失敗。

用法：py -3.10 -I scripts/make_eval_public_415.py <pypdf 抽出的 txt 資料夾> 03_docs/eval/public_415-2025_draft.jsonl
txt 檔名與 PDF 相同、副檔名 .txt，每頁以「=== page N ===」分隔。錨點以 = 開頭表示整行完全相符。
txt 由 scripts/pdf_to_txt.py 產生。
頁碼慣例：PDF 實體頁、從 1 起算（不是頁面上印的「Page x of 47」）。source.page 是主要出處，
source.pages 是所有算正確的頁（跨站題有多頁），評測 recall 時任一頁命中即可。
Open WebUI 檢索結果的 page metadata 是否從 0 起算，寫評測腳本時要先實測再換算。
所有題目 reviewed=false，David 審過才改 true。
"""
import json
import re
import sys
from pathlib import Path

TXT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
T, A, B = "415-2025_Tender.pdf", "415-2025_Appendix_A_IO_Lists.pdf", "415-2025_Appendix_B_Equipment_Lists.pdf"

# (類型, 問題, 答案要點, 檔名, 錨點序列（依序尋找，最後一個所在頁為答案頁）, 章節)
Q = [
    ("text", "這份招標的合約名稱是什麼？", ["Chlorine Ventilation Upgrades at Regional Pumping Stations（原文拼成 VENTIALTION）"], T, ["B1.1 CHLORINE"], "B1.1"),
    ("number", "投標截止時間是什麼時候？", ["2025-06-25 中午 12:00（溫尼伯時間）", "可由 addendum 延後"], T, ["B2.1 The Submission Deadline is"], "B2.1"),
    ("text", "工程範圍涵蓋哪幾座加壓站？", ["Hurst、MacLean、McPhillips 三座 Regional Pumping Station 的加氯房"], T, ["D3.1 The Work to be done"], "D3.1"),
    ("number", "合約可用經費是多少？", ["CAD 4,850,000（含 MRST）"], T, ["D3.4 The funds available"], "D3.4"),
    ("number", "Substantial Performance 的期限？", ["2027-05-21"], T, ["D24.1 The Contractor shall achieve Substantial"], "D24.1"),
    ("number", "Total Performance 的期限？", ["2027-06-25"], T, ["D25.1 The Contractor shall achieve Total"], "D25.1"),
    ("number", "設備 shop drawing 審查這個關鍵階段要在何時前完成？", ["2025-09-19 之前"], T, ["Shop drawing review of all equipment: Prior"], "D23.1(a)"),
    ("number", "未達 Substantial Performance 期限，每個工作天的違約金是多少？", ["CAD 1,000／工作天"], T, ["D26. LIQUIDATED DAMAGES", "(b) Substantial Performance"], "D26.1(b)"),
    ("number", "shop drawing 審查逾期的違約金是多少？", ["CAD 250／工作天"], T, ["D26. LIQUIDATED DAMAGES", "two hundred fifty dollars"], "D26.1(a)"),
    ("text", "保固期多長、從何時起算？LED 燈具有不同嗎？", ["Total Performance 起 2 年", "LED 燈具 5 年"], T, ["D34.1 Notwithstanding C13.2"], "D34.1"),
    ("number", "押標金（bid security）至少要多少？形式為何？", ["Total Bid Price 的 10%", "數位 bid bond（Form G1）"], T, ["B14.1 The Bidder shall include"], "B14.1"),
    ("text", "發現招標文件有錯誤或疑義，最晚何時要提出？", ["截止日前至少 5 個 Business Days，向 Contract Administrator 提出"], T, ["B4.2 If the Bidder finds errors"], "B4.2"),
    ("number", "加壓站可以在什麼時段臨時停機？每次最長多久？", ["23:30–05:00", "每次最多 5.5 小時", "白天一律不准停"], T, ["E13.7.1 Temporary shutdowns"], "E13.7.1"),
    ("number", "停機計畫要提前多久提交？", ["至少 14 個 Business Days"], T, ["E13.5 Prepare and submit shutdown plans"], "E13.5"),
    ("text", "可以同時讓兩座加壓站停機嗎？", ["不行，任何情況都不能同時停多座站", "停機前施工排程須經 Contract Administrator 核准"], T, ["can multiple stations be taken"], "E13.2"),
    ("number", "承包商造成非計畫停機，可能被收多少費用？", ["CAD 2,000–10,000（可歸責時）", "另須自費緊急修復"], T, ["E13.7.4 In the event"], "E13.7.4"),
    ("number", "因承包商工法導致停機次數過多，罰則是什麼？", ["每小時 CAD 500，自進度款扣除"], T, ["E13.7.8 If an unreasonable number"], "E13.7.8"),
    ("text", "MacLean 站和 McPhillips 站在控制盤的工作內容有什麼不同？", ["MacLean：新設 HVAC PLC 盤並新做 HMI 畫面", "McPhillips：新設 remote I/O 盤，在既有 HVAC PLC 的 HMI 加畫面"], T, ["D3.2.1 MacLean", "(h) the supply and installation of an HVAC PLC panel"], "D3.2.1(h)(i)、D3.2.2(j)(k)"),
    ("text", "哪一座站要新設火警系統？", ["Hurst（並拆除既有火警系統）"], T, ["D3.2.3 Hurst", "(q) supply and installation of a new fire alarm"], "D3.2.3(q)"),
    ("text", "McPhillips 站的 tonner room 補氣空調機有幾台、裝在哪？", ["兩台，屋頂型（rooftop）"], T, ["D3.2.2 McPhillips", "(ii) Two new rooftop make up air unit"], "D3.2.2(a)(ii)"),
    ("text", "加氯房既有插座與開關要換成什麼等級？", ["Class 2（NEMA 4X）危險區分類"], T, ["(e) replace all existing receptacles"], "D3.2.1(e)"),
    ("review", "動員與撤場（Mobilization and Demobilization）的付款條件，和本案工作內容一致嗎？", ["不一致：付款節點寫的是下水道清淤與 CIPP 內襯施工", "本案是加氯房通風改善，疑為範本遺留，應於截止前提出澄清"], T, ["E5.2.1 Mobilization and Demobilization", "sewer cleaning and preparation"], "E5.2.1(b)–(d)"),
    ("tag", "MacLean 站的 AIT-C6903-1 接在哪個 PLC 位址？是什麼訊號？", ["PLC-M806，rack 0，slot 5，point 0", "AI 0-20mA 隔離", "加氯設備室氯氣濃度"], A, ["Maclean", "=AIT-C6903-1"], "Maclean CP-M826"),
    ("tag", "SCBR-C670.Flt 的訊號類型與狀態定義？", ["DI 24VDC，fail-safe", "0 = ALARM，1 = NORMAL", "洗氣塔故障警報"], A, ["Maclean", "=SCBR-C670.Flt"], "Maclean CP-M826"),
    ("tag", "McPhillips 與 Hurst 站的 IO 接在哪個控制器、哪面盤？MacLean 呢？", ["McPhillips、Hurst：RIO-C806，盤 CP-C827", "MacLean：PLC-M806，盤 CP-M826", "Hurst 另有 FACP-M922.Trouble／.Alarm 2 點接在既有盤 CP-M826 的 PLC-M806"], A, ["McPhillips", "=RIO-C806"], "McPhillips CP-C827"),
    ("tag", "緊急沖淋 U-C5301.FS 的狀態定義？各站描述有沒有差異？", ["DI 24VDC，0 = NO FLOW，1 = FLOW", "McPhillips／Hurst 描述多了 TONNER TOOM（ROOM 的錯字）"], A, ["McPhillips", "=U-C5301.FS"], "McPhillips CP-C827"),
    ("review", "IO List 中 EF-C640.Flt 這個點有沒有問題？", ["tag 是 EF-C640，描述卻寫 EXHAUST FAN EF-C641 FAULT ALARM", "三站都一樣，需確認是 tag 還是描述錯"], A, ["Maclean", "=EF-C640.Flt"], "三站 slot 2 point 14"),
    ("table", "洗氣塔 SCBR-C670 的電氣規格？需要訓練嗎？", ["480V、3ɸ、3W、40HP", "需要訓練、需 lamacoid、需 shop drawing"], B, ["Maclean", "=SCBR-C670"], "Maclean，圖號 1-0630M-E0024-001"),
    ("table", "洗氣塔的饋線斷路器與變壓器規格？", ["CB-C670：90A 3P", "XFMR-C670：600/480V、3ɸ、75kVA 自耦變壓器"], B, ["Maclean", "=CB-C670"], "Maclean，圖號 1-0630M-E0024／E0073"),
    ("review", "EF-C640 排風機在三座站的規格一樣嗎？", ["MacLean：600V、3ɸ、1.5HP、2.4 FLA", "McPhillips：120V、3ɸ、0.25HP、5.8 FLA", "Hurst：120V、3ɸ、13.8 FLA（未標 HP）", "120V 三相不常見，建議確認"], B, ["McPhillips", "=EF-C640"], "McPhillips，圖號 1-0640C-E0020-001"),
]


def locate(lines, anchors):
    i = 0
    for a in anchors:
        hit = (lambda L: L.strip() == a[1:]) if a.startswith("=") else (lambda L: a.lower() in L.lower())
        while i < len(lines) and not hit(lines[i]):
            i += 1
        if i == len(lines):
            raise SystemExit(f"找不到錨點：{anchors}")
    page = None
    for j in range(i, -1, -1):
        m = re.match(r"=== page (\d+) ===", lines[j])
        if m:
            page = int(m.group(1))
            break
    return page, lines[i].strip()


# 跨站或跨段落的題目：其他同樣算正確的頁（評測 recall 時任一頁命中即可）
ALSO = {
    "P18": [["D3.2.2 McPhillips", "(j) the supply and installation new remote I/O panel"]],
    "P25": [["Maclean", "=PLC-M806"], ["Hurst - Existing Control Panel CP-M826"]],
    "P26": [["Hurst", "=U-C5301.FS"]],
    "P27": [["McPhillips", "=EF-C640.Flt"], ["Hurst", "=EF-C640.Flt"]],
    "P30": [["Maclean", "=EF-C640"], ["Hurst", "=EF-C640"]],
}


def main() -> int:
    from collections import Counter

    cache = {}
    out = []
    for n, (typ, q, ans, f, anchors, sec) in enumerate(Q, 1):
        qid = f"P{n:02d}"
        lines = cache.setdefault(f, (TXT / f.replace(".pdf", ".txt")).read_text(encoding="utf-8").splitlines())
        page, line = locate(lines, anchors)
        pages = sorted({page} | {locate(lines, a)[0] for a in ALSO.get(qid, [])})
        out.append({
            "id": qid, "type": typ, "question": q, "answer_points": ans,
            "source": {"file": f, "page": page, "pages": pages, "section": sec, "anchor": line[:120]},
            "reviewed": False,
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out), encoding="utf-8")
    print(len(out), "題", Counter(x["type"] for x in out))
    for x in out:
        s = x["source"]
        print(x["id"], x["type"], s["file"][9:20], "p", s["pages"], "|", s["anchor"][:60])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
