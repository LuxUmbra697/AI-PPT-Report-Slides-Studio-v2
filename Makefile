.PHONY: up down install fonts dev-api dev-worker dev-web migrate migration test lint gen-api regression

up:
	docker compose up -d

down:
	docker compose down

install:
	cd backend && uv sync
	cd frontend && npm install

# 文字溢出度量字体：本地下载，不进仓库。已存在则跳过。
fonts:
	cd backend && uv run python scripts/fetch_fonts.py

dev-api:
	cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 39800

dev-worker:
	cd backend && uv run arq app.worker.settings.WorkerSettings

dev-web:
	cd frontend && npm run dev

migrate:
	cd backend && uv run alembic upgrade head

# 用法：make migration m="描述"
# autogenerate 产出的代码不满足行宽约束，顺手格式化，免得每次手动收拾
migration:
	cd backend && uv run alembic revision --autogenerate -m "$(m)" \
		&& uv run ruff format alembic/versions \
		&& uv run ruff check --fix alembic/versions

# 前端接口类型由后端 OpenAPI 生成，两端类型不会各写一份而分叉。
# 直接从应用对象导出 schema，因此不需要先把服务跑起来。
gen-api:
	cd backend && uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi(), ensure_ascii=False))" > ../frontend/openapi.json
	cd frontend && npx openapi-typescript openapi.json -o src/api/schema.d.ts

test:
	cd backend && uv run pytest

# 固定回归集：语料 × 3 主题，可编辑性 100% 且溢出槽位比例 < 5%。
regression:
	cd backend && uv run python scripts/run_regression.py

lint:
	cd backend && uv run ruff check .
