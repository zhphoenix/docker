"""FastAPI 应用入口 - 实例化、中间件、生命周期"""

import logging
import uuid
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.chat import router as chat_router
from api.models import router as models_router
from api.health import router as health_router
from api.providers import router as providers_router
from api.tasks import router as tasks_router
from api.approvals import router as approvals_router
from api.agents import router as agents_router
from api.documents import router as documents_router
from api.research import router as research_router
from api.reports import router as reports_router
from api.knowledge import router as knowledge_router
from api.vector import router as vector_router
from api.news import news_router
from api.watchlist import watchlist_router
from tools.postgres import postgres_tool

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("Starting AI Platform Agent Service...")
    await postgres_tool.connect()
    logger.info("PostgreSQL connection pool ready")

    # Apache AGE 图存储（可选，失败不阻塞）
    from storage.knowledge.age import knowledge_age
    try:
        await knowledge_age.connect()
    except Exception as e:
        logger.info("AGE storage init skipped: %s", e)

    # 注册 Skills
    from skills.registry import register_skill
    from skills.rag_search import RAGSearchSkill
    from skills.master_analysis import MasterAnalysisSkill
    from skills.web_article_summary import WebArticleSummarySkill
    register_skill(RAGSearchSkill())
    register_skill(MasterAnalysisSkill())
    register_skill(WebArticleSummarySkill())
    logger.info("Skills registered")

    # 启动 Scheduler
    from runtime.scheduler import start_scheduler
    start_scheduler()

    # 启动 Task Worker
    from runtime.worker import start_worker
    start_worker()

    yield

    # 关闭时
    logger.info("Shutting down AI Platform Agent Service...")
    from runtime.worker import stop_worker
    stop_worker()
    from runtime.scheduler import stop_scheduler
    stop_scheduler()
    from tools.llm import llm_tool
    from tools.embedding import embedding_tool
    from tools.reranker import reranker_tool
    from tools.docling import docling_tool
    await llm_tool.close()
    await embedding_tool.close()
    await reranker_tool.close()
    await docling_tool.close()
    await postgres_tool.close()
    from storage.knowledge.age import knowledge_age
    await knowledge_age.close()


# 创建 FastAPI 实例
app = FastAPI(
    title="AI Platform Agent Service",
    description="OpenAI Compatible API for AI Research Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID 中间件
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s | %s %s | status=%d | duration=%.2fs",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration,
    )
    return response


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "Internal server error",
                "type": "server_error",
            }
        },
    )


# 注册路由
app.include_router(health_router)
app.include_router(models_router)
app.include_router(chat_router)
app.include_router(providers_router)
app.include_router(tasks_router)
app.include_router(approvals_router)
app.include_router(agents_router)
app.include_router(documents_router)
app.include_router(research_router)
app.include_router(reports_router)
app.include_router(knowledge_router)
app.include_router(vector_router)
app.include_router(news_router)
app.include_router(watchlist_router)
