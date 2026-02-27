from fastapi import APIRouter, Request
from logger import logger
import schemas
import service


router = APIRouter(prefix="/v1", tags=["v1"])

@router.post("/asr/text", response_model=schemas.AsrTextResponse)
def asr_text(asr: schemas.AsrTextRequest):
    """
    语音 -> 纯文本
    """
    
    # 调用service层处理业务逻辑
    text = service.asr_text(
        audio_url=asr.audio_url,
    )

    return schemas.AsrTextResponse(text=text)

@router.post("/asr/srt", response_model=schemas.AsrSrtResponse)
def asr_srt(asr: schemas.AsrSrtRequest):
    """
    语音 -> 字幕
    """

    srt_url = service.asr_srt(
        audio_url=asr.audio_url,
    )

    logger.info(f"generate srt: {srt_url}")
    return schemas.AsrSrtResponse(srt_url=srt_url)

@router.post("/asr/text/align", response_model=schemas.AsrTextAlignResponse)
def asr_text_align(request: schemas.AsrTextAlignRequest):
    """
    语音 -> 对齐字幕时间线
    根据音频对齐给定文本的时间线
    """
    
    # 调用service层处理业务逻辑
    texts, timelines = service.align_text_with_audio(
        audio_url=request.audio_url,
        text=request.text,
        max_chars_per_line=request.max_chars_per_line
    )
    
    # 转换时间线格式
    timeline_items = [schemas.TimelineItem(start=item["start"], end=item["end"]) for item in timelines]
    
    return schemas.AsrTextAlignResponse(texts=texts, timelines=timeline_items)

@router.post("/video/add_subtitles", response_model=schemas.AddSubtitlesResponse)
def add_subtitles(request: Request, params: schemas.AddSubtitlesRequest):
    """
    为视频添加字幕
    """

    # 调用service层处理业务逻辑
    video_url = service.add_subtitles(
        video_url=params.video,
        subtitle_url=params.subtitle_url,
        subtitle_config=params.subtitle_config
    )

    return schemas.AddSubtitlesResponse(video_url=video_url)

# 健康检查端点
@router.get("/health", summary="健康检查")
def health_check():
    """检查服务是否正常运行"""
    return {"code": 0, "message": "AutoSubRT Service is running"}