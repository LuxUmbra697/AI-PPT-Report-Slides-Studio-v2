from pptx.oxml.ns import qn
from pptx.table import Table, _Cell

# PowerPoint 内置的"无样式无网格"。不套用它的话，表格会自带蓝白斑马纹与竖向网格线，
# 主题配色会被盖掉，且与 Web 端的横线表格观感不一致。
NO_STYLE_NO_GRID = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"

# tcPr 下边框元素必须按 schema 顺序排在填充之前
_BORDER_TAGS = ("a:lnL", "a:lnR", "a:lnT", "a:lnB")


def use_plain_style(table: Table) -> None:
    table.first_row = False
    table.horz_banding = False

    tbl_pr = table._tbl.find(qn("a:tblPr"))
    if tbl_pr is None:
        return

    for existing in tbl_pr.findall(qn("a:tableStyleId")):
        tbl_pr.remove(existing)

    style_id = tbl_pr.makeelement(qn("a:tableStyleId"), {})
    style_id.text = NO_STYLE_NO_GRID
    tbl_pr.append(style_id)


def set_cell_borders(cell: _Cell, bottom: tuple[float, str] | None = None) -> None:
    """显式声明四边边框，只保留需要的那条。

    未声明的边会继承表格样式，因此"不要某条边"也必须显式写成无填充。
    """
    tc_pr = cell._tc.get_or_add_tcPr()

    for tag in _BORDER_TAGS:
        for existing in tc_pr.findall(qn(tag)):
            tc_pr.remove(existing)

    # 倒序插到最前，最终顺序即 lnL、lnR、lnT、lnB
    for tag in reversed(_BORDER_TAGS):
        line = tc_pr.makeelement(qn(tag), {})
        if tag == "a:lnB" and bottom is not None:
            width_pt, color = bottom
            line.set("w", str(round(width_pt * 12700)))
            line.set("cap", "flat")
            fill = tc_pr.makeelement(qn("a:solidFill"), {})
            fill.append(tc_pr.makeelement(qn("a:srgbClr"), {"val": color.lstrip("#").upper()}))
            line.append(fill)
        else:
            line.append(tc_pr.makeelement(qn("a:noFill"), {}))
        tc_pr.insert(0, line)
