from fastapi import APIRouter
from fastapi.responses import Response
from logger import logger
import concurrency
import schemas
import service


# SRT 文件下载响应：调用方直接拿到字幕文件本体，服务端不落盘
SRT_MEDIA_TYPE = "application/x-subrip"
SRT_DOWNLOAD_FILENAME = "subtitle.srt"


router = APIRouter(prefix="/v1", tags=["v1"])

@router.post("/asr", response_model=schemas.AsrResponse)
def asr_utterances(request: schemas.AsrRequest):
    """
    语音 -> 完整文案 + 分句及逐字时间线
    """

    # 调用service层处理业务逻辑（并发受限，超出上限直接返回「服务器忙」）
    with concurrency.limit():
        text, utterances = service.asr_utterances(audio_url=request.audio_url, api_key=request.apiKey)

    return schemas.AsrResponse(
        text=text,
        utterances=[schemas.AsrUtteranceItem(**item) for item in utterances],
    )

@router.post("/asr/text", response_model=schemas.AsrTextResponse)
def asr_text(asr: schemas.AsrTextRequest):
    """
    语音 -> 纯文本
    """
    
    # 调用service层处理业务逻辑（并发受限，超出上限直接返回「服务器忙」）
    with concurrency.limit():
        text = service.asr_text(
            audio_url=asr.audio_url,
            api_key=asr.apiKey,
        )

    return schemas.AsrTextResponse(text=text)

@router.post("/asr/srt")
def asr_srt(asr: schemas.AsrSrtRequest):
    """
    语音 -> 字幕

    直接返回 SRT 文件本体（Content-Disposition: attachment），服务端不保存文件；
    失败时仍由 ResponseMiddleware 返回统一的 JSON 错误体，调用方按 Content-Type 区分。
    """

    # 并发受限，超出上限直接返回「服务器忙」
    with concurrency.limit():
        srt_text = service.asr_srt(
            audio_url=asr.audio_url,
            api_key=asr.apiKey,
        )

    logger.info(f"generate srt success, length: {len(srt_text)}")
    return Response(
        content=srt_text.encode("utf-8"),
        media_type=f"{SRT_MEDIA_TYPE}; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{SRT_DOWNLOAD_FILENAME}"',
        },
    )

@router.post("/asr/text/align", response_model=schemas.AsrTextAlignResponse)
def asr_text_align(request: schemas.AsrTextAlignRequest):
    """
    语音 -> 对齐字幕时间线
    根据音频对齐给定文本的时间线
    """
    
    # 调用 service 层处理业务逻辑（并发受限，超出上限直接返回「服务器忙」）
    with concurrency.limit():
        texts, timelines, char_timelines = service.align_text_with_audio(
            audio_url=request.audio_url,
            text=request.text,
            max_chars_per_line=request.max_chars_per_line,
            api_key=request.apiKey
        )
    
    # 转换句子级时间线格式（确保为整数）
    timeline_items = [
        schemas.TimelineItem(start=int(round(item["start"])), end=int(round(item["end"]))) 
        for item in timelines
    ]
    
    # 拆分字符级时间线为 words 和 words_timelines
    words = [item["char"] for item in char_timelines]
    words_timeline_items = [
        schemas.WordTimelineItem(start=int(round(item["start"])), end=int(round(item["end"]))) 
        for item in char_timelines
    ]
    
    # 转换为字典格式供 calibrate_subtitles 使用
    words_timeline_dicts = [{"start": wt.start, "end": wt.end} for wt in words_timeline_items]
    timeline_items_dicts = [{"start": ti.start, "end": ti.end} for ti in timeline_items]
    
    # 校准字幕时间线
    calibrated_timelines = service.calibrate_subtitles(
        texts, 
        timeline_items_dicts, 
        words, 
        words_timeline_dicts
    )
    
    # 将校准后的结果转换回 TimelineItem
    calibrated_timeline_items = [
        schemas.TimelineItem(start=t["start"], end=t["end"]) 
        for t in calibrated_timelines
    ]
    
    return schemas.AsrTextAlignResponse(
        texts=texts, 
        timelines=calibrated_timeline_items, 
        words=words, 
        words_timelines=words_timeline_items
    )

# 健康检查端点
@router.get("/health", summary="健康检查")
def health_check():
    """检查服务是否正常运行"""
    return {"code": 0, "message": "AutoSubRT Service is running"}