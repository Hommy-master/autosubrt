from pydantic import BaseModel, Field, HttpUrl


class AsrTextRequest(BaseModel):
    """语音 -> 纯文本请求参数"""
    audio_url: str = Field(default="", description="音频文件URL")

class AsrTextResponse(BaseModel):
    """语音 -> 纯文本响应参数"""
    text: str = Field(default="", description="纯文本")

class AsrSrtRequest(BaseModel):
    """语音 -> 字幕请求参数"""
    audio_url: HttpUrl = Field(..., description="音频文件URL")

class AsrSrtResponse(BaseModel):
    """语音 -> 字幕响应参数"""
    srt_url: str = Field(default="", description="字幕文件URL")

class AsrEmbedRequest(BaseModel):
    """视频（提取语音，识别字幕） -> 嵌入字幕请求参数"""
    video_url: str = Field(default="", description="视频文件URL")

class AsrEmbedResponse(BaseModel):
    """视频（提取语音，识别字幕） -> 嵌入字幕响应参数"""
    video_url: str = Field(default="", description="视频文件URL")
