from __future__ import annotations

import json

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import ValidationError

from app.domain.content_density import density_prompt_block
from app.domain.flex_layout import iter_leaf_block_ids
from app.domain.flex_normalize import normalize
from app.domain.flex_presets import BlockRef, seed_layout_for_blocks
from app.domain.layout import Layout, Slot, get_layout
from app.domain.slide_draft import FlexSlideDraft, SlideDraft
from app.llm.base import SlideGenerationInput
from app.llm.client import StructuredChatClient
from app.llm.errors import InvalidModelOutputError, InvalidSlideOutputError


class DeepSeekSlideGenerator:
    """把一页大纲展开成填进布局槽位的正文内容。

    槽位与容量上限直接写进提示词：布局是硬约束，与其事后裁剪
    模型写超的内容，不如一开始就把可用空间告诉它。
    """

    def __init__(
        self,
        *,
        model: BaseChatModel | None = None,
        api_key: str = "",
        chat: StructuredChatClient | None = None,
    ) -> None:
        if chat is not None:
            self._chat = chat
        elif model is not None:
            self._chat = StructuredChatClient(model=model, api_key=api_key)
        else:
            raise TypeError("需要 model 或 chat")

    async def generate(self, payload: SlideGenerationInput) -> SlideDraft | FlexSlideDraft:
        if payload.layout_mode == "flex":
            return await self._generate_flex(payload)
        return await self._generate_fixed(payload)

    async def _generate_fixed(self, payload: SlideGenerationInput) -> SlideDraft:
        layout = get_layout(payload.layout_id)
        try:
            draft = await self._chat.complete(
                SlideDraft,
                system=self._system_prompt(layout),
                user=self._user_prompt(payload, layout),
                purpose="生成页面内容",
            )
        except (InvalidModelOutputError, ValidationError) as error:
            raise InvalidSlideOutputError("模型返回的页面 JSON 不符合约定结构") from error

        self._validate_draft(draft, layout)
        return draft

    async def _generate_flex(self, payload: SlideGenerationInput) -> FlexSlideDraft:
        try:
            draft = await self._chat.complete(
                FlexSlideDraft,
                system=self._flex_system_prompt(payload),
                user=self._flex_user_prompt(payload),
                purpose="生成灵活布局页面",
            )
        except (InvalidModelOutputError, ValidationError) as error:
            raise InvalidSlideOutputError("模型返回的灵活布局 JSON 不符合约定结构") from error

        return self._finalize_flex_draft(draft, payload)

    def _finalize_flex_draft(
        self, draft: FlexSlideDraft, payload: SlideGenerationInput
    ) -> FlexSlideDraft:
        """规范化布局树并校验叶子与块 id；不一致或规范化异常时回退为预设种子树。"""
        block_ids = {block.id for block in draft.blocks}
        if len(block_ids) != len(draft.blocks):
            raise InvalidSlideOutputError("内容块 id 重复")

        def with_seeded_tree() -> FlexSlideDraft:
            refs = [BlockRef(id=block.id, type=block.type) for block in draft.blocks]
            seeded = seed_layout_for_blocks(
                refs,
                page_role=payload.page_role,
                key_points=list(payload.key_points),
            )
            return draft.model_copy(update={"layout_tree": seeded})

        try:
            # normalize 是纯变换，无稳定领域异常类型；宽捕获以保留「树异常 → 种子」降级
            tree = normalize(draft.layout_tree)
        except Exception:
            return with_seeded_tree()

        leaf_ids = set(iter_leaf_block_ids(tree))
        if leaf_ids != block_ids:
            return with_seeded_tree()
        return draft.model_copy(update={"layout_tree": tree})

    def _system_prompt(self, layout: Layout) -> str:
        return (
            "你是 PPT 正文撰写助手。必须只输出一个 JSON 对象，不要 Markdown，不要额外说明。\n"
            'JSON 结构必须为：{"blocks":[...],"speaker_notes":"..."}\n'
            "blocks 中每个元素都必须带 slot_id 与 type，并按类型提供对应字段：\n"
            '- text: {"slot_id":"title","type":"text","text":"..."}\n'
            '- bullets: {"slot_id":"body","type":"bullets","items":["...","..."]}\n'
            '- image: {"slot_id":"visual","type":"image","alt":"这张图应该表达什么"}\n'
            '- kpi: {"slot_id":"kpi_1","type":"kpi","value":"37%","label":"...","note":"..."}\n'
            '- table: {"slot_id":"body","type":"table","header":["..."],"rows":[["..."]]}\n'
            '- chart: {"slot_id":"visual","type":"chart","chart_type":"bar",'
            '"categories":["..."],"series":[{"name":"...","values":[1,2]}],"unit":"%"}\n'
            '- cards: {"slot_id":"body","type":"cards",'
            '"items":[{"title":"...","desc":"...","icon":"💡"}]}\n'
            '- callout: {"slot_id":"note","type":"callout","text":"...","icon":null,'
            '"variant":"note"|"source"}\n'
            "硬性约束：\n"
            "1. 只能使用下面列出的 slot_id，每个槽位最多出现一次，必填槽位不得缺失。\n"
            "2. 每个槽位只能使用它声明接受的 type。\n"
            "3. 严格遵守每个槽位的字数与条目上限；在上限内尽量写满支撑细节，贴近容量中上沿。\n"
            "4. 正文使用中文，写具体结论与事实，不写「本页介绍……」这类空话。\n"
            "5. 数字必须来自给定来源，缺少数据时不要编造，改用文字表述。\n"
            "6. speaker_notes 用 2–3 句话给出讲稿提示。\n"
            f"本页布局为 {layout.id}（{layout.name}）：{layout.usage}"
        )

    def _flex_system_prompt(self, payload: SlideGenerationInput) -> str:
        return _FLEX_SYSTEM_PROMPT + _page_directives(payload)

    def _user_prompt(self, payload: SlideGenerationInput, layout: Layout) -> str:
        body = {
            "deck_title": payload.deck_title,
            "audience": payload.audience,
            "tone": payload.tone,
            "content_density": payload.content_density,
            "page_role": payload.page_role,
            "page": {
                "position": payload.position,
                "total_pages": payload.total_pages,
                "title": payload.page_title,
                "objective": payload.objective,
                "key_points": payload.key_points,
            },
            "neighbor_titles": payload.neighbor_titles,
            "slots": [_slot_spec(slot) for slot in layout.slots],
            "sections": [
                {"ref": s.ref, "heading": s.heading, "text": s.text} for s in payload.sections
            ],
        }
        prompt = (
            "请为以下页面生成正文 JSON。\n"
            f"{density_prompt_block(payload.content_density, payload.page_role)}\n"
            f"{json.dumps(body, ensure_ascii=False)}"
        )
        if payload.issues:
            prompt += (
                "\n上一次生成存在以下问题，请只修正这些问题并保持其余内容稳定："
                "若问题是内容过瘦或空话，请充实到密度带，勿超槽位上限；"
                "不要为消除溢出而删光支撑细节。\n"
                + "\n".join(f"- {issue}" for issue in payload.issues)
            )
        return prompt

    def _flex_user_prompt(self, payload: SlideGenerationInput) -> str:
        body = {
            "deck_title": payload.deck_title,
            "audience": payload.audience,
            "tone": payload.tone,
            "content_density": payload.content_density,
            "page_role": payload.page_role,
            "page": {
                "position": payload.position,
                "total_pages": payload.total_pages,
                "title": payload.page_title,
                "objective": payload.objective,
                "key_points": payload.key_points,
            },
            "neighbor_titles": payload.neighbor_titles,
            "hint_layout_id": payload.layout_id,
            "visual": payload.visual_hint,
            "sections": [
                {"ref": s.ref, "heading": s.heading, "text": s.text} for s in payload.sections
            ],
        }
        prompt = (
            "请为以下页面生成灵活布局正文 JSON（blocks + layout_tree）。\n"
            f"{density_prompt_block(payload.content_density, payload.page_role)}\n"
            f"{json.dumps(body, ensure_ascii=False)}"
        )
        if payload.issues:
            prompt += (
                "\n上一次生成存在以下问题，请只修正这些问题并保持其余内容稳定："
                "若问题是内容过瘦或空话，请充实到密度带并保持多块结构；"
                "不要为消除溢出而合并/删掉内容块。\n"
                + "\n".join(f"- {issue}" for issue in payload.issues)
            )
        return prompt

    def _validate_draft(self, draft: SlideDraft, layout: Layout) -> None:
        # 结构性错误在这里就拦掉，避免把非法槽位写进数据库再靠渲染兜底
        seen: set[str] = set()
        for block in draft.blocks:
            slot = layout.slot_by_id(block.slot_id)
            if slot is None:
                raise InvalidSlideOutputError(f"布局 {layout.id} 不存在槽位 {block.slot_id}")
            if block.slot_id in seen:
                raise InvalidSlideOutputError(f"槽位 {block.slot_id} 被重复填充")
            if block.type not in slot.accepts:
                raise InvalidSlideOutputError(
                    f"槽位 {slot.id} 只接受 {'、'.join(slot.accepts)}，实际为 {block.type}"
                )
            seen.add(block.slot_id)

        missing = [slot.id for slot in layout.slots if slot.required and slot.id not in seen]
        if missing:
            raise InvalidSlideOutputError(f"必填槽位缺少内容：{'、'.join(missing)}")


_FLEX_SYSTEM_PROMPT = (
    "你是 PPT 正文与灵活排版助手。必须只输出一个 JSON 对象，不要 Markdown，不要额外说明。\n"
    'JSON 结构必须为：{"blocks":[...],"layout_tree":{...},"speaker_notes":"..."}\n'
    "blocks 使用本地 id（如 b1、title、body），每个元素带 id 与 type：\n"
    '- text: {"id":"title","type":"text","text":"..."}\n'
    '- bullets: {"id":"body","type":"bullets","items":["...","..."]}\n'
    '- image: {"id":"visual","type":"image","alt":"这张图应该表达什么"}\n'
    '- kpi: {"id":"kpi_1","type":"kpi","value":"37%","label":"...","note":"..."}\n'
    '- table: {"id":"table","type":"table","header":["..."],"rows":[["..."]]}\n'
    '- chart: {"id":"chart","type":"chart","chart_type":"bar",'
    '"categories":["..."],"series":[{"name":"...","values":[1,2]}],"unit":"%"}\n'
    '- cards: {"id":"cards","type":"cards",'
    '"items":[{"title":"...","desc":"...","icon":"💡"}]}\n'
    '- callout: {"id":"note","type":"callout","text":"...","icon":null,'
    '"variant":"note"|"source"}\n'
    "callout 是强调：variant=source 写数据出处，variant=note 写行动建议或提醒，"
    "用量以本页约束为准。cards 适合「小标题+描述」要点组。\n"
    "layout_tree 是嵌套的 row/column/block 树，不含坐标：\n"
    '- 容器: {"type":"row"|"column","id":"...","gap_pt":16,"grow":1,'
    '"ratios":[50,50],"children":[...]}\n'
    '- 叶子: {"type":"block","id":"leaf-xxx","block_id":"<对应 blocks[].id>",'
    '"grow":1,"text_style":"title"|"body"|"bullet"|null,"bleed":false}\n'
    "内容默认渲染在页面安全区内（四周留边）；bleed 只给封面/章节页贴边的整幅"
    "image/chart 使用，让它顶到画布边缘，文字块一律不得设 bleed。\n"
    "硬性约束：\n"
    "1. layout_tree 所有叶子的 block_id 必须与 blocks[].id 一一对应，不多不少。\n"
    "2. ratios 仅用于 row，且取值来自 {33,38,50,62,67}，两列之和应为 100。\n"
    "3. 嵌套深度不超过 3；同一 row 最多 4 个子节点。\n"
    "4. grow 建议在 0.25–4；标题类 text_style 用 title/subtitle，grow 宜偏小。\n"
    "5. 正文使用中文，写具体结论与事实；数字须来自给定来源。\n"
    "6. speaker_notes 用 2–3 句话给出讲稿提示。\n"
    "7. 一页必须用多个内容块丰富表达（标题 + 要点 + KPI/图/表等），"
    "禁止只有一个大块；按用户给定的文字量档位与页型组织块数与组合。"
)


def _page_directives(payload: SlideGenerationInput) -> str:
    """逐页追加的硬约束。

    配图与版式骨架都是"整份看才成立"的节奏，各页并发生成时互相看不见，
    所以由编排层提前分配好、在这里落成本页不可商量的命令。
    """
    rules: list[str] = []
    if payload.visual_hint:
        rules.append(
            f"本页必须包含且仅包含一个 image 块，alt 严格写成「{payload.visual_hint}」，"
            "且不得设 bleed。"
        )
    if payload.skeleton_hint:
        rules.append(f"本页版式必须按此骨架组织：{payload.skeleton_hint}。")
    if not payload.allow_callout:
        rules.append(
            "本页不得出现 callout 块（note 与 source 都不行）；"
            "数据出处写进 kpi 的 note 或正文句尾。"
        )
    else:
        rules.append("本页最多使用一个 callout 块。")
    return "".join(f"\n{index}. {rule}" for index, rule in enumerate(rules, start=8))


def _slot_spec(slot: Slot) -> dict:
    capacity = slot.capacity.model_dump(exclude_none=True)
    return {
        "slot_id": slot.id,
        "accepts": list(slot.accepts),
        "required": slot.required,
        "capacity": capacity,
    }
