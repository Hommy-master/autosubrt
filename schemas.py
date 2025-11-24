from pydantic import BaseModel, Field, HttpUrl
from typing import Optional


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

class FontPosConfig(BaseModel):
    """字体位置配置"""
    height: str = Field(default="30%", description="高度百分比")
    pos_x: str = Field(default="5%", description="X轴位置百分比")
    pos_y: str = Field(default="70%", description="Y轴位置百分比")
    width: str = Field(default="90%", description="宽度百分比")

class SubtitleConfig(BaseModel):
    """字幕配置"""
    font_color: str = Field(default="#FF0000FF", description="字体颜色")
    font_pos_config: FontPosConfig = Field(default_factory=FontPosConfig, description="字体位置配置")
    font_size: int = Field(default=40, description="字体大小")

class AddSubtitlesRequest(BaseModel):
    """添加字幕请求参数"""
    subtitle_config: SubtitleConfig = Field(default_factory=SubtitleConfig, description="字幕配置")
    subtitle_url: HttpUrl = Field(..., description="字幕文件URL")
    video: HttpUrl = Field(..., description="视频文件URL")

class AddSubtitlesResponse(BaseModel):
    """添加字幕响应参数"""
    video_url: str = Field(default="", description="视频文件URL")