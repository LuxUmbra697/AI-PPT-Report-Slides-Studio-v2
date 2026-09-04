# Contributing to Slide Report Studio

Thanks for taking an interest in improving Slide Report Studio. The project combines a browser editor, asynchronous AI jobs, native PPTX rendering, and standalone HTML reports, so a small change can affect more than one delivery path.

## Before you start

1. Search existing issues and open one before beginning a large feature or breaking change.
2. Never add credentials, personal datasets, customer documents, private templates, or generated runtime media to a pull request.
3. Keep PPT and HTML behaviour intentionally separate: a change to one path must not make the other inherit its theme, canvas, or export assumptions.

## Local development

See the [README](README.md#quick-start) for prerequisites and bootstrapping. Copy `backend/.env.example` to `backend/.env` and use your own development credentials; the real file is ignored by Git.

Run the relevant checks before opening a pull request:

```bash
cd backend
uv run ruff check .
uv run pytest

cd ../frontend
npm run lint
npm run build
```

## Pull request expectations

- Keep each pull request focused and explain the user-visible outcome.
- Add or update automated tests for changed backend behaviour.
- For visual changes, include screenshots or a concise verification note.
- Test an outline through its complete intended path: review, generation, preview/editing, and export/download.
- Preserve accessibility basics: semantic controls, keyboard operation, readable contrast, and text alternatives for meaningful imagery.
- Do not commit build artefacts, `.env` files, logs, local runbooks, caches, or `backend/var/` media.

## Architecture guardrails

- `shared/` is used by both frontend and backend. Update compatibility deliberately.
- PPTX output must stay editable; avoid rasterising a whole slide to solve a layout issue.
- HTML reports are model-authored `HTML + CSS + JS` documents. They must remain isolated from the host application and offline exports must remain self-contained.
- Remote executable scripts, iframes, machine paths, and unvalidated remote assets are not valid HTML-report dependencies.

## Reporting security issues

Do not open a public issue for a suspected vulnerability. Read [SECURITY.md](SECURITY.md) first.
