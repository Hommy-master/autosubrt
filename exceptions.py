from enum import Enum

# 自定义错误码
class CustomError(Enum):
    """错误码枚举类（支持中英文）"""
    
    # ===== 基础错误码 (1000-1999) =====
    SUCCESS = (0, "成功", "Success")
    PARAM_VALIDATION_FAILED = (1001, "参数校验失败", "Parameter validation failed")
    
    # ===== 业务错误码 (2000-2999) =====
    RECOGNIZE_AUDIO_FAILED = (2001, "识别音频失败", "Failed to recognize audio")
    FILE_SIZE_LIMIT_EXCEEDED = (2002, "文件大小超出限制", "File size exceeds the limit")
    DOWNLOAD_FILE_FAILED = (2003, "下载文件失败", "Download file failed")
    DOWNLOAD_FILE_TIMEOUT = (2005, "下载文件超时", "Download file timeout")

    # ===== 计费错误码 =====
    # 与 capcut-mate 保持同一组数字码（2035/2036），便于客户端用一张表识别各服务的计费错误
    INSUFFICIENT_ACCOUNT_BALANCE = (2035, "账户余额不足，当前积分需大于 1 才可继续使用服务，请完成充值后重试", "Insufficient account balance. A minimum of 1 point is required to continue using the service. Please recharge and try again.")
    INVALID_APIKEY = (2036, "无效的 apiKey，请登录官网 https://jcaigc.cn 获取", "Invalid apiKey. Please log in at https://jcaigc.cn to obtain one")

    # ===== 系统错误码 (9000-9999) =====
    # 并发数已达上限：请求没有排队，调用方稍后重试即可（不是参数或业务错误，故不在 2xxx）
    SERVER_BUSY = (9997, "服务器忙，请稍后重试", "Server is busy, please try again later")
    INTERNAL_SERVER_ERROR = (9998, "系统内部错误", "Internal server error")
    UNKNOWN_ERROR = (9999, "未知异常", "Unknown error")

    def __init__(self, code: int, cn_message: str, en_message: str):
        self.code = code
        self.cn_message = cn_message
        self.en_message = en_message

    def as_dict(self, detail: str = None, lang: str = 'zh') -> dict:
        """转换为API响应格式，支持中英文"""
        message = self.cn_message if lang == 'zh' else self.en_message
        if detail:
            message += f": {detail}"
        return {"code": self.code, "message": message}


# 自定义异常类
class CustomException(Exception):
    """自定义业务异常类"""
    def __init__(self, err: CustomError, detail: str = None):
        self.err = err
        self.detail = detail
        super().__init__(err.cn_message)
