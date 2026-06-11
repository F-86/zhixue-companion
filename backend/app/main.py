import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# force=True 强制覆盖 uvicorn 的日志配置，确保所有 logger.info 输出到 stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

from app.core.config import settings
from app.db.init_db import init_db
from app.db.vector_store import init_vector_store
from app.services import minimax_client

# 模块加载时立即创建必要目录，确保 StaticFiles mount 不报错
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.log_dir, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表（关系数据库）
    init_db()
    # 启动时初始化向量数据库
    init_vector_store()
    # 预热 MiniMax HTTP 连接池
    minimax_client._get_client()
    logger.info("智学伴侣 API 已启动")
    yield
    # 关闭时释放 HTTP 连接池
    minimax_client.close()


app = FastAPI(title="智学伴侣 API", version="0.2.0", lifespan=lifespan)

# CORS（开发阶段允许所有来源，生产环境按需收窄）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 上传文件静态访问
app.mount("/files", StaticFiles(directory=settings.upload_dir), name="files")

# ── 注册路由 ──────────────────────────────────────────────────
from app.api import (  # noqa: E402
    routes_auth,
    routes_courses,
    routes_sections,
    routes_announcements,
    routes_discussions,
    routes_questions,
    routes_scores,
    routes_chat,
    routes_summaries,
    routes_learning_plans,
    routes_quizzes,
    routes_upload,
    routes_student_assignments,
    routes_teacher_assignments,
)

app.include_router(routes_auth.router, prefix="/api")
app.include_router(routes_courses.router, prefix="/api")
app.include_router(routes_sections.router, prefix="/api")
app.include_router(routes_announcements.router, prefix="/api")
app.include_router(routes_discussions.router, prefix="/api")
app.include_router(routes_questions.router, prefix="/api")
app.include_router(routes_scores.router, prefix="/api")
app.include_router(routes_chat.router, prefix="/api")
app.include_router(routes_summaries.router, prefix="/api")
app.include_router(routes_learning_plans.router, prefix="/api")
app.include_router(routes_quizzes.router, prefix="/api")
app.include_router(routes_upload.router, prefix="/api")
app.include_router(routes_student_assignments.router, prefix="/api")
app.include_router(routes_teacher_assignments.router, prefix="/api")


# ── 健康检查 ──────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"success": True, "data": {"status": "ok", "service": "zhixue-companion-api"}, "message": "ok"}


# ── 全局异常处理 ──────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": str(exc)}},
    )
