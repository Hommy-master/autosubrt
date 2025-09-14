from fastapi import FastAPI
from contextlib import asynccontextmanager
import router
import service
import middlewares
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import status, Request
from logger import logger
from exceptions import CustomError

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

# 4. 添加中间件
app.middleware("http")(middlewares.prepare_middleware)
# 注册统一响应处理中间件（注意顺序，应该在其他中间件之后注册）
app.middleware("http")(middlewares.response_middleware)

# 5. 异常处理：参数校验错误
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """自定义参数校验错误处理器"""
    # 1. 拼接完整错误信息
    error_messages = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        error_type = error["type"]
        error_msg = error["msg"]
        # 组合字段+错误类型+详情信息
        error_messages.append(f"{field} ({error_type}): {error_msg}")
    
    # 2. 构建统一响应结构
    full_message = "; ".join(error_messages)  # 用分号分隔多个错误
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=CustomError.PARAM_VALIDATION_FAILED.as_dict(full_message)
    )

# 6. 打印所有路由
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
