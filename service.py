from funasr import AutoModel
from logger import logger
from exceptions import CustomException, CustomError
import traceback
import helper
import pysrt
import config
import os


# 加载模型（只加载一次）
model = None

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
    try:
        # 1. 下载音频文件
        audio_file = helper.download(audio_url, config.TEMP_DIR)

        # 2. 执行音频转文本
        result = model.generate(input=audio_file)
        
        # 3. 提取文本结果
        if isinstance(result, list) and len(result) > 0 and "text" in result[0]:
            text = result[0]["text"]
            logger.info(f"ASR text success, text length: {len(text)}")
            return text
        else:
            logger.warning("Empty ASR result")
            return ""
            
    except CustomException:
        # 自定义异常直接抛出
        raise
    except Exception as e:
        logger.error(f"ASR process failed: {str(e)}, detail: {traceback.format_exc()}")
        raise CustomException(err=CustomError.RECOGNIZE_AUDIO_FAILED)

def asr_srt(audio_url: str) -> str:
    """
    语音 -> 字幕（提取视频文案）
    
    Args:
        audio_url: 音频URL
    
    Returns:
        srt_url: 字幕URL

    Raises:
        CustomException: 自定义异常
    """
    # 1. 下载音频文件
    audio_file = helper.download(audio_url, config.TEMP_DIR)

    # 2. 生成srt文件名
    srt_file = os.path.join(config.SRT_OUTPUT_DIR, helper.gen_unique_id() + ".srt")

    # 3. 执行音频转srt格式文件
    process_audio_to_srt(audio_file, srt_file)
    logger.info(f"Process audio to srt success, srt_file: {srt_file}")

    # 4. 生成下载路径
    return gen_download_url(srt_file)

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

def load_model():
    """加载语音识别模型"""
    global model
    if model is None:
        try:
            logger.info("load paraformer-zh model...")
            model = AutoModel(model="paraformer-zh", disable_update=True)
            logger.info("paraformer-zh model load success")
        except Exception as e:
            logger.error(f"paraformer-zh model load failed: {str(e)}")
            logger.error(traceback.format_exc())
            raise

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

def ms_to_subrip_time(ms):
    """将毫秒转换为pysrt.SubRipTime对象"""
    total_seconds = ms / 1000
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int((total_seconds - int(total_seconds)) * 1000)
    return pysrt.SubRipTime(hours=hours, minutes=minutes, seconds=seconds, milliseconds=milliseconds)

def filter_valid_timestamps(timestamps):
    """过滤有效的时间戳（至少包含开始和结束时间）"""
    return [ts for ts in timestamps if len(ts) >= 2]

def segment_sentences_by_intervals(words, valid_timestamps, interval_threshold=250):
    """根据时间间隔分割句子"""
    sentences = []
    sentence_start_idx = 0
    
    for i in range(1, len(valid_timestamps)):
        # 计算时间间隔
        prev_end = valid_timestamps[i-1][1]
        curr_start = valid_timestamps[i][0]
        interval = curr_start - prev_end
        
        # 如果间隔超过阈值，认为是一个句子结束
        if interval > interval_threshold and i > sentence_start_idx:
            start_ms = valid_timestamps[sentence_start_idx][0]
            end_ms = valid_timestamps[i-1][1]
            sentence_text = ''.join(words[sentence_start_idx:i])
            sentences.append((start_ms, end_ms, sentence_text))
            sentence_start_idx = i
    
    return sentences, sentence_start_idx

def add_remaining_sentence(words, valid_timestamps, sentence_start_idx, sentences):
    """添加剩余的单词作为一个句子"""
    if sentence_start_idx < len(valid_timestamps):
        start_ms = valid_timestamps[sentence_start_idx][0]
        end_ms = valid_timestamps[-1][1]
        sentence_text = ''.join(words[sentence_start_idx:])
        sentences.append((start_ms, end_ms, sentence_text))

def add_fallback_sentence(words, valid_timestamps, text, sentences):
    """添加后备句子（当无法正常分割时使用）"""
    if not sentences and words and valid_timestamps:
        start_ms = valid_timestamps[0][0]
        end_ms = valid_timestamps[-1][1]
        sentence_text = ''.join(words)
        sentences.append((start_ms, end_ms, sentence_text))
    
    # 如果仍然没有句子，返回一个默认的条目
    if not sentences:
        sentences.append((0, 30000, text))  # 假设30秒的持续时间

def split_text_by_timestamp(text, timestamps):
    """根据时间戳拆分文本，创建更准确的SRT条目"""
    # 1. 过滤有效时间戳
    valid_timestamps = filter_valid_timestamps(timestamps)
    
    # 2. 分割文本为单词列表
    words = text.split()
    
    # 3. 根据时间间隔分割句子
    sentences, sentence_start_idx = segment_sentences_by_intervals(words, valid_timestamps)
    
    # 4. 添加剩余的单词作为一个句子
    add_remaining_sentence(words, valid_timestamps, sentence_start_idx, sentences)
    
    # 5. 添加后备句子（当无法正常分割时使用）
    add_fallback_sentence(words, valid_timestamps, text, sentences)
    
    return sentences

def extract_asr_result(result):
    """从ASR结果中提取文本和时间戳"""
    if isinstance(result, list) and len(result) > 0 and "text" in result[0]:
        item = result[0]
        text = item["text"]
        timestamps = item.get("timestamp", [])
        return text, timestamps
    return None, None

def create_srt_entries(text, timestamps):
    """创建SRT条目"""
    subs = pysrt.SubRipFile()
    
    # 调试用
    logger.info(f"text: {text}, len(text): {len(text)}, len(timestamps): {len(timestamps)}")
    
    # 拆分文本为句子级别的SRT条目
    sentences = split_text_by_timestamp(text, timestamps)
    
    # 创建SRT条目
    for i, (start_ms, end_ms, sentence_text) in enumerate(sentences, 1):
        start_time = ms_to_subrip_time(start_ms)
        end_time = ms_to_subrip_time(end_ms)
        subs.append(pysrt.SubRipItem(index=i, start=start_time, end=end_time, text=sentence_text))
    
    logger.info(f"Create {len(sentences)} SRT entries")
    return subs

def process_audio_to_srt(audio_path: str, srt_path: str):
    """处理音频文件并生成SRT字幕"""
    try:
        # 1. 使用模型生成识别结果
        result = model.generate(input=audio_path)
        
        # 2. 提取ASR结果
        text, timestamps = extract_asr_result(result)
        
        if text is not None:
            # 3. 创建SRT条目
            subs = create_srt_entries(text, timestamps)
            
            # 4. 保存SRT文件
            subs.save(srt_path)
            logger.info(f"SRT file saved: {srt_path}")
        else:
            logger.warning("Empty result")
            
    except Exception as e:
        logger.error(f"Handle audio file failed: {str(e)}, detail: {traceback.format_exc()}")
        raise CustomException(err=CustomError.RECOGNIZE_AUDIO_FAILED)