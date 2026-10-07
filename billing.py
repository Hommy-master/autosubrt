"""
计费编排：调用前的 apiKey 校验 + 余额门槛，识别成功后的按时长扣费

与兄弟服务 capcut-mate 的积分体系保持一致：
    前置校验 == src/service/gen_video.py（余额需大于 1）
    尽力扣费 == src/service/upload_file.py（扣费失败只记日志，不影响已成功的请求）
"""

import config
import points
from exceptions import CustomError, CustomException
from logger import logger

# 调用前要求的余额门槛：账户积分需严格大于该值才可继续使用服务
MIN_POINTS = 1

# 写入积分流水 desc 字段的场景描述
SCENE_ASR = "语音识别"


def check_api_key(api_key: str = None) -> None:
    """调用前的 apiKey 与余额校验

    必须在下载音频之前调用，避免为不合格的调用方白白消耗算力。

    Args:
        api_key: 请求传入的 apiKey

    Raises:
        CustomException: 未传 apiKey（2036）或余额不足（2035）
    """
    # 未启用计费时不做任何校验
    if not config.ENABLE_APIKEY:
        return

    if not api_key:  # 未传或空字符串
        raise CustomException(CustomError.INVALID_APIKEY)

    # 用模块属性访问而非 from...import：便于测试打桩，也便于运行时改写 points.POINTS_API_BASE_URL
    user_points = points.get_user_points(api_key)

    # 与参考实现一致：积分需大于 1 才可继续使用服务
    if user_points <= MIN_POINTS:
        logger.error(
            f"Insufficient account balance: {user_points} for API key: {api_key[:8]}***"
        )
        raise CustomException(CustomError.INSUFFICIENT_ACCOUNT_BALANCE)


def charge(api_key: str, duration: float) -> bool:
    """按音频时长扣费（必需执行但不关心结果）

    本函数保证**永不抛异常**：扣费发生在业务已经成功之后，扣费失败只记日志，
    不能反过来把一次成功的识别变成失败响应。

    Args:
        api_key: 请求传入的 apiKey
        duration: 音频时长（秒）

    Returns:
        bool: 是否实际扣费成功
    """
    try:
        # 未启用计费或没有 apiKey 属预期跳过，不打日志避免刷屏
        if not config.ENABLE_APIKEY or not api_key:
            return False

        # 时长拿不到时无法计费，与参考实现一样只告警不报错
        if not duration or duration <= 0:
            logger.warning(f"Could not determine audio duration for charging: {duration}")
            return False

        cost = round(duration * config.POINTS_PER_SECOND, 6)

        # 金额小到四舍五入后为 0 时直接跳过，避免无意义的扣费请求
        if cost <= 0:
            logger.info(f"Skip charging, cost rounds to zero, duration: {duration:.2f}s")
            return False

        # 费用保留 6 位小数：本服务单价低，保留 2 位会把短音频全部显示成 0.00
        charged = points.deduct_user_points(
            api_key=api_key,
            points=cost,
            desc=f"{SCENE_ASR}，时长{duration:.2f}秒，费用{cost:.6f}积分",
        )

        if charged:
            logger.info(
                f"Successfully charged {cost:.6f} points for audio duration "
                f"{duration:.2f}s, API key: {api_key[:8]}***"
            )
        else:
            logger.warning(
                f"Failed to charge {cost:.6f} points for audio duration "
                f"{duration:.2f}s, API key: {api_key[:8]}***"
            )
        return charged

    except Exception as e:
        # deduct_user_points 本身不抛异常，这里的兜底是为了让「charge 永不抛异常」这一
        # 不变量在本模块内自证，调用方无需再包 try
        logger.error(f"Error calculating or charging for audio duration: {e}")
        return False
