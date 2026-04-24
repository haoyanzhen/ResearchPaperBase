"""
ORM 模型 — 阶段记录层（table 7）

对应 schema.sql：
  Table 7: stage_records — 构建模式（7 阶段）和综述模式（5 阶段）各阶段执行详情

深度研究模式无固定阶段，不使用本表。
当前执行阶段通过查询本表 (project_id + mode，取最新 started_at) 获取，
不在 projects 表冗余存储。
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class StageRecord(Base):
    """
    阶段执行记录表（stage_records）

    构建模式（mode='construction'）阶段：
      1-检索词生成  2-检索与汇总  3-评分与筛选  4-下载与解析
      5-总结生成    6-格式化与储存  7-邮件发送（全自动，无交互暂停）

    综述模式（mode='review'）阶段：
      1-扩写课题内容  2-生成综述架构  3-撰写章节内容
      4-自动审查迭代  5-汇总成综述文章

    CHECK 约束防止非法组合（如 mode='review', stage=7）。
    """

    __tablename__ = "stage_records"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('construction','review')",
            name="chk_stage_records_mode",
        ),
        CheckConstraint(
            "status IN ('running','paused','completed','failed')",
            name="chk_stage_records_status",
        ),
        # 构建模式 stage 合法范围：1-7
        CheckConstraint(
            "NOT (mode = 'construction' AND (stage < 1 OR stage > 7))",
            name="chk_stage_records_stage_construction",
        ),
        # 综述模式 stage 合法范围：1-5
        CheckConstraint(
            "NOT (mode = 'review' AND (stage < 1 OR stage > 5))",
            name="chk_stage_records_stage_review",
        ),
    )

    id:         Mapped[str] = mapped_column(String(50), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    mode:   Mapped[str] = mapped_column(String(20),   nullable=False)   # construction / review
    stage:  Mapped[int] = mapped_column(SmallInteger, nullable=False)   # 构建 1-7；综述 1-5
    status: Mapped[str] = mapped_column(String(20),   nullable=False)   # running/paused/completed/failed

    # 时间戳：started_at 由应用层在启动任务时写入，无 server_default
    started_at:   Mapped[datetime]       = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resumed_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 阶段产出物（各阶段 JSONB 结构见 frontend/types/index.ts Stage1Result~Stage7Result）
    result:       Mapped[dict | None] = mapped_column(JSONB)
    error:        Mapped[str | None]  = mapped_column(Text)
    # 用户在交互暂停点的操作记录（接受/编辑/重新执行/继续，见 UserAction 类型）
    user_actions: Mapped[list | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        back_populates="stage_records", lazy="noload"
    )
