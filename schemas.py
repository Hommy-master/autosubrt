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

class AsrTextAlignRequest(BaseModel):
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
