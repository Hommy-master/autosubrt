from fastapi import FastAPI
from contextlib import asynccontextmanager
import router
import asr
import cleanup
import config
import punctuation
import middlewares
from logger import logger


# 1. 加载模型
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---------------- 启动 ----------------
    # await create_db_pool()
    # await start_redis()
    logger.info("✅ app start")
    # 计费开关只认 "true"，这里显式打出生效值，避免误写成 ENABLE_APIKEY=1 时计费被静默关闭
    logger.info(
        "Billing: ENABLE_APIKEY=%s, POINTS_PER_SECOND=%s",
        config.ENABLE_APIKEY,
        config.POINTS_PER_SECOND,
    )
    # 先清理上次被强杀时残留的临时文件，再去加载模型，避免磁盘被残留文件占满
    await cleanup.start()
    # 在应用启动时加载模型
    asr.load_model()
    punctuation.load_model()
    yield
    # ---------------- 关闭 ----------------
    # await close_db_pool()
    # await stop_redis()
    await cleanup.stop()
    logger.info("❌ app shutdown")

# 2. 创建FastAPI应用
app = FastAPI(title="AutoSubRT API", description="语音转SRT字幕服务", lifespan=lifespan)

# 3. 注册路由
app.include_router(router.router, prefix="/openapi/autosubrt", tags=["AutoSubRT"])

# 4. 添加中间件
app.add_middleware(middlewares.PrepareMiddleware)
# 注册统一响应处理中间件（注意顺序，应该在其他中间件之后注册）
app.add_middleware(middlewares.ResponseMiddleware)

# 5. 打印所有路由
for r in app.routes:
    # 1. 取 HTTP 方法列表
    methods = getattr(r, "methods", None) or [getattr(r, "method", "WS")]
    # 2. 取路径
    path = r.path
    # 3. 取函数名
    name = r.name
    logger.info("Route: %s %s -> %s", ",".join(sorted(methods)), path, name)

if __name__ == "__main__":
    import uvicorn
    logger.info("Start AutoSubRT Service ...")
    # log_config=None：不让 uvicorn 用自己的配置覆盖 logger.py 里的 handler，
    # 否则 uvicorn 的启动与访问日志只会打到 stdout，不会写进日志文件
    uvicorn.run(app, host="0.0.0.0", port=30001, lifespan="on", log_config=None)
    logger.info("AutoSubRT Service stopped")
