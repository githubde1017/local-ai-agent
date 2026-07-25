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

* **🔒 100% 本地數據隱私**：資料庫、對話記錄與 Vector DB 皆存放於本地硬碟，絕無數據外流風險。
* **⚡ 雙硬碟架構優化**：模型載入放 SSD (`F:/ollama`)，海量儲存與向量庫放大容量 HDD (`D:/local-ai-agent`)。
* **🧩 模組化自動化工作流**：使用 n8n 串接 Telegram Bot、搜尋 API 與本地 LLM，輕鬆建立無人值守 Agent。
* **🐳 一鍵 Docker Compose 部署**：免去繁雜的環境安裝，直接一鍵啟動全套 AI 生態系。

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

* **Open WebUI 介面**：`http://localhost:3000`
* **n8n 工作流介面**：`http://localhost:5678`
* **Qdrant 儀表板**：`http://localhost:6333/dashboard`
* **Ollama API**：`http://localhost:11434`
* **Crawler API**：`http://localhost:5000`

---

## 📂 專案架構 (Project Structure)

```text
local-ai-agent/
├── crawler/                # 自訂爬蟲服務與 Dockerfile
├── n8n_data/               # n8n 資料與自訂節點 (Baseten, SerpApi, GSC...)
├── open-webui/             # Open WebUI 快取、嵌入模型模型與向量庫資料
├── qdrant_storage/         # Qdrant 向量資料庫實體數據
├── workflow/               # 匯出的 n8n 工作流 JSON 檔案目錄
├── .env                    # 環境變數設定檔 (已在 .gitignore 中忽略)
├── .env.example            # 環境變數範本檔
└── docker-compose.yml      # Docker 容器編排設定檔

```

---

## 📝 授權條款 (License)

本專案採用 [MIT License](https://www.google.com/search?q=LICENSE) 授權。
