import hashlib
import json

from app.models.project import Project
from app.schemas.project import MAX_DECK_PAGE_COUNT, MIN_DECK_PAGE_COUNT


def _hash_payload(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _core_payload(project: Project) -> dict:
    return {
        "title": project.title,
        "audience": project.audience,
        "tone": project.tone,
        "sources": [
            {
                "id": str(source.id),
                "sections": source.sections,
            }
            for source in project.sources
        ],
    }


def project_input_signature(project: Project) -> str:
    """计算影响大纲的输入指纹。

    大纲草稿生成后仍允许用户调整设置或材料，但确认时必须发现它已经过期，
    不能把旧大纲与新输入静默绑定。

    不含 page_count：确认大纲页可增删页并同步目标页数，页数由
    ``len(pages) == project.page_count`` 单独校验；把它放进指纹会在
    「只改了页数」时误报需要重新生成。
    """
    return _hash_payload(_core_payload(project))


def _legacy_signature_with_page_count(project: Project, page_count: int) -> str:
    """legacy 指纹：core + page_count，兼容库中已写入的签名。"""
    return _hash_payload({**_core_payload(project), "page_count": page_count})


def outline_input_matches(project: Project, stored: str | None) -> bool:
    """当前输入是否仍与生成大纲时的指纹一致（含 legacy 公式兼容）。"""
    if not stored:
        return False
    if stored == project_input_signature(project):
        return True
    # legacy 签名含 page_count：core 未变且任意合法页数能对上即放行。
    # 范围按编辑器边界取，页面手工增删后页数可能已经超出创建时的区间。
    return any(
        stored == _legacy_signature_with_page_count(project, count)
        for count in range(MIN_DECK_PAGE_COUNT, MAX_DECK_PAGE_COUNT + 1)
    )


def migrate_outline_signature(project: Project, stored: str | None) -> str | None:
    """若仅因 legacy 公式/页数差异而匹配，返回应写回的新指纹；否则 None。"""
    if not stored or stored == project_input_signature(project):
        return None
    if outline_input_matches(project, stored):
        return project_input_signature(project)
    return None
