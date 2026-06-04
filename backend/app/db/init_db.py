from app.db.session import Base, engine

# 导入所有模型，确保建表时已注册
import app.models.user  # noqa: F401
import app.models.course  # noqa: F401
import app.models.section  # noqa: F401
import app.models.assignment  # noqa: F401
import app.models.submission  # noqa: F401
import app.models.grade  # noqa: F401
import app.models.analysis_report  # noqa: F401
import app.models.chat  # noqa: F401
import app.models.summary  # noqa: F401
import app.models.learning_plan  # noqa: F401
import app.models.announcement  # noqa: F401
import app.models.discussion  # noqa: F401
import app.models.question  # noqa: F401
import app.models.quiz  # noqa: F401
import app.models.plan_progress  # noqa: F401


def init_db() -> None:
    """创建所有数据表（若不存在）"""
    Base.metadata.create_all(bind=engine)
