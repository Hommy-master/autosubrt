from fastapi import FastAPI
from contextlib import asynccontextmanager
import router
import service
import middlewares
from logger import logger


# 1. 加载模型
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---------------- 启动 ----------------
    # await create_db_pool()
    # await start_redis()
    logger.info("✅ app start")
    # 在应用启动时加载模型
    service.load_model()
    yield
    # ---------------- 关闭 ----------------
    # await close_db_pool()
    # await stop_redis()
    logger.info("❌ app shutdown")

# 2. 创建FastAPI应用
app = FastAPI(title="AutoSubRT API", description="语音转SRT字幕服务", lifespan=lifespan)

# 3. 注册路由
app.include_router(router.router, prefix="/openapi", tags=["AutoSubRT"])

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
    uvicorn.run(app, host="0.0.0.0", port=60000, lifespan="on")
    logger.info("AutoSubRT Service stopped")
