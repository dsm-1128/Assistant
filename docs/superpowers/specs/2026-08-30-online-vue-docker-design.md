# 旅行智能助手在线化设计

## 目标

在现有 Streamlit、本地 Qwen2.5-7B/LoRA、本地 BGE-M3 项目上增量增加可通过 Docker 部署的 Vue 3 + FastAPI 生产链路。保留领域 Schema、Prompt、攻略校验、知识解析、训练配置、训练数据、脚本以及 D 盘已有模型和 Chroma 数据；攻略生成和向量化的生产运行时改为 OpenAI-compatible 在线 API。

## 架构

- `frontend/`：Vue 3、Vite、TypeScript、Vue Router、Axios。提供攻略生成、知识上传、运行状态三个页面。
- `backend/`：FastAPI REST API。使用单进程、单工作线程队列串行处理攻略生成，避免同一服务实例并发占用过多在线 API 配额。
- `travel_assistant/`：保留领域模型、Prompt、攻略校验和 RAG 逻辑；将本地模型类替换为在线 Chat/Embedding 客户端。
- `data/chroma/`：唯一需要持久化写入的运行目录。
- Docker Compose：Frontend Nginx 反向代理 `/api` 到单 worker Backend。

## 在线模型配置

Chat API：`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`LLM_TIMEOUT_SECONDS`、`LLM_MAX_RETRIES`。

Embedding API：`EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL`、`EMBEDDING_DIMENSION`、`EMBEDDING_TIMEOUT_SECONDS`。Embedding 的 URL 和 Key 留空时回退到 Chat API 对应配置。

客户端仅对网络错误、超时、HTTP 429 和可恢复 5xx 执行指数退避重试；认证错误、请求错误和响应结构错误直接返回清晰中文错误。

## RAG 一致性

入库前通过在线 Embedding API 批量生成向量，并将 `embedding_model` 与 `embedding_dimension` 写入 Collection metadata 和每个 chunk metadata。已有非空 Collection 的模型或维度不一致时拒绝混用，提示用户清空或更换 Collection 后重新入库。

## API

- `GET /api/v1/health`：进程健康检查，不请求外部 API。
- `GET /api/v1/status`：返回配置完整性、模型名和知识库状态，不泄漏 Key。
- `POST /api/v1/knowledge/documents`：上传 TXT、Markdown 或文本型 PDF 并入库。
- `POST /api/v1/guides`：校验旅行条件并返回 `task_id`。
- `GET /api/v1/tasks/{task_id}`：返回 `queued/running/completed/failed`，完成时包含攻略与引用证据。

错误统一为 `{ "error": { "code", "message", "details" } }`。

## 前端交互

攻略页提交任务后轮询状态，将当前 `task_id` 存入 `localStorage`，刷新后继续查询；任务未结束时禁用重复提交。知识页上传资料并显示片段数。状态页显示后端、在线模型配置与 ChromaDB 状态。生产代码仅访问相对路径 `/api`。

## 部署与兼容

- Backend 使用 Python slim 镜像，不安装 Torch、Transformers、PEFT、Sentence Transformers 或 CUDA 依赖。
- Frontend 使用 Node 构建后复制到 Nginx；Nginx 支持 Vue Router history fallback，并代理 `/api`。
- `app.py` 保留原有 Streamlit 交互并适配在线客户端与新的 Planner 返回值，明确标记为 Legacy；生产 Docker 不复制、不安装也不启动该入口。
- LoRA 训练配置与数据准备脚本保留为可选离线资料，依赖拆分到 `requirements-training.txt`。
- D 盘已有 `models/`、`data/chroma/`、`.venv/`、`.idea/` 均不删除；新在线向量使用独立 Collection，避免覆盖旧 BGE-M3 数据。
- 不加入自动化测试框架；执行 Python 导入、Frontend build、Compose 配置等验证。
