from fastapi import FastAPI
from contextlib import asynccontextmanager
import router
import service
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
app.include_router(router.router, prefix="/openapi", tags=["autosubrt"])

# 4. 打印所有路由
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
    
    # 运行FastAPI应用 - 移除workers参数以便直接通过脚本运行
    # 在生产环境中，建议使用命令：uvicorn main:app --host 0.0.0.0 --port 60000 --workers 4
    logger.info("Start AutoSubRT Service ...")
    uvicorn.run(app, host="0.0.0.0", port=60000, lifespan="on")
    logger.info("AutoSubRT Service stopped")
