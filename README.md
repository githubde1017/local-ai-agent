# 🤖 Local AI Agent (`local-ai-agent`)

> 隱私優先、完全離線執行的本地端 AI Agent 協作與自動化系統。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Supported-blue)](https://www.docker.com/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama%20%2F%20Local-orange)](https://ollama.ai/)

---

## 📌 專案簡介 (Overview)

**`local-ai-agent`** 是一個旨在實現 **數據不外流、全本地運算** 的輕量化 AI Agent 框架與服務。專案結合本地 LLM（如 Ollama / llama.cpp / vLLM）與視覺/OCR 模型，讓您能夠在沒有網際網路連接或考量資訊安全的環境下，構建具備工具調用 (Tool Calling)、自動化任務排程與多 Agent 協作能力的智慧工作流。

---

## ✨ 核心特色 (Key Features)

* **🔒 100% 本地與隱私保護**：所有 prompt、文件資料與 API 調用均在本地端處理，敏感數據零外流風險。
* **🧠 多模型靈活支援**：整合 Ollama / Local OpenAI-compatible API，輕鬆切換不同大小的文本與視覺模型 (VLM)。
* **🛠️ 模組化 Tool & Agent 機制**：內建檔案處理、數據解析、自動化腳本執行等工具，支援客製化 Agent 角色定義。
* **🐳 一鍵 Docker 部署**：提供獨立容器化環境，簡化 GPU / CUDA 驅動與跨平台依賴套件配置。
* **⚡ 輕量化與高速回應**：專為一般工作站 / 本地開發環境優化資源佔用。

---

## 🏗️ 系統架構 (Architecture)

```text
  ┌───────────────────────────────────────────────────┐
  │                 User / Client                     │
  └─────────────────────────┬─────────────────────────┘
                            │
                            ▼
  ┌───────────────────────────────────────────────────┐
  │                 local-ai-agent                    │
  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
  │  │ Agent Engine │  │ Tool Executor│  │ Workflow │ │
  │  └──────┬───────┘  └──────┬───────┘  └────┬─────┘ │
  └─────────┼─────────────────┼───────────────┼───────┘
            │                 │               │
            ▼                 ▼               ▼
  ┌──────────────────┐┌──────────────┐┌───────────────┐
  │  Local LLM / VLM ││ Local File   ││ Custom Tools  │
  │ (Ollama / vLLM)  ││ / Databases  ││ (Python/Bash) │
  └──────────────────┘└──────────────┘└───────────────┘

```

---

## 🚀 快速開始 (Quick Start)

### 1. 環境需求 (Prerequisites)

* Linux / macOS / Windows (WSL2)
* Python 3.10+
* Docker & Docker Compose (推薦)
* 本地 LLM 引擎（例如已安裝 [Ollama](https://ollama.ai/) 並拉取模型）

---

### 2. 本地端開發設定 (Local Development)

```bash
# 1. 複製專案庫
git clone [https://github.com/your-username/local-ai-agent.git](https://github.com/your-username/local-ai-agent.git)
cd local-ai-agent

# 2. 建立 Python 虛擬環境
python3 -m venv venv
source venv/bin/activate  # Windows 請用: venv\Scripts\activate

# 3. 安裝依賴套件
pip install -r requirements.txt

# 4. 設定環境變數
cp .env.example .env
# 編輯 .env 調整 LOCAL_LLM_URL, MODEL_NAME 等設定

# 5. 啟動主程式
python main.py

```

---

### 3. Docker Compose 部署 (Docker Setup)

```bash
# 一鍵啟動 AI Agent 及其依賴服務
docker-compose up -d --build

```

---

## 📂 專案架構 (Project Structure)

```text
local-ai-agent/
├── config/                 # 系統設定檔 (models, prompts, configs)
├── src/
│   ├── agents/             # Agent 邏輯與角色定義
│   ├── tools/              # 工具套件 (File Ops, Web Scraper, Exec)
│   ├── llm/                # Local LLM API 連接介面 (Ollama / OpenAI spec)
│   └── utils/              # 通用輔助函式
├── tests/                  # 單元測試與整合測試
├── .env.example            # 環境變數設定範本
├── Dockerfile              # 主服務 Docker 建置檔
├── docker-compose.yml      # 容器編排檔
├── requirements.txt        # Python 依賴清單
└── main.py                 # 應用程式入口點

```

---

## ⚙️ 環境變數設定 (Environment Variables)

請參考 `.env.example` 建立 `.env` 檔案：

```ini
# Local LLM Endpoint Settings
LOCAL_LLM_URL=http://localhost:11434
DEFAULT_MODEL=llama3:8b
VISION_MODEL=llava:latest

# Agent Options
VERBOSE=true
MAX_ITERATIONS=10

```

---

## 📝 授權條款 (License)

本專案採用 [MIT License](https://www.google.com/search?q=LICENSE) 授權。

```

```