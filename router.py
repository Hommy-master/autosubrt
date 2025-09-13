from fastapi import APIRouter, Request
import schemas
import service


router = APIRouter(prefix="/v1", tags=["v1"])

@router.post("/asr/text", response_model=schemas.AsrTextResponse)
def asr_text(request: Request, asr: schemas.AsrTextRequest):
    """
    语音 -> 纯文本
    """
    
    # 调用service层处理业务逻辑
    text = service.asr_text(
        audio_url=asr.audio_url,
    )

    return schemas.AsrTextResponse(text=text)

@router.post("/asr/srt", response_model=schemas.AsrSrtResponse)
def asr_srt(request: Request, asr: schemas.AsrSrtRequest):
    """
    语音 -> 字幕
    """

    srt_url = service.asr_srt(
        audio_url=asr.audio_url,
    )

    return schemas.AsrSrtResponse(srt_url=srt_url)

@router.post("/asr/embed", response_model=schemas.AsrEmbedResponse)
def asr_embed(request: Request, asr: schemas.AsrEmbedRequest):
    """
    视频（提取语音，识别字幕） -> 嵌入字幕
    """

    # 调用service层处理业务逻辑
    embed_url = service.asr_embed(
        video_url=asr.video_url,
    )

    return schemas.AsrEmbedResponse(video_url=embed_url)

# 健康检查端点
@router.get("/health", summary="健康检查")
def health_check():
    """检查服务是否正常运行"""
    return {"code": 0, "message": "AutoSubRT Service is running"}