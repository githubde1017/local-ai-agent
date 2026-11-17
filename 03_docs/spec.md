# spec：Open WebUI「噪音」知識庫評測驅動升級
版本：v0.1｜日期：2026-11-17｜repo：local-ai-agent（`D:\01_Workflow\local-ai-agent`，origin `githubde1017/local-ai-agent`）

## 最終目標（為什麼做）
David 自用的本地中文專業文件問答助理：問「噪音」知識庫裡的計畫書內容時，答案要附正確頁碼，找不到就明說；資料除了一個標示清楚的例外 pipe 以外都不出本機。是否「變好」一律用固定評測集的分數判定，不靠感覺。

## 本次任務
1. **P0 清理**（只對 open-webui）
   - 停容器備份 `D:\local-ai-agent\open-webui`（`cache/` 除外）到 `D:\local-ai-agent\_backup\open-webui_YYYYMMDD\`，記錄 `webui.db` 的 sha256。
   - 刪除孤兒檔案 `baa836b1…`、`b85cb0f2…`（屬於已刪除的知識庫 `3843fc6b`），連同對應的 384 維 Chroma collection 與 `knowledge_file` 孤兒列。優先走 Open WebUI API。
   - 關閉 OpenAI 連線（`openai.enable=false`，目前沒有 key）。
   - `claude_gemini` pipe **保留**：描述改成實際的「Groq＋Gemini 交叉點評」，README 新增「外部資料傳輸例外」一節，寫明這是唯一會把對話送出本機的元件。
   - compose：open-webui 埠改成 `127.0.0.1:3000:8080`，映像從 `:main` 改成固定版本 tag（與目前的 0.10.2 相同或經評測確認的版本）。
2. **P1 基準**
   - 建立評測集：至少 30 題，每題有問題、標準答案要點、來源檔名、頁碼，涵蓋兩份 PDF，其中至少 5 題是表格或數字題。先由 Claude 草擬，**David 審過**才算定稿。
   - 評測腳本：對指定知識庫逐題檢索，算 recall@5（前 5 個片段有沒有命中正確頁碼）、MRR，以及檢索延遲 p50/p95。結果附 commit 與設定名稱，寫入 `02_data/metrics.csv`。
   - 用目前設定（snowflake-arctic-embed2、無 hybrid、無 reranker、chunk 1000）跑一次，作為 baseline。
3. **P2 逐項升級**（一次只改一項；改完重建索引、重跑評測，分數沒提升就回退）
   - embedding 換成 `bge-m3`（Ollama，GPU），全庫重建
   - 開啟 hybrid search（BM25＋向量）
   - reranker `BAAI/bge-reranker-v2-m3`（在 open-webui 容器內跑 CPU）
   - Markdown 標題切塊，chunk size／overlap 掃 2～3 組
   - 相關度門檻與「找不到就明說」的 RAG template
4. **P3 解析（條件式）**：只有在 P2 之後表格題的 recall@5 < 0.6 時才做。加一個 Docling 容器當 content extraction engine，重新解析並評測。
5. 最終設定寫成程式碼：RAG 相關設定放進 compose 環境變數或匯出檔（`02_data/owui_rag_config.json`），並在 `03_docs/` 說明每項設定的選擇理由與分數依據。

## 不在範圍內
- n8n 新聞 Bot 的失敗修復、Qdrant 與 crawler 的去留（另開任務）
- 把向量庫從 Chroma 換成 Qdrant
- 「噪音」以外的知識庫、新增文件
- Ollama 裡 `qwen2.5:3b` 以 CPU 常駐的原因（只記錄觀察，不處理）
- 合併 `D:\local-ai-agent`（資料）與 `D:\01_Workflow\local-ai-agent`（原始碼）兩個目錄
- 生成答案品質的 LLM 評分（本輪只評檢索；答案品質留到下一輪）

## 驗收標準（必須能自動驗證）
- [ ] 備份存在且可讀：備份目錄內的 `webui.db` 可用 `sqlite3` 開啟，sha256 寫入 `02_data/verify_YYYYMMDD.md`
- [ ] 孤兒資料已清除：盤點腳本輸出 `file` 表中不存在 `baa836b1`、`b85cb0f2`；`knowledge_file` 沒有指向不存在知識庫的列；Chroma 裡沒有任何 384 維且有資料的 collection；「噪音」知識庫仍為 2 份檔案
- [ ] OpenAI 連線已關閉：`config` 表的 `openai.enable` = `false`
- [ ] pipe 標示：`function` 表裡 `claude_gemini` 的描述包含「Groq」與「Gemini」；README 有「外部資料傳輸例外」一節
- [ ] 只限本機：`docker port open-webui` 只顯示 `127.0.0.1:3000`；從本機用區網 IP 執行 `curl http://<區網IP>:3000` 連線失敗
- [ ] 版本固定：`docker-compose.yml` 中 open-webui 的 image 不是 `:main` 或 `:latest`
- [ ] 服務正常：`docker compose up -d` 後 60 秒內 `curl localhost:3000/health` 回 200
- [ ] 評測集定稿：評測集檔案 ≥ 30 題，每題都有 `file`、`page`，並標記 `reviewed: true`（由 David 審過）
- [ ] baseline 與每次升級都有紀錄：`02_data/metrics.csv` 至少有 baseline 加 P2 各項的列（日期、commit、設定名、recall@5、MRR、p50、p95、指令）
- [ ] 最終設定達標（**暫定**門檻）：recall@5 ≥ max(baseline + 0.10, 0.80)；檢索 p50 ≤ 3 秒、p95 ≤ 8 秒（含 CPU reranker）。暫定依據：目前沒有任何基準數字，等 baseline 出來後若門檻明顯不合理，說明理由後問 David
- [ ] embedding 一致：「噪音」知識庫所有 collection 的維度相同，並與 `rag.embedding_model` 一致（盤點腳本輸出）
- [ ] 評測可重現：同一設定連跑 2 次，recall@5 完全相同
- [ ] 驗收紀錄：`02_data/verify_YYYYMMDD.md` 逐條寫指令、輸出摘要、是否通過

## 可以自行決定
- 腳本語言與放置位置（Python 用 `py -3.10` 或專案 venv）、評測集格式（建議 jsonl）
- 透過 Open WebUI API 或直接檢索 Chroma 計分的方式（前提是與實際聊天走同一條檢索路徑）
- P2 各項的嘗試順序、chunk 參數組合、reranker 候選數（top_k_reranker）
- 新容器（Docling）的映像與資源設定，但映像要固定版本
- 分支命名與 commit 粒度（每完成一個驗收項目 commit，訊息用繁體中文）

## 必須停下來問我
- 建立 Open WebUI API key：請 David 在 UI 產生，放進 `.env` 的 `OWUI_API_KEY`，Claude 不自行建立
- 除了兩份孤兒檔案以外，要刪除任何上傳檔、知識庫、對話或 collection
- 在容器運作中直接寫入 `webui.db`（API 做不到、必須直接改 DB 時，要先停容器、先備份、先問）
- 刪除 `cache/embedding`（889 MB 的 MiniLM 快取）
- 評測集定稿（需要 David 審題）、調整驗收門檻
- 需要對外付費 API、需要用到外部 API 才能完成評測或解析
- VRAM 會超過 8 GB，或需要停掉其他專案的容器（例如 `legion-db`）
- push 到 GitHub

## 環境與限制
- Windows 11 原生，Docker Desktop；PowerShell 5.1；Python `py -3.10`
- RTX 4060 8 GB。bge-m3（約 1.2 GB）加上 7B q4 對話模型（約 4.7 GB）加上 KV cache，估計約 6.5 GB（**暫定，未實測**）
- open-webui 映像沒有 CUDA（`USE_CUDA_DOCKER=false`），本機 reranker 只能跑 CPU（6 核）
- 服務埠：open-webui 3000、ollama 11434（Docker 容器，模型在 `F:\ollama`）、n8n 5678、qdrant 6333/6334、crawler 5000
- 資料位置：compose 掛載 `D:\local-ai-agent\open-webui`（**不是** repo 內的 `open-webui/`，那份是 7 月的舊資料）
- Open WebUI 0.10.2：設定存在 `webui.db` 的 `config` 表（key/value），環境變數與 DB 設定誰的優先權高**未驗證**，實作時要先確認
- `.env` 有 hook 保護，不可讀取；需要的新變數加進 `.env.example`

## 已知背景（2026-11-17 盤點）
- 「噪音」知識庫（id `310106ad`）：2 份 PDF——111年度臺中市科技感測器稽查整合計畫（89 MB，439 個片段）、114年度彰化縣機動車輛排氣管污染管理事務計畫成果報告（4 MB，60 個片段），1024 維（snowflake-arctic-embed2）。自訂模型 `noise-query` 以 `qwen2.5-tw` 為底。
- 同兩份 PDF 有舊副本（`baa836b1`、`b85cb0f2`），屬於已刪除的知識庫 `3843fc6b`，向量是 384 維（MiniLM），沒有任何對話引用。
- 目前的 RAG 設定：top_k 5、chunk 1000、無 hybrid、無 reranker、web search 關閉。
- 對話 13 筆，最後一筆是 2026-10-23。使用者只有 David（admin），註冊已關閉。
- `claude_gemini` pipe：描述寫 Claude＋Gemini，實際設定的是 `GROQ_API_KEY`、`GEMINI_API_KEY`。
- 89 MB 那份 PDF 是否有文字層、表格多不多：未驗證。
