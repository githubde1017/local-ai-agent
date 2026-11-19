# spec：Open WebUI 水處理儀控工程文件問答檢查台
版本：v0.2｜日期：2026-11-18｜repo：local-ai-agent（`D:\01_Workflow\local-ai-agent`，origin `githubde1017/local-ai-agent`）

> v0.1 → v0.2：David 於 2026-11-18 經 frontier 提案選定方案 A。Open WebUI 的定位從「噪音知識庫」改為「機密工程文件的本地問答與檢查台」。P0 清理已完成（見 `02_data/verify_20261118.md`）；原 P1–P3 的方法保留，評測對象改為 David 實際的案場文件。

## 最終目標（為什麼做）
David 處理水處理儀控案場文件（規範、P&ID 說明、IO List、BOM）時，不必把機密文件上傳雲端，也能在本機：(1) 問文件內容並得到附檔名與頁碼的答案，找不到就明說；(2) 一鍵檢查 IO List 與 BOM 的 tag 是否一致。成功的樣子：上線 4 週內每週至少使用 3 次；評測分數與檢查正確率都有紀錄可查。

## 本次任務
1. **A1 建知識庫**：David 指定 1 個案場的 3–10 份文件（含至少 1 份 IO List、1 份 BOM），建立知識庫「案場-<代號>」與對應的自訂模型。文件只放在本機 `D:\local-ai-agent\`，不進 git。
2. **A2 評測基準**：從這些文件草擬 30 題實務問題（含至少 8 題表格、數字或 tag 題），每題附標準答案要點、檔名、頁碼或工作表與列號，**由 David 審過**後定稿。寫評測腳本，透過 Open WebUI API 對知識庫檢索，算 recall@5、MRR、檢索延遲 p50/p95，寫入 `02_data/metrics.csv`；以目前設定跑 baseline。
3. **A3 檢索升級**：一次只改一項，每項重跑評測，分數沒提升就回退。候選：embedding 換 `bge-m3`、hybrid search、reranker `BAAI/bge-reranker-v2-m3`（CPU）、Markdown 標題切塊、相關度門檻＋「找不到就明說」template；表格題 recall@5 < 0.6 時加 Docling 解析。
4. **A4 IO List／BOM 交叉檢查 Tool**：寫成 Open WebUI Tool（Python），輸入 IO List 與 BOM（xlsx 或 csv），輸出：IO List 有、BOM 沒有的 tag；BOM 有、IO List 沒有的 tag；重複的 tag；不符命名規則的 tag（規則由 David 提供或從範例歸納後經 David 確認）。檢查邏輯放在可單獨測試的純 Python 模組，Tool 只負責包裝。
5. 最終 RAG 設定寫成程式碼（compose 環境變數或匯出 `02_data/owui_rag_config.json`），並在 `03_docs/` 說明每項設定的選擇理由與分數依據。

## 不在範圍內
- 「噪音」知識庫的評測與調校（保留不動）
- 多個案場、多使用者權限、對外分享
- P&ID 圖面（影像）辨識
- n8n 改走 Open WebUI API（方案 B）
- 修 Open WebUI 上游的刪檔不刪向量問題（只記錄）
- 生成答案品質的 LLM 評分（本輪只評檢索與檢查 Tool）

## 驗收標準（必須能自動驗證）
- [ ] 知識庫建立：`py -3.10 scripts/owui_audit.py --knowledge 案場-<代號>` 顯示檔案數 = David 指定的份數，所有 collection 維度一致且等於 `rag.embedding_model` 的維度
- [ ] 機密文件不進 git：`git ls-files` 中沒有任何案場文件；`.gitignore` 涵蓋評測集中可能含機密內容的檔案（若評測集含原文摘錄，評測集也不進 git，只記錄雜湊）
- [ ] 評測集定稿：≥ 30 題，每題有來源檔名與頁碼（或工作表＋列號），標記 `reviewed: true`
- [ ] baseline 與每次升級都有紀錄：`02_data/metrics.csv` 至少有 baseline 加 A3 各項的列（日期、commit、設定名、recall@5、MRR、p50、p95、指令）
- [ ] 檢索達標（**暫定**）：recall@5 ≥ max(baseline + 0.10, 0.80)；檢索 p50 ≤ 3 秒、p95 ≤ 8 秒。baseline 出來後若門檻明顯不合理，說明理由後問 David
- [ ] 評測可重現：同一設定連跑 2 次 recall@5 相同
- [ ] 檢查 Tool 正確：`py -3.10 -m pytest tests/` 通過；測試資料是以 David 的範例為底、刻意放入至少 5 種錯誤（缺漏、多出、重複、命名錯、大小寫或空白差異）的副本，每種錯誤都被抓到且沒有誤報
- [ ] 檢查 Tool 在 Open WebUI 可用：透過 API 以測試檔呼叫 Tool，回傳結果與 pytest 期望一致（紀錄寫入 verify）
- [ ] 服務正常：`curl localhost:3000/health` 回 200；`docker port open-webui` 仍只有 `127.0.0.1:3000`
- [ ] 驗收紀錄：`02_data/verify_YYYYMMDD.md` 逐條寫指令、輸出摘要、是否通過

## 可以自行決定
- 腳本語言與位置（Python 用 `py -3.10` 或專案 venv）、評測集格式（建議 jsonl）、測試框架
- 透過 Open WebUI API 或直接檢索計分的方式（必須和實際聊天走同一條檢索路徑）
- A3 各項的嘗試順序與參數組合、reranker 候選數
- 新容器（Docling）的映像與資源設定，但映像要固定版本
- 分支命名與 commit 粒度（每完成一個驗收項目 commit，訊息用繁體中文）

## 必須停下來問我
- 選哪個案場、哪些文件；文件的機密等級與是否允許出現在評測集或 git 中
- IO List／BOM 的欄位定義與 tag 命名規則（不可自行假設後直接上線）
- 評測集定稿、調整驗收門檻
- 刪除任何上傳檔、知識庫、對話或 collection；直接寫入 `webui.db` 或 Chroma
- 建立 API key（由 David 在 UI 產生；key 只透過環境變數 `OWUI_API_KEY` 給腳本，`.env` 受 hook 保護，腳本不得讀取；需要 key 的步驟由 David 在自己的終端機執行）
- 需要外部付費 API、或會把案場文件內容送出本機的任何步驟
- VRAM 會超過 8 GB，或需要停掉其他專案的容器
- push 到 GitHub

## 環境與限制
- Windows 11 原生，Docker Desktop；PowerShell 5.1；Python `py -3.10`
- RTX 4060 8 GB。bge-m3（約 1.2 GB）＋ 7B q4 對話模型（約 4.7 GB）＋ KV cache 估計約 6.5 GB（**暫定，未實測**）
- open-webui 映像沒有 CUDA，本機 reranker 只能跑 CPU（6 核）
- open-webui：`127.0.0.1:3000`、映像以 digest 固定（0.10.2）、資料在 `D:\local-ai-agent\open-webui`
- Docker Desktop 停止 open-webui 容器時可能卡住數分鐘（映像 `StopTimeout=1`，kill 耗時 18 秒以上）；重建容器前要預留停機時間
- `claude_gemini` pipe 會外送資料：**不可**用於案場文件的問答，自訂模型與知識庫不得連到它

## 已知背景
- 2026-11-18 盤點：Open WebUI 13 筆對話，本地模型各只試過 1 次，「噪音」知識庫只用過 1 次；實際常用的是 Groq＋Gemini 交叉點評 pipe。因此改以 David 真正會查的工程文件為評測與優化對象。
- David 曾上傳「水處理工程儀控 P&ID BOM IOList 專家規則引擎」需求文件（file id `23e98a38`），可作為 A4 規則的參考。
- Open WebUI 提供 OpenAI 相容的 `/api/chat/completions`（`main.py:1007`），評測與 Tool 驗證可透過它進行。
- P0 已完成：孤兒資料清除、OpenAI 連線關閉、只綁本機、版本固定、維護腳本（`scripts/`）。
