from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# 布局与主题的单一真源。Web 端与 PPTX 端加载的是同一批文件，
# 两端各自维护一套排版规则的可能性从物理上被排除。
SHARED_DIR = REPO_ROOT / "shared"
LAYOUTS_DIR = SHARED_DIR / "layouts"
THEMES_DIR = SHARED_DIR / "themes"
