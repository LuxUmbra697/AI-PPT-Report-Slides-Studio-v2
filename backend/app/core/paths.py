from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# 布局与主题的单一真源。Web 端与 PPTX 端加载的是同一批文件，
# 两端各自维护一套排版规则的可能性从物理上被排除。
SHARED_DIR = REPO_ROOT / "shared"
LAYOUTS_DIR = SHARED_DIR / "layouts"
THEMES_DIR = SHARED_DIR / "themes"
# 用户放入的参考 PPTX 模板目录。它和 shared/themes 的内置主题分开：
# 前者可随时增删，并由运行时解析；后者则是随前端构建发布的精选预设。
TEMPLATE_DIR = REPO_ROOT / "Template"
TEMPLATE_ANALYSIS_CACHE = REPO_ROOT / "backend" / "var" / "template-analysis-cache.json"
