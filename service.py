import config


def gen_download_url(file_path: str) -> str:
    """
    生成下载URL，将文件路径中的/app/替换成DOWNLOAD_URL
    
    Args:
        file_path: 文件路径
    
    Returns:
        download_url: 下载URL
    """
    # 替换文件路径中的/app/为DOWNLOAD_URL
    download_url = file_path.replace("/app/", config.DOWNLOAD_URL)
    return download_url

def asr_text(audio_url: str) -> str:
    """
    语音 -> 纯文本
    
    Args:
        audio_url: 音频URL
    
    Returns:
        text: 纯文本

    Raises:
        CustomException: 自定义异常
    """

    print(f"audio_url: {audio_url}\n")

    return ""

def asr_srt(audio_url: str) -> str:
    """
    语音 -> 字幕
    
    Args:
        audio_url: 音频URL
    
    Returns:
        srt_url: 字幕URL

    Raises:
        CustomException: 自定义异常
    """
    print(f"audio_url: {audio_url}\n")

    return ""

def asr_embed(video_url: str) -> str:
    """
    视频（提取语音，识别字幕） -> 嵌入字幕
    
    Args:
        video_url: 视频URL
    
    Returns:
        embed_url: 嵌入字幕URL

    Raises:
        CustomException: 自定义异常
    """
    print(f"video_url: {video_url}\n")

    return ""
