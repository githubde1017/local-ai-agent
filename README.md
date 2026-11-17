# 🤖 Local AI Agent (`local-ai-agent`)

> 隱私優先、完全離線執行的本地端微服務架構 AI Agent 與自動化工作流系統。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Supported-blue)](https://www.docker.com/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-orange)](https://ollama.ai/)
[![n8n](https://img.shields.io/badge/Workflow-n8n-ff6d5a)](https://n8n.io/)
[![Qdrant](https://img.shields.io/badge/VectorDB-Qdrant-red)](https://qdrant.tech/)

---

## 📌 專案簡介 (Overview)

**`local-ai-agent`** 是一個完全本地運行的微服務 AI 協作生態系統。專案結合了本地 LLM 推理引擎 (Ollama)、向量資料庫 (Qdrant)、智慧前端 UI (Open WebUI) 以及工作流自動化引擎 (n8n)，搭配自訂的 AI 爬蟲服務 (Crawler)，達成 **數據零外流、隱私優先、模組化自動化** 的 AI Agent 工作流。

---

## 🏗️ 系統架構與服務清單 (Architecture & Services)

系統由多個 Docker 容器與本地儲存目錄相互搭配運作：

```text
                      ┌─────────────────────────────────┐
                      │    Open WebUI (Port 3000)       │
                      │   (AI 助理前端介面與知識庫)      │
                      └────────────────┬────────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            ▼                          ▼                          ▼
  ┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
  │ Ollama Engine    │       │ Qdrant Vector DB │       │ n8n Workflow     │
  │ (Port 11434, GPU)│       │ (Port 6333/6334) │       │ (Port 5678)      │
  └──────────────────┘       └──────────────────┘       └────────┬─────────┘
                                                                 │
                                                                 ▼
                                                        ┌──────────────────┐
                                                        │ Crawler Service  │
                                                        │ (Port 5000)      │
                                                        └──────────────────┘

```

### 服務說明

* **Ollama (Port `11434`)**: 本地 LLM 推理引擎（支援 NVIDIA GPU 加速，模型掛載於 `F:/ollama`）。
* **Open WebUI (Port `3000`)**: AI 聊天對話介面與文件 RAG 知識庫系統。
* **Qdrant (Port `6333` / `6334`)**: 高性能向量資料庫 (Vector Database)，提供 RAG 檢索增強生成。
* **n8n (Port `5678`)**: 自動化流程編排引擎，整合各式自訂 Node (如 Baseten, Google Search Console, SerpApi)。
* **Crawler (Port `5000`)**: 完全離線/私有化的 AI 網頁爬蟲微服務。

---

## ✨ 核心特色 (Key Features)

* **🔒 本地數據隱私**：資料庫、對話記錄與 Vector DB 皆存放於本地硬碟；唯一的例外見下方「外部資料傳輸例外」。
* **⚡ 雙硬碟架構優化**：模型載入放 SSD (`F:/ollama`)，海量儲存與向量庫放大容量 HDD (`D:/local-ai-agent`)。
* **🧩 模組化自動化工作流**：使用 n8n 串接 Telegram Bot、搜尋 API 與本地 LLM，輕鬆建立無人值守 Agent。
* **🐳 一鍵 Docker Compose 部署**：免去繁雜的環境安裝，直接一鍵啟動全套 AI 生態系。

### ⚠️ 外部資料傳輸例外

以下元件會把資料送出本機，使用時請留意：

| 元件 | 位置 | 送出的資料 | 送往 |
|---|---|---|---|
| `claude_gemini` pipe | Open WebUI → Functions | 該模型對話的提問與歷史訊息（最近數則） | Groq API、Google Gemini API |
| n8n 新聞 Bot | `workflow/*.json` | RSS 摘要結果 | Telegram |

在 Open WebUI 中，`claude_gemini` 是唯一會外送資料的元件；其餘對話（Ollama 本地模型）與知識庫檢索都只在本機處理。Open WebUI 的 OpenAI 連線已關閉。

---

## 🚀 快速開始 (Quick Start)

### 1. 環境需求 (Prerequisites)

* Windows 10/11 (WSL2 / Docker Desktop) 或 Linux
* [Docker & Docker Compose](https://www.docker.com/)
* NVIDIA 顯示卡與對應 GPU 驅動程序（建議配置）

---

### 2. 環境變數設定 (Environment Variables)

複製範例檔並建立 `.env`：

```bash
cp .env.example .env

```

請編輯 `.env` 填入您的設定（如 Telegram Token）：

```ini
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Local AI Services
OLLAMA_BASE_URL=http://ollama:11434
QDRANT_HOST=qdrant

# System Settings
TZ=Asia/Taipei

```

---

### 3. 一鍵啟動服務 (Launch Services)

```bash
# 啟動所有容器服務 (包含自動建構 Crawler)
docker-compose up -d --build

```

啟動後即可透過瀏覽器存取以下服務：

* **Open WebUI 介面**：`http://localhost:3000`（只綁本機，區網其他裝置無法連線）
* **n8n 工作流介面**：`http://localhost:5678`
* **Qdrant 儀表板**：`http://localhost:6333/dashboard`
* **Ollama API**：`http://localhost:11434`
* **Crawler API**：`http://localhost:5000`

### 4. Open WebUI 維護腳本

| 腳本 | 用途 | 需要 |
|---|---|---|
| `scripts/owui_audit.py` | 唯讀盤點：孤兒檔、懸空連結、向量維度、RAG 設定 | 無 |
| `scripts/owui_p0_api.py` | 透過 API 刪孤兒檔、關 OpenAI 連線、更新 pipe 描述（預設只預覽，加 `--apply` 才執行） | 環境變數 `OWUI_API_KEY` |
| `scripts/owui_purge_orphans.py` | 清除刪檔後殘留的向量集合與懸空連結（**須先停 open-webui**，用一次性容器執行，見檔頭說明） | 無 |

`OWUI_API_KEY` 在 Open WebUI「設定 → 帳號 → API 金鑰」產生（管理員須先在「管理員控制台 → 設定 → 驗證」開啟「啟用 API 金鑰」）。只放在自己終端機的環境變數，不要寫進 repo：

```powershell
$env:OWUI_API_KEY = "sk-..."
py -3.10 scripts/owui_audit.py
```

---

## 📂 專案架構 (Project Structure)

```text
local-ai-agent/               # 原始碼（本 repo）
├── 02_data/                # 驗收紀錄與指標
├── 03_docs/                # spec 與設計文件
├── crawler/                # 自訂爬蟲服務與 Dockerfile
├── scripts/                # Open WebUI 盤點與維護腳本
├── workflow/               # 匯出的 n8n 工作流 JSON 檔案目錄
├── .env                    # 環境變數設定檔 (已在 .gitignore 中忽略)
├── .env.example            # 環境變數範本檔
└── docker-compose.yml      # Docker 容器編排設定檔

D:/local-ai-agent/            # 容器資料（不進 git，由 compose 掛載）
├── n8n_data/               # n8n 資料與自訂節點
├── open-webui/             # Open WebUI 資料庫、上傳檔、向量庫與快取
├── qdrant_storage/         # Qdrant 向量資料庫實體數據
└── _backup/                # 手動備份
```

---

## 📝 授權條款 (License)

本專案採用 [MIT License](https://opensource.org/licenses/MIT) 授權。

```text
MIT License

Copyright (c) 2026 local-ai-agent

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT$ TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.