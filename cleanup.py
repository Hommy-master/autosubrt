"""临时文件清理

正常情况下临时音频文件由各请求的 finally 删除，但进程被强杀（OOM、docker stop 宽限期
到点、重新部署）时 finally 不会执行，文件就留在磁盘上再无任何引用。这里做两件事：

1. 启动时清空 temp 目录：上一个进程的残留（年龄可能只有几分钟，按年龄阈值清不掉）；
2. 按 TEMP_RETENTION_SECONDS 周期兜底清理：防止运行期出现意料之外的残留。

被清掉的只是临时音频文件，不影响任何业务数据。
"""

import asyncio
import config
import helper
import traceback
from contextlib import suppress
from logger import logger


# 周期任务的强引用：asyncio 只持弱引用，不保存的话任务可能被 GC 掉、清理静默停止
_task: asyncio.Task = None

def _cleanup_once() -> None:
    """按保留时长清理临时目录（同步，由 to_thread 调用）"""
    if config.TEMP_RETENTION_SECONDS > 0:
        helper.cleanup_dir(config.TEMP_DIR, config.TEMP_RETENTION_SECONDS)

async def start() -> None:
    """启动清理任务：先做一次启动清理，再启动周期清理"""
    global _task

    # 启动清理：此时还没有任何请求在跑，temp 里的文件都是上一个进程的残留，直接清空
    if config.TEMP_CLEAN_ON_START:
        try:
            removed, freed = await asyncio.to_thread(helper.cleanup_dir, config.TEMP_DIR, 0)
            if removed:
                logger.info(f"Startup cleanup: removed {removed} leftover file(s), freed {freed / 1024 / 1024:.2f}MB")
        except Exception as e:
            # 清理只是顺带做的事，失败不能影响服务启动
            logger.error(f"Startup cleanup failed: {str(e)}, detail: {traceback.format_exc()}")

    if config.CLEANUP_INTERVAL_SECONDS <= 0:
        logger.warning("Periodic disk cleanup is disabled (CLEANUP_INTERVAL_SECONDS <= 0)")
        return

    _task = asyncio.create_task(_loop(), name="disk-cleanup")

async def _loop() -> None:
    """周期清理循环"""
    while True:
        # 先等待：启动清理刚刚已经跑过一次
        await asyncio.sleep(config.CLEANUP_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(_cleanup_once)
        except asyncio.CancelledError:
            # 取消要透传，否则会吞掉关闭信号
            raise
        except Exception as e:
            # 单次清理失败不能打断循环，否则后台清理就永久停止了
            logger.error(f"Periodic disk cleanup failed: {str(e)}, detail: {traceback.format_exc()}")

async def stop() -> None:
    """停止周期清理任务"""
    global _task
    if _task is None:
        return

    _task.cancel()
    with suppress(asyncio.CancelledError):
        await _task
    _task = None
