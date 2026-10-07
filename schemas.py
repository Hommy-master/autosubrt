from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional
import uuid


def validate_api_key_uuid(value: Optional[str]) -> Optional[str]:
    """
    校验 apiKey 格式：空值归一为 None，非 UUID 时抛出 ValueError。

    Args:
        value: 请求传入的 apiKey

    Returns:
        Optional[str]: 归一化后的 apiKey

    Raises:
        ValueError: apiKey 不是合法 UUID
    """
    if value is None or value == "":
        return None
    try:
        uuid.UUID(value)
    except ValueError:
        raise ValueError(
            "API密钥格式不正确，必须是合法的UUID；请登录官网 https://jcaigc.cn 获取 apiKey"
        )
    return value


class ApiKeyMixin(BaseModel):
    """带 apiKey 校验的请求参数基类

    格式非法时 pydantic 抛 ValueError，FastAPI 返回 422，再由 ResponseMiddleware
    统一转成 1001 参数校验失败。该校验不随 ENABLE_APIKEY 开关变化。
    """
    apiKey: Optional[str] = Field(
        default=None,
        description="apiKey 必须是合法的 UUID 格式；可登录官网 https://jcaigc.cn 获取",
    )

    @field_validator('apiKey')
    @classmethod
    def validate_api_key(cls, v):
        return validate_api_key_uuid(v)


class AsrTextRequest(ApiKeyMixin):
    """语音 -> 纯文本请求参数"""
    audio_url: str = Field(default="", description="音频文件URL")

class AsrTextResponse(BaseModel):
    """语音 -> 纯文本响应参数"""
    text: str = Field(default="", description="纯文本")

class AsrSrtRequest(ApiKeyMixin):
    """语音 -> 字幕请求参数"""
    audio_url: HttpUrl = Field(..., description="音频文件URL")

class AsrTextAlignRequest(ApiKeyMixin):
    """语音 -> 对齐字幕时间线请求参数"""
    audio_url: str = Field(..., description="音频文件URL")
    text: str = Field(..., description="音频对应字幕文本")
    max_chars_per_line: Optional[int] = Field(default=15, description="每行最大字数")

class TimelineItem(BaseModel):
    """时间线项"""
    start: int = Field(..., description="开始时间 (微秒)")
    end: int = Field(..., description="结束时间 (微秒)")

class CharTimelineItem(BaseModel):
    """字符级时间线项"""
    char: str = Field(..., description="字符")
    start: int = Field(..., description="开始时间 (微秒)")
    end: int = Field(..., description="结束时间 (微秒)")

class WordTimelineItem(BaseModel):
    """字级时间线项"""
    start: int = Field(..., description="开始时间 (微秒)")
    end: int = Field(..., description="结束时间 (微秒)")

class AsrTextAlignResponse(BaseModel):
    """语音 -> 对齐字幕时间线响应参数"""
    texts: list[str] = Field(..., description="对齐后的文本列表")
    timelines: list[TimelineItem] = Field(..., description="对应的时间线列表")
    words: list[str] = Field(default=[], description="字数组（按顺序排列的每个字）")
    words_timelines: list[WordTimelineItem] = Field(default=[], description="每个字对应的时间线（与 words 数组一一对应）")

class AsrWordItem(BaseModel):
    """字级时间线项"""
    text: str = Field(..., description="字")
    start_time: int = Field(..., description="开始时间 (毫秒)")
    end_time: int = Field(..., description="结束时间 (毫秒)")

class AsrUtteranceItem(BaseModel):
    """一句话/一段话"""
    text: str = Field(default="", description="一句话或一段话的文本")
    words: list[AsrWordItem] = Field(default=[], description="该句话中每个字的时间线")

class AsrRequest(ApiKeyMixin):
    """语音 -> 完整文案及逐字时间线请求参数"""
    audio_url: str = Field(..., description="音频文件URL")

class AsrResponse(BaseModel):
    """语音 -> 完整文案及逐字时间线响应参数"""
    text: str = Field(default="", description="完整文案")
    utterances: list[AsrUtteranceItem] = Field(default=[], description="分句结果及每个字的时间线")
