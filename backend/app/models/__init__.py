"""
ORM 模型注册入口

集中导入所有 SQLAlchemy 模型，使 Base.metadata 包含全部表定义。
Alembic autogenerate 和 create_all() 依赖此处的完整注册。

表与文件对应关系（对齐 schema.sql 章节编号）：
  1  users                  → user.py
  2  user_configs           → user.py
  3  projects               → project.py
  4  keywords               → project.py
  5  papers                 → paper.py
  6  project_paper_relations → paper.py
  7  stage_records          → stage.py
  8  research_dialogues     → dialogue.py
  9  dialogue_turns         → dialogue.py
  10 review_outlines        → review.py
  11 review_chapters        → review.py
  12 recommendations        → recommendation.py
"""

from app.models.base import Base
from app.models.dialogue import DialogueTurn, ResearchDialogue
from app.models.paper import Paper, ProjectPaperRelation
from app.models.project import Keyword, Project
from app.models.recommendation import Recommendation
from app.models.review import ReviewChapter, ReviewOutline
from app.models.stage import StageRecord
from app.models.user import User, UserConfig

__all__ = [
    "Base",
    # 用户层
    "User",
    "UserConfig",
    # 研究主题层
    "Project",
    "Keyword",
    # 论文层
    "Paper",
    "ProjectPaperRelation",
    # 阶段记录层
    "StageRecord",
    # 深度研究层
    "ResearchDialogue",
    "DialogueTurn",
    # 综述层
    "ReviewOutline",
    "ReviewChapter",
    # 推荐层
    "Recommendation",
]
