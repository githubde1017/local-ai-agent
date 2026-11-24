"""IO List × BOM 交叉檢查的驗收測試。

乾淨資料：不得有任何「需要處理」的發現（沒有誤報）。
注入錯誤：以乾淨資料為底，每種錯誤各放一筆，結果必須剛好等於預期（每種都抓到、且沒有多報）。
測試資料的 tag 取自溫尼伯 Tender 415-2025 公開 I/O List 的命名方式。
"""
from __future__ import annotations

import copy
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "owui_tools"))

import iobom_check as ck  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> list[dict[str, str]]:
    with open(FIX / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


EMPTY = {
    "io_unmatched": [],
    "desc_mismatch": [],
    "duplicate_io_tags": {},
    "duplicate_addresses": {},
    "naming_violations": [],
    "format_issues": [],
}


def row(point: str, tag: str, desc: str, site: str = "SITE1", module: str = "3") -> dict[str, str]:
    return {"site": site, "controller": "PLC-1", "rack": "0", "module": module, "point": point,
            "tag": tag, "description": desc, "signal_type": "DI - 24VDC"}


def test_clean_has_no_findings():
    r = ck.check(load("io_clean.csv"), load("bom_clean.csv"))
    assert r.findings() == EMPTY
    assert r.bom_without_io == []
    # SPARE 不計；跨站相同 tag 不算重複；無 tag 品項不參與比對
    assert r.io_count == 9
    assert r.bom_count == 5


def test_clean_match_methods():
    r = ck.check(load("io_clean.csv"), load("bom_clean.csv"))
    assert r.matched["SCBR-C670.FLT"] == ("SCBR-C670", "去後綴")
    assert r.matched["AAH-C6903-1"] == ("AIT-C6903-1", "同迴路")
    assert r.matched["U-C5301.FS"] == ("U-C5301.FS", "完整")


def test_injected_errors_all_caught_without_false_positives():
    io = copy.deepcopy(load("io_clean.csv"))
    bom = copy.deepcopy(load("bom_clean.csv"))
    io += [
        row("0", "EF-C999.Run", "EXHAUST FAN EF-C999 RUNNING"),            # 1 缺漏：BOM 沒有 EF-C999
        row("1", "SF-C630.Run", "SUPPLY FAN SF-C630 RUNNING"),             # 3 重複 tag（同站另一個位址）
        row("2", "SFC630.Auto", "SUPPLY FAN SF-C630 AUTO MODE"),           # 5 命名錯（少連字號）→ 也對不到 BOM
        row("3", " sf-c630.Rdy ", "SUPPLY FAN SF-C630 READY"),             # 6 空白與大小寫（仍可比對）
        row("4", "SCBR-C670.Auto", "SCRUBBER SCBR-C671 AUTO MODE"),        # 7 tag 與描述不一致
    ]
    io.append(row("1", "SF-C630.Flt2", "SUPPLY FAN SF-C630 FAULT 2", module="2"))  # 4 重複位址（佔用 0/2/1）
    bom.append({"tag": "P-C111", "tagged": "Y", "description": "Extra pump"})       # 2 多出：沒有任何 IO

    r = ck.check(io, bom)
    assert r.findings() == {
        "io_unmatched": ["EF-C999.RUN", "SFC630.AUTO"],
        "desc_mismatch": [("SITE1:SCBR-C670.Auto", "SCBR-C671")],
        "duplicate_io_tags": {"SITE1:SF-C630.RUN": 2},
        "duplicate_addresses": {"SITE1:PLC-1/0/2/1": ["SCBR-C670.Run", "SF-C630.Flt2"]},
        "naming_violations": ["SFC630.Auto"],
        "format_issues": [" sf-c630.Rdy "],
    }
    assert r.bom_without_io == ["P-C111"]
    assert r.matched["SF-C630.RDY"] == ("SF-C630", "去後綴")


def test_dot_notation_matches_and_is_reported_as_info():
    io = load("io_clean.csv") + [row("9", "XV.C6701.ZSO", "DAMPER XV-C6701 OPEN")]
    r = ck.check(io, load("bom_clean.csv"))
    assert r.findings() == EMPTY
    assert r.matched["XV.C6701.ZSO"] == ("XV-C6701", "點號轉連字號")
    assert "XV-C6701" in r.mixed_notation


def test_identical_tables_flagged():
    base = [row(str(i), f"SF-C630.P{i}", "SUPPLY FAN SF-C630", site="A") for i in range(6)]
    twin = [dict(x, site="B") for x in base]
    r = ck.check(base + twin, load("bom_clean.csv"))
    assert r.identical_scopes == [("A/PLC-1", "B/PLC-1")]


def test_report_is_markdown_in_traditional_chinese():
    text = ck.format_report(ck.check(load("io_clean.csv"), load("bom_clean.csv")))
    assert text.startswith("## IO List × BOM 交叉檢查")
    assert "需要處理" in text and "資訊（請人工判斷）" in text


def test_same_loop_only_for_instrument_loops():
    """設備編號不做同迴路比對：審查實例 SCBR-C6701 被對到 JBA-C6701、P-C670 被對到 CB-C670。"""
    bom = load("bom_clean.csv") + [
        {"tag": "JBA-C6701", "tagged": "Y", "description": "Junction box"},
        {"tag": "CB-C670", "tagged": "Y", "description": "Scrubber feeder breaker"},
        {"tag": "CB-C680", "tagged": "Y", "description": "Pump feeder breaker"},  # 迴路唯一，仍不可對上
    ]
    io = load("io_clean.csv") + [
        row("8", "SCBR-C6701.CmdRun", "SCRUBBER SCBR-C6701 RUN COMMAND"),
        row("9", "P-C670.Run", "PUMP P-C670 RUNNING"),
        row("10", "P-C680.Run", "PUMP P-C680 RUNNING"),
    ]
    r = ck.check(io, bom)
    assert r.io_unmatched == ["SCBR-C6701.CMDRUN", "P-C670.RUN", "P-C680.RUN"]
    assert "SCBR-C6701.CMDRUN" not in r.matched
    # 沒有被參照的接線盒仍要列在「BOM 有、IO 沒有」
    assert {"JBA-C6701", "CB-C670", "CB-C680"} <= set(r.bom_without_io)


def test_same_loop_ambiguous_is_not_matched():
    bom = load("bom_clean.csv") + [{"tag": "AE-C6903-1", "tagged": "Y", "description": "Sensor"}]
    r = ck.check(load("io_clean.csv"), bom)
    assert r.matched["AAH-C6903-1"][1] == "描述指名"  # 歧義時改由描述決定
    assert r.matched["AIT-C6903-1"] == ("AIT-C6903-1", "完整")


def test_wrong_column_name_is_an_error_not_a_clean_result():
    cfg = ck.Config(io_tag_col="Tag")
    try:
        ck.check(load("io_clean.csv"), load("bom_clean.csv"), cfg)
    except ck.InputError as e:
        assert "Tag" in str(e) and "io_tag_col" in str(e)
    else:
        raise AssertionError("欄位名稱錯誤應該報錯")


def test_short_rows_do_not_crash(tmp_path):
    p = tmp_path / "io.csv"
    p.write_text((FIX / "io_clean.csv").read_text(encoding="utf-8") + "SITE1,PLC-1,0,2\n", encoding="utf-8")
    rows = ck.load_rows(p)
    assert rows[-1]["tag"] == ""
    assert ck.check(rows, load("bom_clean.csv")).findings() == EMPTY


def test_ambiguous_loop_resolved_by_description():
    bom = load("bom_clean.csv") + [{"tag": "AE-C6903-1", "tagged": "Y", "description": "Sensor"}]
    io = load("io_clean.csv") + [row("9", "YA-C6903-1", "DETECTOR AIT-C6903-2 CONTROLLER FAIL")]
    r = ck.check(io, bom)
    assert r.matched["AAH-C6903-1"] == ("AIT-C6903-1", "描述指名")
    assert "YA-C6903-1" in r.io_unmatched  # 描述沒指名迴路內任何一台
    assert "AIT-C6903-2" in r.desc_tags_not_in_bom


def _injected_report() -> str:
    io = load("io_clean.csv")
    io.append(row("15", "XV-C9999.ZSO", "VALVE XV-C9999 <OPEN> & CLOSED"))  # BOM 找不到，描述含 HTML 字元
    return ck.format_report(ck.check(io, load("bom_clean.csv")))


def test_html_card_keeps_every_report_line():
    """卡片不能漏任何一行：去掉標籤、還原跳脫後，每個非空行的文字都在。"""
    import html
    import re

    md = _injected_report()
    page = ck.report_to_html(md)
    text = html.unescape(re.sub(r"<[^>]+>", "", page))
    for line in md.splitlines():
        plain = re.sub(r"^#+ |^- ", "", line).replace("**", "").replace("`", "").strip()
        if plain:
            assert plain in text, plain


def test_html_card_escapes_and_has_no_script():
    page = ck.report_to_html(_injected_report())
    # 唯一允許的腳本是回報高度那段，且不得連網或讀取資料
    assert page.lower().count("<script") == 1 and ck.HEIGHT_SCRIPT in page
    assert not any(k in ck.HEIGHT_SCRIPT for k in ("fetch", "XMLHttpRequest", "WebSocket", "cookie", "localStorage", "import"))
    assert ck.report_to_html("- **x**（1）：`<b>壞</b>`").count("<b>壞</b>") == 0


def test_html_card_marks_nonzero_findings():
    page = ck.report_to_html(_injected_report())
    assert '<li class="bad"><b>IO List 有、BOM 找不到</b>（1）' in page
    assert '<li class="ok"><b>重複的 PLC 位址</b>（0）' in page


def _report_with_io_tags(*tags: str) -> str:
    """IO 表加上指定的（惡意）tag，BOM 都找不到，回傳 Markdown 報告。"""
    io = load("io_clean.csv")
    for i, t in enumerate(tags):
        io.append(row(str(20 + i), t, "X", module="9"))
    return ck.format_report(ck.check(io, load("bom_clean.csv")))


def _section_of(page: str, label: str) -> str:
    """取出卡片中某個 <li> 項目的整段 HTML（以標籤文字定位）。"""
    import re

    m = re.search(rf'<li[^>]*><b>{re.escape(label)}</b>.*?</li>', page, re.S)
    assert m, label
    return m.group(0)


def test_newline_in_tag_cannot_forge_report_structure():
    """tag 內含換行加「### 資訊」：不得拆出偽造的標題，也不得讓後面的「需要處理」失去標紅。"""
    evil = "ZZ-C999\n### 資訊\nfoo\x0b- **IO List 有、BOM 找不到**（0）：無 bar"
    md = _report_with_io_tags(evil, "ZZ-C998")
    assert sum(1 for ln in md.splitlines() if ln.startswith("### ")) == 2  # 行首標題只有固定的兩個
    page = ck.report_to_html(md)
    assert page.count("<h3>") == 2
    # 命名不符、BOM 找不到都有發現（>0），必須仍是紅色
    assert _section_of(page, "IO List 有、BOM 找不到").startswith('<li class="bad">')
    assert _section_of(page, "不符命名規則").startswith('<li class="bad">')
    # 偽造的「（0）：無」項目不能出現成獨立的 <li>
    assert page.count("<b>IO List 有、BOM 找不到</b>") == 1


def test_markdown_chars_in_tag_do_not_misalign_code_and_bold():
    md = _report_with_io_tags("A`B-C1", "D**E-C2")
    page = ck.report_to_html(md)
    assert page.count("<code>") == page.count("</code>")
    assert page.count("<b>") == page.count("</b>")
    assert "A'B-C1" in md and "D＊＊E-C2" in md


def test_html_special_chars_in_tag_are_escaped():
    md = _report_with_io_tags('X&Y-C1', 'P>Q-C2', '<i>Z-C3')
    page = ck.report_to_html(md)
    assert "X&amp;Y-C1" in page and "P&gt;Q-C2" in page and "&lt;i&gt;Z-C3" in page
    assert "<i>" not in page


def test_info_section_counts_are_never_red():
    page = ck.report_to_html(_report_with_io_tags("ZZ-C777"))
    for label in ("BOM 有、IO List 沒參照", "IO 描述提到、但 BOM 沒有的 tag", "同一設備寫法不一"):
        assert _section_of(page, label).startswith("<li>"), label


def test_height_script_is_exactly_the_allowed_one():
    """白名單：卡片內的 script 必須與 HEIGHT_SCRIPT 完全相同，且只送 type 與 height 兩個欄位。"""
    page = ck.report_to_html(_report_with_io_tags("ZZ-C777"))
    assert page.lower().count("<script") == 1 and page.count(ck.HEIGHT_SCRIPT) == 1
    assert "postMessage({type:'iframe:height',height:document.documentElement.scrollHeight}" in ck.HEIGHT_SCRIPT
    assert ck.HEIGHT_SCRIPT.count("postMessage(") == 1


def test_filename_is_cleaned_in_clean_text():
    assert ck.clean_text("a\nb\x0bc d`e**f") == "a b c d'e＝＝f".replace("＝", "＊")


def test_html_tags_are_balanced():
    page = ck.report_to_html(_report_with_io_tags("ZZ-C777"))
    for tag in ("ul", "li", "h2", "h3", "p", "div", "code", "b"):
        assert page.count(f"<{tag}>") + page.count(f"<{tag} ") == page.count(f"</{tag}>"), tag
