# 旅行智能助手

这是对原有旅行助手的**增量迁移**：原项目的旅行请求 Schema、Prompt、攻略校验、知识文档解析、ChromaDB RAG、训练配置和数据准备脚本继续保留；生产界面从 Streamlit 扩展为 Vue 3，服务层增加 FastAPI 与 Docker，Chat 和 Embedding 的生产推理切换为 OpenAI-compatible 在线 API。

生产运行时不再加载或下载本地 Qwen、LoRA、BGE-M3，也不依赖 GPU、CUDA、Torch、Transformers、PEFT 或 Sentence Transformers。此前遇到的 Hugging Face 大文件下载中断、`IncompleteRead`、`ConnectionResetError` 不再属于生产启动链路。D 盘项目中已经下载的 `models/` 不会删除，也不会复制进 Docker 镜像。

## 架构与目录

```text
travel-assistant/
├── app.py                     # 保留的 Legacy Streamlit 在线入口
├── backend/                    # FastAPI、单任务队列、Dockerfile
├── frontend/                   # Vue 3 + Vite + TypeScript、Nginx
├── travel_assistant/           # Prompt、领域 Schema、在线客户端、RAG
├── scripts/                    # 命令行入库、可选训练数据准备
├── config/qwen_lora.yaml       # 仅保留为可选离线训练资料
├── data/chroma/                # ChromaDB 持久化目录（首次运行时创建）
├── compose.yaml
├── requirements.txt            # 生产依赖
├── requirements-legacy.txt     # 可选 Streamlit 界面依赖
└── requirements-training.txt   # 可选本地 LoRA 训练依赖
```

运行链路：

```text
浏览器 → Vue 3 / Nginx → FastAPI → 在线 Chat API
                              └→ 在线 Embedding API → ChromaDB
```

## API

- `GET /api/v1/health`：进程健康检查，不调用在线服务。
- `GET /api/v1/status`：查看 Chat、Embedding、任务队列和知识库配置状态，不显示 API Key。
- `POST /api/v1/knowledge/documents`：上传 TXT、Markdown 或文本型 PDF。
- `POST /api/v1/guides`：提交旅行条件，立即返回 `task_id`。
- `GET /api/v1/tasks/{task_id}`：查询 `queued`、`running`、`completed`、`failed` 状态。

攻略生成使用进程内单工作线程队列，同一 Backend 实例一次只生成一份攻略。任务状态只保存在当前进程内，Backend 重启后未完成任务不会恢复；因此 Docker 配置固定为一个 Uvicorn worker。

## Docker 启动（推荐）

环境要求：Docker Desktop 或 Docker Engine + Docker Compose Plugin。

1. 进入项目目录：

```powershell
cd <项目目录>\Assistant
```

2. 创建 Docker 环境配置：

```powershell
Copy-Item .env.docker.example .env.docker
```

3. 编辑 `.env.docker`，至少填写：

```dotenv
LLM_BASE_URL=https://你的服务商地址/v1
LLM_API_KEY=你的Chat API Key
LLM_MODEL=你的在线聊天模型名
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/api/v1
EMBEDDING_API_KEY=你的Embedding API Key
EMBEDDING_MODEL=qwen3-vl-embedding
EMBEDDING_DIMENSION=1024
EMBEDDING_BATCH_SIZE=20
```

`.env.docker` 和其他本地 `.env*` 文件已被 Git 忽略。不要把真实 API Key 写入源码、README 或示例配置；公开仓库只保留 `.env.example` 与 `.env.docker.example`。

如果 Chat 和 Embedding 使用同一个服务商和 Key，`EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY` 可以留空；程序会分别回退到 `LLM_BASE_URL`、`LLM_API_KEY`。如果使用不同服务商，请单独填写。

`LLM_BASE_URL` 必须是服务商的 OpenAI-compatible API 根地址，通常包含 `/v1`，不要填写到 `/chat/completions`。使用 `qwen3-vl-embedding` 或 `qwen2.5-vl-embedding` 时，`EMBEDDING_BASE_URL` 应填写 DashScope 原生 API 根地址 `https://dashscope.aliyuncs.com/api/v1`；其他 Embedding 模型仍按其 OpenAI-compatible API 根地址配置。

当前默认使用 `qwen3-vl-embedding`，客户端会显式请求 1024 维并将单批文本限制为 20 条。也可将 `EMBEDDING_MODEL` 改为 `qwen2.5-vl-embedding`，但该模型每次请求只能处理一段文本，因此大量资料入库会更慢。

两个模型不会自动互相回退。即使维度同为 1024，不同模型的向量空间也不能混用；切换模型时必须使用新的 `CHROMA_COLLECTION` 并重新入库。后续切换本地 `bge-m3` 时同样需要新建 Collection，客户端会继续使用 OpenAI-compatible `/embeddings` 协议。

4. 构建并启动：

```powershell
docker compose up --build -d
```

5. 查看容器状态并访问：

```powershell
docker compose ps
docker compose logs -f backend
```

浏览器打开 `http://localhost:8080`。停止服务：

```powershell
docker compose down
```

Compose 只挂载 `./data/chroma:/app/data/chroma`，不会挂载或下载 `models/`，也没有 GPU 配置。

## 从已有本地项目迁移

本项目可以基于已有版本增量迁移。大体积本地资产保留在原项目目录，新在线版只需要交付运行所需源码：

| 原有内容 | 迁移结果 | 新生产运行时用途 |
| --- | --- | --- |
| 原项目 `models/` 下的 Qwen、BGE-M3 和分类模型 | 留在原目录，不重复复制 | 新生产运行时不加载 |
| 原项目 `data/chroma/` | 留在原目录，不覆盖 | 新目录创建在线 Embedding Collection |
| `data/training/`、`config/qwen_lora.yaml` | 随源码交付 | 可选 LoRA/QLoRA 实验 |
| `scripts/prepare_training.py` | 随源码交付 | 训练数据校验与规范化 |
| 原项目 `.venv/`、`.idea/`、`.env` | 留在原目录，不覆盖 | 新目录按本文步骤重新配置 |

旧 `.env` 中的 `BASE_MODEL_ID`、`LORA_ADAPTER_PATH`、`EMBEDDING_MODEL_ID` 等字段不会被新的在线运行时读取。在新目录本地启动 Backend 或 Legacy Streamlit 前，请复制 `.env.example` 为 `.env`，并特别设置：

```dotenv
CHROMA_COLLECTION=travel_knowledge_online
```

这样会在新目录 `data/chroma` 内创建在线向量 Collection，原项目的 BGE-M3 向量保持不变。Docker 使用单独的 `.env.docker`，不会覆盖本地 `.env`。

## 本地开发启动

建议 Python 3.11、Node.js 20 或更高版本。

1. 安装 Backend：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env` 后启动：

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1 --reload
```

Backend 文档位于 `http://localhost:8000/docs`。

2. 在另一个终端启动 Frontend：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`，Frontend 没有硬编码生产 Backend 地址。

## Legacy Streamlit 入口（可选）

原项目的 `app.py` 没有被删除，已适配 `OnlineChatModel`、`OnlineEmbeddingClient` 和兼容版 `TravelPlanner`。它保留原有三个 Tab 的使用方式，但现在同样调用在线 Chat/Embedding API，不再加载本地 Qwen 或 BGE-M3。

如需继续使用 Streamlit 界面：

```powershell
python -m pip install -r requirements-legacy.txt
streamlit run app.py
```

生产 Docker 不安装 Streamlit，也不启动 `app.py`；Docker 默认入口仍为 Vue 3 + FastAPI。

## 使用知识库

在“知识库”页面填写目的地并上传资料，或运行：

```powershell
python scripts/ingest_knowledge.py --path data/knowledge --destination 成都 --topic 综合
```

支持 UTF-8 TXT、Markdown、带文本层的 PDF；扫描版 PDF 需要先 OCR。检索严格按目的地过滤，入库和攻略表单的目的地名称应保持一致。

每个 Collection 都记录 `embedding_model` 和 `embedding_dimension`。如果当前配置与已有非空 Collection 不一致，程序会拒绝检索和写入，以免不同向量空间混用。切换 `qwen3-vl-embedding`、`qwen2.5-vl-embedding` 或本地 `bge-m3` 时，都必须修改 `CHROMA_COLLECTION` 使用一个新名称，然后重新入库。

旧版默认 BGE-M3 Collection 不会自动转换。默认新名称为 `travel_knowledge_online`，原 `data/chroma` 内容会保留，但旧向量不会被新 Collection 使用。

## 在线 API 重试与错误

Chat 和 Embedding 请求只会在网络中断、超时、HTTP 429、可恢复的 5xx 时按指数退避重试。API Key 错误、Base URL/模型名错误、请求参数错误、响应结构错误不会盲目重试，前端会显示中文原因。

常见检查顺序：

1. “运行状态”页是否显示 Chat 与 Embedding 配置完整。
2. Base URL 是否包含服务商要求的 `/v1`。
3. Chat 与 Embedding 模型名是否是该服务商实际支持的 ID。
4. `EMBEDDING_DIMENSION` 是否与服务商返回向量维度一致。
5. Docker 容器能否访问对应 API 域名，Key 是否有额度与权限。

本项目不会在状态页探测在线 API，因此“配置完整”只表示必需字段已填写，不代表服务商调用已经成功。

## 可选 LoRA 训练资料

原项目中的 `models/` 继续作为离线资产保留；新目录中的 `config/qwen_lora.yaml`、`data/training/` 和 `scripts/prepare_training.py` 也只用于离线实验，不参与生产服务。若仍要单独实验 Qwen2.5 + LoRA，请创建独立训练环境：

```powershell
python -m pip install -r requirements-training.txt
python scripts/prepare_training.py --input data/training/travel_sample.jsonl --output data/training/travel_prepared.jsonl
swift sft config/qwen_lora.yaml
```

训练输出不会被当前在线生产运行时自动加载。

## 说明

按你的要求，项目不包含 `pytest`、Vitest、Playwright 等自动化测试套件。交付验证只进行 Python 编译/导入、Vue 生产构建、Docker Compose 配置及可用环境下的镜像构建；没有真实 API Key 时不会调用在线服务，也不会声称在线生成已经成功。
