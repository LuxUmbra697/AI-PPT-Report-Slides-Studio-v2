# LuxUmbra Slides

LuxUmbra Slides 是一个面向中文场景的 AI 演示文稿生成与编辑平台。它支持从主题、长文本和文档材料生成结构化大纲，再通过异步任务并发产出完整页面，最终导出为可继续编辑的原生 PPTX。

项目采用 Python 全栈架构：后端基于 FastAPI、LangChain、LangGraph、ARQ 与 python-pptx，前端基于 React、TypeScript 与 Vite。系统围绕“先生成可控大纲，再逐页生成内容，再在线编辑和导出”的工作流设计，重点解决生成速度、可编辑性、结构一致性与导出质量问题。

## 核心能力

- 多入口生成：支持主题、长文本、PDF、Word、Markdown、TXT 等输入方式
- 大纲先行：先生成结构化大纲，支持修改标题、要点、顺序和页数
- 异步并发：页级任务并发生成，配合 Redis 与 SSE 实时反馈进度
- 在线编辑：支持文本编辑、版式切换、主题切换、图片替换与 AI 局部修改
- 原生导出：导出为可继续编辑的 PPTX，而不是整页截图
- 质量校验：导出前执行结构、溢出、边界与内容完整性检查

## 技术栈

- Backend: FastAPI, SQLAlchemy, Alembic, ARQ, Redis, PostgreSQL
- AI: LangChain, LangGraph, DeepSeek-compatible API
- Rendering: python-pptx, FontTools
- Frontend: React, TypeScript, Vite, Tailwind CSS, React Query, Zustand

## 系统结构

- `backend/`: Python API、异步任务、领域逻辑、PPTX 渲染与测试
- `frontend/`: Web 客户端、编辑器界面、预览与交互逻辑
- `shared/`: 前后端共享的主题、布局、样例文稿与排版预设

`shared/` 是项目运行所需的配置源。前端直接读取主题与布局定义，后端也依赖同一套 JSON 做生成、校验和导出，因此它不是演示素材目录，而是系统的一部分。

## 运行方式

1. 启动基础依赖
2. 安装前后端依赖
3. 配置 `backend/.env`
4. 启动 API、Worker 与前端

```bash
make up
make install
make migrate
make dev-api
make dev-worker
make dev-web
```

## 默认端口

- Frontend: `http://127.0.0.1:39173`
- API: `http://127.0.0.1:39800`
- PostgreSQL: `127.0.0.1:39432`
- Redis: `127.0.0.1:39379`

## 项目定位

LuxUmbra Slides 关注的不是一次性生成静态页面，而是构建一个完整的 AI 文稿工作流：输入材料、生成大纲、并发出稿、人工编辑、质量校验、最终导出。这使它更适合需要“可生成、可修改、可交付”的真实业务场景。

## Attribution

This repository is a customized and independently maintained LuxUmbra-branded distribution of an AI presentation workflow project. If you publish it externally, please make sure your usage complies with the original upstream license and attribution requirements.
