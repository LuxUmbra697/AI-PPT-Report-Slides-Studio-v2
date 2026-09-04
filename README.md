# Slide Report Studio

> AI 驱动的可编辑 PPT 与动态 HTML 报告工作台。
> AI‑powered editable PPT and dynamic HTML report studio.

`FastAPI` · `React` · `PostgreSQL` · `Redis` · `ARQ` · `python-pptx` · `DeepSeek 兼容模型` · `Qwen 图像 / 视觉模型`

[中文](#中文) · [English](#english)

---

<a id="中文"></a>

Slide Report Studio 把主题、长文本或上传材料转换为可审阅的大纲，再分别生成可编辑演示文稿或独立的动态 HTML 报告。它关注的不只是“生成一页内容”，而是从大纲确认、异步生成、人工修改到最终交付的完整创作流程。

| 中文                                               |
| ------------------------------------------------ |
| 面向可编辑 PPT 与动态 HTML 报告的 AI 创作工作台：大纲优先、模板解析与多格式交付。 |

### 核心能力

| 能力 | PPT 工作流 | HTML 报告工作流 |
| --- | --- | --- |
| 大纲优先，可人工确认与修改 | 支持 | 支持 |
| 原生可编辑 PPTX | 支持 | — |
| PPT 导出 HTML / Markdown / PDF | 支持 | — |
| 由 AI 直接编写 HTML + CSS + JS | — | 支持 |
| 动效、交互、数据大屏与丰富 Web 组件 | 预览能力 | 支持 |
| 独立离线 HTML 下载 | 支持 | 支持 |
| PPT 主题与 `Template/` 模板参考 | 支持 | 不使用 |

- **先确认大纲再生成**：在消耗完整生成时间前，先调整页面标题、重点、顺序和页数。
- **PPT 与 HTML 完整解耦**：PPT 使用主题、版式和可编辑对象；HTML 报告直接由模型依据内容与风格提示创作，不继承 PPT 背景、封面或模板。
- **可编辑 PPTX**：文本、图表、表格和主要结构以原生对象导出，而不是整页截图。
- **动态 HTML 报告**：支持动效、章节导航、图表、数据看板、语义表格、Excel 风格数据表、二维码、条码、ECharts 2D、ECharts-GL/Three.js 3D 可视化及降级展示。
- **可靠图片链路**：后端下载、验证并保存生成图片或图库图片；在线预览使用本站相对媒体路径，下载时内嵌图片，避免本机绝对路径和易失效的外链。
- **可选外部 PPTX 模板解析**：将你拥有权利的 `.pptx` 放入 `Template/`，系统会读取背景、图片、布局、位置、图表、表格、组件与配色，供 **PPT 工作流** 单独选择。
- **二次元工作台界面**：多套独立主题、动态装饰与可拖动看板娘。

### 产品截图

<details open>
<summary><strong>01 · 登录与界面主题选择</strong></summary>

![登录与主题选择](docs/screenshots/1、登录界面-可选主题.png)
</details>

<details>
<summary><strong>02 · 个人项目列表</strong></summary>

![个人项目列表](docs/screenshots/2、登录后进入个人界面.png)
</details>

<details>
<summary><strong>03 · 新建 PPT</strong></summary>

![PPT 制作页面](docs/screenshots/3、PPT制作页面.png)
</details>

<details>
<summary><strong>04 · 新建 HTML 报告</strong></summary>

![HTML 报告制作页面](docs/screenshots/4、HTML报告制作页面.png)
</details>

<details>
<summary><strong>05 · PPT 生成工作区</strong></summary>

![PPT 报告生成页面](docs/screenshots/5、PPT报告生成页面.png)
</details>

<details>
<summary><strong>06 · PPT 多格式导出</strong></summary>

![PPT 多格式导出](docs/screenshots/6、PPT生成后支持多种格式导出.png)
</details>

<details>
<summary><strong>07 · HTML 报告生成中</strong></summary>

![HTML 报告生成中](docs/screenshots/7、HTML报告正在生成页面.png)
</details>

<details>
<summary><strong>08 · HTML 报告结果</strong></summary>

![HTML 报告结果](docs/screenshots/8、HTML报告生成页面.png)
</details>

### 工作流程

```text
主题 / 文本 / 文档材料
          │
          ▼
AI 生成大纲 → 人工审阅与修改
          │
          ├─ PPT：逐页异步生成 → 在线编辑 → PPTX / HTML / Markdown / PDF
          │
          └─ HTML：AI 直接生成完整 HTML + CSS + JS → 隔离预览 → 下载单文件 HTML
```

### HTML 报告的设计原则

HTML 是独立交付物，而不是将 PPT 页面套入网页容器。

- 模型可使用原生 HTML/CSS/JS、Tailwind、ECharts、ECharts-GL、Three.js、JsBarcode、QRCode 与 SheetJS。
- 图表与数据必须来自输入材料；示例数据必须清楚标记。WebGL/3D 内容必须提供 2D、表格或文字降级方案。
- 服务端会阻止任意远程脚本、iframe、机器本地绝对路径、第三方图片热链和远程 3D 资源。
- 导出的 HTML 会将受允许的框架脚本和项目媒体内嵌，离线打开仍可正常使用。

### PPT 主题与外部模板

内置主题库只保留差异明确的主题，覆盖二次元、企业汇报、个人介绍、政企、中国红、科技、古风与科学技术等方向。

如需分析自己的参考模板，将 `.pptx` 放在仓库根目录的 `Template/`。解析器会读取母版、布局、页面、填充、线条、图片、图表、表格、对象层级与归一化位置；外部模板只作用于 PPT，不会改变 HTML 报告的风格。

### 技术架构

```text
┌──────────────────────────────────────────────────────────────────┐
│ React 19 + TypeScript + Vite + Tailwind CSS                       │
│ React Router · TanStack Query · Zustand · Recharts · Lucide       │
└───────────────────────────────┬──────────────────────────────────┘
                                │ 同源 /api 代理、SSE 进度事件
┌───────────────────────────────▼──────────────────────────────────┐
│ FastAPI · Pydantic · SQLAlchemy Async · Alembic · JWT / Argon2   │
│ 项目、材料、编辑、模板、导出与媒体 API                            │
└───────────────┬──────────────────────────────┬───────────────────┘
                │                              │
     ┌──────────▼──────────┐        ┌──────────▼──────────┐
     │ PostgreSQL 16       │        │ Redis 7 + ARQ        │
     │ 项目/大纲/页面数据  │        │ 队列、进度、重试     │
     └─────────────────────┘        └──────────┬──────────┘
                                                │
                                   ┌────────────▼────────────┐
                                   │ Worker                  │
                                   │ LangGraph 工作流        │
                                   │ LLM / 图像 / 模板分析   │
                                   └────────────┬────────────┘
                                                │
                         ┌──────────────────────▼─────────────────────┐
                         │ 本地存储或对象存储 · python-pptx · ReportLab │
                         └────────────────────────────────────────────┘
```

| 层级 | 已使用的框架、库与职责 |
| --- | --- |
| Web 前端 | **React 19**、TypeScript、Vite、Tailwind CSS 4；React Router 负责路由，TanStack React Query 负责请求缓存与失效更新，Zustand 保存轻量 UI 状态，Recharts/Lucide 分别负责图表与图标。 |
| API 与认证 | **FastAPI**、Pydantic Settings、SQLAlchemy 2 异步 ORM、Alembic；PostgreSQL 保存用户、项目、大纲、页面与任务状态，JWT + pwdlib/Argon2 处理认证。 |
| 实时与异步任务 | **Redis 7** 保存队列协调、取消标记与事件快照；**ARQ** 执行大纲、逐页 PPT、HTML 报告、图片等耗时任务；SSE 将进度回传浏览器。模型或临时网络失败最多尝试 3 次，缺少密钥不会盲目重试。 |
| LLM 与 Prompt | **LangChain Core / langchain-openai** 通过 OpenAI 兼容接口连接文本模型。System Prompt + User Prompt 明确内容密度、页面角色、版式、输出边界；Pydantic schema + JSON mode 约束结构化结果。 |
| LangGraph 工作流 | **LangGraph StateGraph** 编排大纲“准备→生成”、单页“准备→生成→校验→必要时修复”、改稿“生成/工具调用→校验→必要时修复”。这使版式、溢出和结构校验能形成有边界的自纠正回路。 |
| Agent / 工具调用 | 局部改稿使用 `bind_tools`、System/Human/AI/Tool 消息与受限编辑操作，可视为**任务型编辑 Agent**。它只允许改内存中的受控文稿副本，不具备任意文件、Shell 或网络工具权限。 |
| 材料解析 | PDF 使用 pdfplumber，Word 使用 python-docx，Markdown/TXT 使用对应解析器；材料转为带定位信息的章节，再按字数预算送入 Prompt。 |
| PPT 与导出 | python-pptx 输出可编辑 PPTX，FontTools 进行字体度量，ReportLab 输出静态 PDF；同一 Deck 内容模型还可导出 HTML 与 Markdown。 |
| 图片、模板与存储 | 图片会验证 MIME/尺寸后进入项目媒体；支持本地存储或对象存储。Template 解析使用 python-pptx 读取结构，必要时由 Qwen-VL 描述视觉资产、文本模型总结样式。 |

#### AI 能力边界：RAG、Embedding 与 ReAct

当前版本**没有**向量数据库、Embedding 模型、Retriever 或通用的多工具 ReAct Agent。上传材料采用“解析为章节 → 按页/大纲筛选与裁剪 → 直接注入结构化 Prompt”的受控上下文方案，因此不能宣传为向量 RAG。

当前的 LangGraph 状态机、Pydantic 结构化输出、受限工具调用和“校验→修复”循环已经覆盖生成可靠性；未来如果接入 Embedding + 向量检索，可在材料解析层之后增加 Retriever，再把引用片段连同来源定位写入 Prompt 与导出结果。这样可以扩展 RAG，而不破坏现有 PPT/HTML 工作流。

### 项目结构

```text
frontend/   React + TypeScript + Vite 客户端与编辑工作区
backend/    FastAPI、ARQ 任务、模型适配、存储、PPTX 渲染与测试
shared/     前后端共用的主题、视觉规则、布局与示例数据
Template/   可选的自有 PPTX 参考模板
docs/       公开文档与项目截图
```

`shared/` 是运行时单一数据源，前端预览与后端渲染共同使用其中的视觉定义。

### 启动前需要安装

本地 Windows 开发需要以下软件：

- Docker Desktop（开启 WSL 2 后端）与 Docker Compose v2；
- Python 3.12+；
- [uv](https://docs.astral.sh/uv/)；
- Node.js 20+ 与 npm；
- Git（克隆、分支与提交时需要）；
- 可用的文本模型 API Key。图片生成、Qwen-VL 模板视觉分析、Unsplash 和对象存储均可按需要配置，不是启动 API 的硬前置条件。

### 从 GitHub 获取项目

项目发布到 GitHub 后，在 PowerShell 中选择一个工作目录并克隆。将 `<OWNER>` 替换为 GitHub 页面上显示的仓库拥有者：

```powershell
git clone https://github.com/<OWNER>/slide-report-studio.git
cd slide-report-studio
git status
```

已配置 SSH Key 的开发者也可以使用：

```powershell
git clone git@github.com:<OWNER>/slide-report-studio.git
cd slide-report-studio
```

克隆后按下方四终端流程启动。需要获取其他人推送的最新 `main` 时，先确保没有未提交改动，再执行：

```powershell
git switch main
git pull --ff-only origin main
```

`--ff-only` 会在远端历史与本地分叉时停止，而不是自动制造合并提交；此时应先检查分支差异，不要用强制覆盖命令。

### Windows 本地完整启动流程

以下使用四个终端完成：

#### 终端 1：启动 PostgreSQL 与 Redis

先启动 Docker Desktop，确认其完全运行后，在项目根目录执行：

```powershell
cd <项目根目录>
docker compose up -d
docker compose ps
```

`postgres` 与 `redis` 应显示为 `running` / `healthy`。排查基础服务时使用 `docker compose logs postgres redis`。

#### 终端 2：初始化并启动 FastAPI

```powershell
cd <项目根目录>\backend

# 首次执行时创建虚拟环境；uv sync 也会自动维护它
uv venv
.\.venv\Scripts\Activate.ps1
uv sync

# 仅首次复制，之后保留自己填写过的 .env
Copy-Item .env.example .env

# 创建数据库表并下载文字度量字体
uv run alembic upgrade head
uv run python scripts/fetch_fonts.py

# 启动 API
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 39800
```

如 PowerShell 阻止本次会话激活虚拟环境，可先执行 `Set-ExecutionPolicy -Scope Process Bypass`，再激活；这不会修改系统级执行策略。也可以不激活环境，直接使用所有 `uv run ...` 命令。

#### 配置 `backend/.env`

`.env.example` 已提供无密钥的完整注释。首次启动至少确认下列值与本机 Docker 端口一致：

```dotenv
DATABASE_URL=postgresql+asyncpg://luxumbra:luxumbra@localhost:39432/luxumbra
REDIS_URL=redis://localhost:39379/0
JWT_SECRET=<使用下方命令生成的随机值>
LLM_API_KEY=<你的文本模型密钥>
```

可在已完成 `uv sync` 的 backend 目录生成 JWT 密钥：

```powershell
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

`启动流程.txt` 中的 `SECRET_KEY` 与 `postgresql://postgres:postgres...` 属于旧配置，当前代码实际读取的是 `JWT_SECRET` 与 `postgresql+asyncpg://luxumbra:luxumbra@localhost:39432/luxumbra`。请不要把真实 `.env`、模型密钥、数据库密码或服务器信息提交到仓库。

#### 终端 3：启动 ARQ Worker

Worker 必须和 API 同时运行，负责大纲、PPT 页面、HTML 报告、图片与重试任务：

```powershell
cd <项目根目录>\backend
uv run arq app.worker.settings.WorkerSettings
```

#### 终端 4：启动 React / Vite 前端

```powershell
cd <项目根目录>\frontend
npm ci
npm run dev
```

打开 `http://127.0.0.1:39173` 使用应用。前端会将 `/api` 请求代理到 `http://127.0.0.1:39800`；健康检查地址为 `http://127.0.0.1:39800/api/v1/health`。

#### 启动检查清单

1. `docker compose ps` 中 PostgreSQL 与 Redis 健康；
2. API 终端没有数据库、Redis 或配置错误；
3. Worker 终端已连接 Redis；
4. 访问健康检查返回正常组件状态；
5. 浏览器可以登录并完成一次大纲生成。若大纲卡在“生成中”，先检查 Worker 是否运行、Redis 连接串是否正确、模型密钥是否配置；查看 Worker 日志即可获取失败原因。

### 质量检查

```bash
# 后端
cd backend
uv run ruff check .
uv run pytest

# 前端
cd ../frontend
npm run lint
npm run build
```

CI 会在提交至 `main` 及 Pull Request 时重复执行后端与前端检查。

### 参与贡献与安全反馈

- 开发规范：见 [CONTRIBUTING.md](CONTRIBUTING.md)
- 安全问题：见 [SECURITY.md](SECURITY.md)，不要公开提交敏感复现材料、账号、密钥或用户数据。

---

<a id="english"></a>

Slide Report Studio is an AI workspace for editable presentations and dynamic HTML reports. It turns a topic, long-form text, or uploaded material into a reviewable outline, then follows either a native PPT workflow or a fully independent HTML report workflow.


| English                                                                                                                           |
| --------------------------------------------------------------------------------------------------------------------------------- |
| An AI workspace for outline-first editable PPTX decks and dynamic HTML reports, with template analysis and multi-format delivery. |

### Highlights

- **Outline-first creation** — review and edit page titles, points, order, and page count before full generation.
- **Separate PPT and HTML paths** — PPT uses themes, layouts, and editable objects; HTML is authored directly as HTML, CSS, and JavaScript from the confirmed outline and style prompt.
- **Editable PPTX delivery** — main text, charts, tables, and structure are exported as native objects.
- **Interactive HTML reports** — supports animation, navigation, dashboards, tables, barcode/QR components, 2D charts, and 3D visuals with accessible fallbacks.
- **Portable media** — project images are downloaded and validated by the backend, served through same-site relative routes, and embedded in exported standalone HTML files.
- **PPTX template analysis** — owned `.pptx` files in `Template/` can be analysed for backgrounds, images, layout, placement, composition, and visual rules. They apply to PPT only.

### Workflow

```text
Topic / text / documents
          │
          ▼
AI outline → human review and edits
          │
          ├─ PPT  → async slide generation → editing → PPTX / HTML / Markdown / PDF
          └─ HTML → direct HTML + CSS + JS generation → isolated preview → standalone HTML
```

### Architecture

```text
React 19 + TypeScript + Vite + Tailwind CSS
React Router · TanStack Query · Zustand · Recharts · Lucide
                         │ same-origin /api proxy and SSE progress
FastAPI + Pydantic + SQLAlchemy Async + Alembic + JWT / Argon2
                         │
          PostgreSQL 16  │  Redis 7 + ARQ queue / retry / event snapshots
                         │
      LangGraph workflows + LangChain structured model calls + workers
                         │
local/object storage · python-pptx · ReportLab · media/template analysis
```

| Layer | Implemented responsibilities |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, React Router, TanStack React Query, Zustand, Recharts, and Lucide. |
| API and data | FastAPI, Pydantic Settings, SQLAlchemy 2 async ORM, Alembic, PostgreSQL, JWT, and pwdlib/Argon2 authentication. |
| Async and realtime | Redis 7 stores task coordination, cancellation state, and event snapshots. ARQ runs expensive generation jobs; SSE streams progress. Transient model failures are attempted up to three times. |
| Prompt and model layer | LangChain Core and langchain-openai use an OpenAI-compatible model endpoint. System and user prompts describe page role, density, layout, and output limits; Pydantic schemas plus JSON mode validate structured output. |
| LangGraph | StateGraph orchestrates outline preparation/generation, slide preparation/generation/validation/repair, and slide-edit generation/tool calls/validation/repair. |
| Agent and tools | Slide editing uses scoped `bind_tools` calls and System/Human/AI/Tool messages against an in-memory document copy. It has no arbitrary filesystem, shell, or network tool access. |
| Sources and delivery | PDF, DOCX, Markdown, and TXT are parsed into located sections. python-pptx emits editable slides, FontTools measures text, and ReportLab emits static PDF. |
| Media and templates | Project media is MIME/size-validated before local or object storage. python-pptx analyses template structure; Qwen-VL can describe visual assets and the text model can summarize style. |

#### RAG, embeddings, and ReAct scope

The current runtime does **not** include a vector database, embedding model, retriever, or a general autonomous multi-tool ReAct agent. Source files are parsed into sections, budgeted and selected for the relevant outline/slide, then inserted directly into structured prompts. This is controlled prompt context, not vector RAG.

LangGraph state machines, structured output, scoped edit tools, and validation/repair loops are implemented today. An embedding-backed Retriever can later be inserted after source parsing while keeping the PPT and HTML delivery paths intact.

### Prerequisites

For local Windows development, install Docker Desktop with the WSL 2 backend, Docker Compose v2, Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+ with npm, Git, and a text-model API key. Image generation, Qwen-VL template vision, Unsplash, and object storage are optional integrations.

### Clone from GitHub

After the repository is published, choose a local workspace and replace `<OWNER>` with the repository owner shown on GitHub:

```powershell
git clone https://github.com/<OWNER>/slide-report-studio.git
cd slide-report-studio
git status
```

Developers with an SSH key can instead run:

```powershell
git clone git@github.com:<OWNER>/slide-report-studio.git
cd slide-report-studio
```

Follow the four-terminal startup flow below. To retrieve the latest `main` branch, first make sure that the working tree has no uncommitted changes, then run:

```powershell
git switch main
git pull --ff-only origin main
```

`--ff-only` stops when histories diverge instead of creating an unexpected merge commit. Inspect the branch difference rather than using a force operation.

### Complete Windows local startup

The following uses four terminals.

**Terminal 1 — Docker services**

```powershell
cd <project-root>
docker compose up -d
docker compose ps
```

Wait until `postgres` and `redis` are `running` / `healthy`.

**Terminal 2 — backend initialization and API**

```powershell
cd <project-root>\backend
uv venv
.\.venv\Scripts\Activate.ps1
uv sync
Copy-Item .env.example .env
uv run alembic upgrade head
uv run python scripts/fetch_fonts.py
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 39800
```

Set at least these values in the ignored `backend/.env` file:

```dotenv
DATABASE_URL=postgresql+asyncpg://luxumbra:luxumbra@localhost:39432/luxumbra
REDIS_URL=redis://localhost:39379/0
JWT_SECRET=<a random 32-byte-or-longer value>
LLM_API_KEY=<your text-model key>
```

Generate a suitable local JWT secret with:

```powershell
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

The legacy `SECRET_KEY` setting and `postgresql://postgres:postgres...` URL in the local startup note are not the current runtime settings. Use `JWT_SECRET` and the `postgresql+asyncpg` URL above.

**Terminal 3 — ARQ worker**

```powershell
cd <project-root>\backend
uv run arq app.worker.settings.WorkerSettings
```

**Terminal 4 — React/Vite client**

```powershell
cd <project-root>\frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:39173`. The Vite development server proxies `/api` to `http://127.0.0.1:39800`; the health endpoint is `http://127.0.0.1:39800/api/v1/health`.

Check Docker health, API logs, Worker-to-Redis connectivity, and model credentials if a job remains in a generating state. Never commit `.env`, API keys, database passwords, or server details.

### Quality checks

```bash
cd backend
uv run ruff check .
uv run pytest

cd ../frontend
npm run lint
npm run build
```

CI repeats these checks on pull requests and pushes to `main`. Read [CONTRIBUTING.md](CONTRIBUTING.md) before contributing and [SECURITY.md](SECURITY.md) before reporting a security issue.
