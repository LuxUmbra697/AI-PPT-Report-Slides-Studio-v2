import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

ProjectStatus = Literal["draft", "outline_ready", "generating", "ready"]
SourceKind = Literal["topic", "text", "document"]


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # 删除用户时连带清理其项目，避免留下无主数据
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    audience: Mapped[str | None] = mapped_column(String(100))
    tone: Mapped[str] = mapped_column(String(32), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    theme_id: Mapped[str] = mapped_column(String(50), nullable=False)
    # 相对 theme_id 预设的局部覆盖；空对象表示纯预设
    theme_overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # fixed=槽位布局；flex=布局树（新项目默认）
    layout_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="flex")
    # 整份文字量：concise / medium / detailed
    content_density: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    sources: Mapped[list["ProjectSource"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectSource.created_at",
        lazy="selectin",
    )
    outline: Mapped["ProjectOutline | None"] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )
    slides: Mapped[list["Slide"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Slide.position",
    )


class ProjectSource(Base):
    """项目的一份输入材料：一句主题、一段长文本，或一个上传的文档。"""

    __tablename__ = "project_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)

    filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    # 原始文件在对象存储中的键，纯文本输入为空
    storage_key: Mapped[str | None] = mapped_column(String(512))

    # 解析出的小节列表。结构随解析器演进，用 JSONB 存避免频繁改表；
    # 而项目本身的字段要参与筛选与排序，因此仍用独立列。
    sections: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="sources")


class ProjectOutline(Base):
    __tablename__ = "project_outlines"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_outlines_project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="generating")
    pages: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    job_id: Mapped[str | None] = mapped_column(String(100))
    input_signature: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="outline")
