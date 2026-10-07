"""ASR 接口的并发限流

单个请求的峰值内存与音频时长成正比：解码后的 float32 音频、VAD 的两次整段拷贝、
每 30s 一片的梅尔特征，再加上推理工作区，1 小时音频可以到 1GB 量级；而 FastAPI 的
同步端点默认最多 40 个线程并发，不限流时几个长音频同时进来就会顶到容器内存上限被
OOM 杀掉（模型本身还常驻约 1.5GB）。

因此所有 ASR 接口共用一份名额，超出 MAX_CONCURRENCY 的请求直接返回「服务器忙」，
不在此排队：排队只会让调用方等到超时，不如立刻给出明确结果，由它自行重试或降级。
"""

import threading
from contextlib import contextmanager

import config
from exceptions import CustomError, CustomException


# 进程内的并发名额，所有 ASR 接口共用（模型只有一份，内存开销也是全局的）。
# MAX_CONCURRENCY <= 0 时为 None，表示不限流
_semaphore = (
    threading.Semaphore(config.MAX_CONCURRENCY) if config.MAX_CONCURRENCY > 0 else None
)

@contextmanager
def limit():
    """占用一个并发名额，占不到时抛「服务器忙」，退出时释放

    Yields:
        None

    Raises:
        CustomException: 并发数已达 MAX_CONCURRENCY
    """
    if _semaphore is None:
        yield
        return

    # 非阻塞获取：拿不到名额就走错误分支，不在这里排队等待
    if not _semaphore.acquire(blocking=False):
        raise CustomException(err=CustomError.SERVER_BUSY)

    try:
        yield
    finally:
        # 无论业务成功还是抛异常都要归还名额（异常由 ResponseMiddleware 统一转成响应体）
        _semaphore.release()
