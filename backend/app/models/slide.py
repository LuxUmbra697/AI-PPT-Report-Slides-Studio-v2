import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

SlideStatus = Literal["pending", "generating", "ready", "failed"]


class Slide(Base):
    """一页正式内容。

    以大纲页 id 作为幂等键：重试、断点恢复和重复入队都落到同一行，
    不会因为再跑一次任务就多出一页。
    """

    __tablename__ = "slides"
    __table_args__ = (
        UniqueConstraint("project_id", "outline_page_id", name="uq_slides_project_outline_page"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    outline_page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    position: Mapped[int] = mapped_column(Integer, nullable=False)
    layout_id: Mapped[str] = mapped_column(String(50), nullable=False)
    layout_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="flex")
    layout_tree: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 大纲标题先行落库，页面还没生成时进度列表也能显示这一页是什么
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    blocks: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    speaker_notes: Mapped[str | None] = mapped_column(Text)
    issues: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text)

    # 乐观锁：AI 局部修改与人工编辑提交时带上它，不一致即判冲突
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="slides")  # noqa: F821
