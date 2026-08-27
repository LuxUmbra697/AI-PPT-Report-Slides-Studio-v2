from pptx.dml.color import RGBColor

# 混色是纯计算，装饰层生成时也要用，因此实现放在 domain，这里只做转发
from app.domain.color import mix_hex as mix

__all__ = ["mix", "to_rgb"]


def to_rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color.lstrip("#").upper())
