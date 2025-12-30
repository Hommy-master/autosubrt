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
punc_model = None

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
    audio_file = None
    try:
        # 1. 下载音频文件
        audio_file = helper.download(audio_url, config.TEMP_DIR)

        # 2. 执行音频转文本
        result = model.generate(input=audio_file)
        
        # 3. 提取文本结果
        if isinstance(result, list) and len(result) > 0 and "text" in result[0]:
            text = result[0]["text"]
            logger.info(f"ASR text success, text length: {len(text)}")
            
            # 4. 添加标点符号
            global punc_model
            if punc_model is not None:
                try:
                    punc_result = punc_model.generate(input=text)
                    if isinstance(punc_result, list) and len(punc_result) > 0 and "text" in punc_result[0]:
                        punctuated_text = punc_result[0]["text"]
                        logger.info(f"Punctuation success, text length: {len(punctuated_text)}")
                        return punctuated_text
                except Exception as e:
                    logger.error(f"Punctuation process failed: {str(e)}, detail: {traceback.format_exc()}")
            
            # 如果标点符号处理失败或未启用，返回原始文本
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
    finally:
        # 清理临时音频文件
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
                logger.info(f"Temporary audio file cleaned up: {audio_file}")
            except Exception as e:
                logger.error(f"Failed to remove temporary audio file {audio_file}: {str(e)}")

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
    audio_file = None
    try:
        # 1. 下载音频文件
        audio_file = helper.download(audio_url, config.TEMP_DIR)

        # 2. 生成srt文件名
        srt_file = os.path.join(config.SRT_OUTPUT_DIR, helper.gen_unique_id() + ".srt")

        # 3. 执行音频转srt格式文件
        process_audio_to_srt(audio_file, srt_file)
        logger.info(f"Process audio to srt success, srt_file: {srt_file}")

        # 4. 生成下载路径
        return gen_download_url(srt_file)
    finally:
        # 清理临时音频文件
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
                logger.info(f"Temporary audio file cleaned up: {audio_file}")
            except Exception as e:
                logger.error(f"Failed to remove temporary audio file {audio_file}: {str(e)}")

# 使用FFmpeg命令添加字幕：ffmpeg -v error -i input.mp4 -vf "subtitles=subtitle.srt:force_style='Outline=2,OutlineColour=&H000000,PrimaryColour=&HFFFFFF,FontName=SJbangshu,FontSize=24'" -c:a copy output.mp4
def add_subtitles(video_url: str, subtitle_url: str, subtitle_config) -> str:
    """
    为视频添加字幕
    
    Args:
        video_url: 视频URL
        subtitle_url: 字幕文件URL
        subtitle_config: 字幕配置参数 (SubtitleConfig 对象或字典)
        
    Returns:
        video_url: 添加字幕后的视频URL

    Raises:
        CustomException: 自定义异常
    """
    video_file = None
    subtitle_file = None
    try:
        # 1. 下载视频文件
        video_file = helper.download(video_url, config.TEMP_DIR)
        
        # 2. 下载字幕文件
        subtitle_file = helper.download(subtitle_url, config.TEMP_DIR)
        
        # 3. 生成输出视频文件路径
        output_video_file = os.path.join(config.VIDEO_OUTPUT_DIR, helper.gen_unique_id() + ".mp4")
        
        # 4. 使用ffmpeg将字幕嵌入到视频中
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_video_file), exist_ok=True)
        
        # 解析字幕配置参数
        # 检查subtitle_config是字典还是对象
        if hasattr(subtitle_config, 'font_color'):
            # Pydantic模型对象
            font_color = subtitle_config.font_color
            font_size = subtitle_config.font_size
        else:
            # 字典
            font_color = subtitle_config.get("font_color", "#FF0000FF")
            font_size = subtitle_config.get("font_size", 40)
        
        # 构建字幕样式参数
        # 将颜色格式从 #AARRGGBB 转换为 &HAABBGGRR
        if font_color.startswith('#') and len(font_color) == 9:
            # 转换颜色格式: #AARRGGBB -> &HBBGGRR
            color_hex = font_color[3:9]  # 取RGB部分
            color_value = "&H" + color_hex[4:6] + color_hex[2:4] + color_hex[0:2]  # 转换为BGR
        else:
            color_value = "&HFFFFFF"  # 默认白色
        
        # 构建字幕样式
        subtitle_style = f"Outline=2,OutlineColour=&H000000,PrimaryColour={color_value},FontName=SJbangshu,FontSize={font_size}"
        
        # 构建并执行FFmpeg命令
        import subprocess
        import shlex
        
        # 处理Windows路径问题，将反斜杠转换为正斜杠
        subtitle_file_fixed = subtitle_file.replace('\\', '/')
        video_file_fixed = video_file.replace('\\', '/')
        
        ffmpeg_cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-i", video_file_fixed,
            "-vf", f"subtitles='{subtitle_file_fixed}':force_style='{subtitle_style}'",
            "-c:a", "copy",
            output_video_file
        ]
        
        logger.info(f"Executing FFmpeg command: {' '.join(shlex.quote(arg) for arg in ffmpeg_cmd)}")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"FFmpeg process failed: {result.stderr}")
            raise CustomException(err=CustomError.PROCESS_VIDEO_FAILED)
        
        logger.info(f"Embed subtitles success, output_video_file: {output_video_file}")
        
        # 5. 生成下载路径
        return gen_download_url(output_video_file)
        
    except CustomException:
        # 自定义异常直接抛出
        raise
    except Exception as e:
        logger.error(f"Process video embed subtitles failed: {str(e)}, detail: {traceback.format_exc()}")
        raise CustomException(err=CustomError.PROCESS_VIDEO_FAILED)
    finally:
        # 清理临时视频和字幕文件
        for temp_file in [video_file, subtitle_file]:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.info(f"Temporary file cleaned up: {temp_file}")
                except Exception as e:
                    logger.error(f"Failed to remove temporary file {temp_file}: {str(e)}")

def load_model():
    """加载语音识别模型"""
    global model, punc_model
    if model is None:
        try:
            logger.info("load paraformer-zh model...")
            model = AutoModel(model="paraformer-zh", disable_update=True)
            logger.info("paraformer-zh model load success")
        except Exception as e:
            logger.error(f"paraformer-zh model load failed: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    # 加载标点符号模型
    if punc_model is None:
        try:
            logger.info("load ct-punc model...")
            from funasr import AutoModel as AutoPuncModel
            punc_model = AutoPuncModel(model="ct-punc", disable_update=True)
            logger.info("ct-punc model load success")
        except Exception as e:
            logger.error(f"ct-punc model load failed: {str(e)}")
            logger.error(traceback.format_exc())
            # 标点符号模型加载失败不抛出异常，只记录日志

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

