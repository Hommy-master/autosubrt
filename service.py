from funasr import AutoModel
from logger import logger
from exceptions import CustomException, CustomError
import traceback
import helper
import pysrt
import config
import os
import re


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

def split_text_by_punctuation_without_symbols(text: str) -> list[str]:
    """根据标点符号分割文本为句子，但不在结果中包含标点符号
    
    Args:
        text: 输入文本
        
    Returns:
        分割后的句子列表（不含标点符号）
    """
    # 使用正则表达式按标点符号分割，但不保留标点符号在结果中
    # 包含中文和英文的常见标点符号：！，；。？\n\r
    sentences = re.split(r'[。！？，；.!?,;:\n\r]', text)
    
    # 过滤掉空字符串和只包含空白的字符串
    result = [s.strip() for s in sentences if s.strip()]
    
    return result

def align_text_with_audio(audio_url: str, text: str, max_chars_per_line: int = 15) -> tuple[list[str], list[dict], list[dict]]:
    """
    根据音频对齐文本时间线
    
    Args:
        audio_url: 音频 URL
        text: 需要对齐的文本
        max_chars_per_line: 每行最大字数
    
    Returns:
        tuple: (texts 列表 - 用户文本，timelines 列表 - 用户文本时间线，words 列表 - ASR 字符级时间线)
    """
    audio_file = None
    try:
        # 1. 下载音频并获取 ASR 结果
        asr_text, timestamps = _get_asr_result(audio_url, audio_file)
        
        if not asr_text or not timestamps:
            return [text], [{"start": 0, "end": 30000000}], []
        
        # 2. 预处理用户文本
        user_sentences = split_text_by_punctuation_without_symbols(text)
        
        # 3. 生成 ASR 字符级时间线（基于 ASR 识别的原始文本）
        words = _generate_asr_words(asr_text, timestamps)
        
        # 4. 为用户文本生成时间线
        final_texts, timelines = _align_user_text(user_sentences, timestamps, max_chars_per_line)
        
        return final_texts, timelines, words
        
    except CustomException:
        raise
    except Exception as e:
        logger.error(f"Text alignment failed: {str(e)}, detail: {traceback.format_exc()}")
        raise CustomException(err=CustomError.RECOGNIZE_AUDIO_FAILED)
    finally:
        _cleanup_audio_file(audio_file)

def _get_asr_result(audio_url: str, audio_file: str) -> tuple[str, list[list]]:
    """下载音频并获取 ASR 识别结果"""
    audio_file = helper.download(audio_url, config.TEMP_DIR)
    result = model.generate(input=audio_file)
    
    asr_text, timestamps = extract_asr_result(result)
    logger.info(f"ASR recognized text length: {len(asr_text)}, timestamps count: {len(timestamps)}")
    
    return asr_text, timestamps

def _generate_asr_words(asr_text: str, timestamps: list[list]) -> list[dict]:
    """
    基于 ASR 识别的文本和时间戳生成字符级时间线
    
    Args:
        asr_text: ASR 识别的文本
        timestamps: ASR 返回的时间戳列表
    
    Returns:
        list[dict]: 每个字符的时间线，包含 char, start, end
    """
    valid_timestamps = filter_valid_timestamps(timestamps)
    if not asr_text or not valid_timestamps:
        return []
    
    # 构建 ASR 词汇时间轴
    asr_words = _build_asr_word_timeline(valid_timestamps)
    total_text_length = len(asr_text)
    num_asr_words = len(asr_words)
    
    char_timelines = []
    
    for char_idx in range(total_text_length):
        # 计算归一化位置
        if total_text_length > 1:
            char_norm = float(char_idx) / float(total_text_length - 1)
        else:
            char_norm = 0.5
        
        char_float_idx = char_norm * float(num_asr_words - 1)
        
        # 获取开始时间
        char_start = _interpolate_time(char_float_idx, asr_words, num_asr_words)
        
        # 获取结束时间
        if char_idx < total_text_length - 1:
            # 不是最后一个字符：使用下一个字符的开始时间
            next_char_norm = float(char_idx + 1) / float(total_text_length - 1)
            next_char_float_idx = next_char_norm * float(num_asr_words - 1)
            char_end = _interpolate_time(next_char_float_idx, asr_words, num_asr_words)
        else:
            # 最后一个字符：使用 ASR 的总结束时间
            char_end = asr_words[-1]['end'] if asr_words else char_start + 1000
        
        char_timelines.append({
            'char': asr_text[char_idx],  # ✅ 使用 ASR 文本
            'start': char_start,
            'end': char_end
        })
    
    # 后处理：确保时间线有效
    _ensure_valid_char_timelines(char_timelines)
    
    return char_timelines

def _align_user_text(
    user_sentences: list[str], 
    timestamps: list[list],
    max_chars_per_line: int
) -> tuple[list[str], list[dict]]:
    """
    为用户输入的文本生成时间线
    
    Args:
        user_sentences: 用户文本分割后的句子列表
        timestamps: ASR时间戳
        max_chars_per_line: 每行最大字数
    
    Returns:
        tuple: (texts 列表，timelines 列表)
    """
    valid_timestamps = filter_valid_timestamps(timestamps)
    
    # 生成句子级时间线
    sentence_timelines = _generate_sentence_timelines(user_sentences, timestamps)
    
    # 分割长句子并优化
    final_texts, final_timelines = _split_and_optimize(
        sentence_timelines, max_chars_per_line
    )
    
    # 计算总时长范围
    if valid_timestamps and final_timelines:
        min_time = valid_timestamps[0][0] * 1000
        max_time = valid_timestamps[-1][1] * 1000
        
        # 后处理
        _global_optimize_timelines(final_timelines, min_time, max_time)
    
    _convert_to_microseconds(final_timelines)
    
    return final_texts, final_timelines

def _generate_sentence_timelines(user_sentences: list[str], timestamps: list[list]) -> list[dict]:
    """生成句子级时间线"""
    valid_timestamps = filter_valid_timestamps(timestamps)
    if not user_sentences or not valid_timestamps:
        return []
    
    asr_words = _build_asr_word_timeline(valid_timestamps)
    full_user_text = ''.join(user_sentences)
    total_text_length = len(full_user_text)
    num_asr_words = len(asr_words)
    
    sentence_timelines = []
    for sentence_idx, sentence in enumerate(user_sentences):
        timeline = _calculate_sentence_timeline(
            sentence_idx, sentence, user_sentences, 
            full_user_text, total_text_length, asr_words, num_asr_words
        )
        sentence_timelines.append(timeline)
    
    return sentence_timelines

def _build_asr_word_timeline(valid_timestamps: list[list]) -> list[dict]:
    """构建 ASR 词汇时间轴（毫秒转微秒）"""
    asr_words = []
    for ts in valid_timestamps:
        asr_words.append({
            'start': float(ts[0] * 1000),
            'end': float(ts[1] * 1000)
        })
    return asr_words

def _calculate_sentence_timeline(sentence_idx, sentence, user_sentences, full_text, total_len, asr_words, num_words):
    """计算单个句子的时间线"""
    start_char_idx = sum(len(s) for s in user_sentences[:sentence_idx])
    end_char_idx = start_char_idx + len(sentence) - 1
    
    start_norm = float(start_char_idx) / float(max(1, total_len - 1))
    end_norm = float(end_char_idx) / float(max(1, total_len - 1))
    
    start_time = _interpolate_time(start_norm * float(num_words - 1), asr_words, num_words)
    end_time = _interpolate_time(end_norm * float(num_words - 1), asr_words, num_words)
    
    return {
        'text': sentence,
        'start': start_time,
        'end': end_time,
        'length': len(sentence)
    }

def _interpolate_time(float_idx: float, asr_words: list[dict], num_words: int) -> float:
    """使用线性插值获取精确时间"""
    if not asr_words or num_words == 0:
        return 0
    
    # 确保索引在有效范围内
    float_idx = max(0.0, min(float_idx, float(num_words - 1)))
    
    if num_words > 1:
        floor = int(float_idx)
        frac = float_idx - floor
        
        # 确保不越界
        if floor >= num_words - 1:
            floor = num_words - 2
            frac = 1.0
        
        if floor < num_words - 1 and floor >= 0:
            return (asr_words[floor]['start'] * (1 - frac) + 
                    asr_words[floor + 1]['start'] * frac)
        else:
            return asr_words[max(0, num_words - 1)]['start']
    else:
        return asr_words[0]['start']

def _split_and_optimize(sentence_timelines: list[dict], max_chars_per_line: int):
    """分割长句子并优化时间线"""
    final_texts = []
    final_timelines = []
    
    for sent_info in sentence_timelines:
        if len(sent_info['text']) <= max_chars_per_line:
            final_texts.append(sent_info['text'])
            final_timelines.append({
                'start': sent_info['start'],
                'end': sent_info['end']
            })
        else:
            chunks = _split_long_sentence(sent_info, max_chars)
            final_texts.extend(chunks['texts'])
            final_timelines.extend(chunks['timelines'])
    
    return final_texts, final_timelines

def _split_long_sentence(sent_info: dict, max_chars: int) -> dict:
    """分割长句子"""
    text = sent_info['text']
    start = sent_info['start']
    end = sent_info['end']
    length = len(text)
    
    num_chunks = (length + max_chars - 1) // max_chars
    texts = []
    timelines = []
    
    for i in range(num_chunks):
        chunk_start = i * max_chars
        chunk_end = min((i + 1) * max_chars, length)
        chunk_text = text[chunk_start:chunk_end]
        
        if chunk_text.strip():
            chunk_start_time, chunk_end_time = _calculate_chunk_timeline(
                i, num_chunks, chunk_start, chunk_end, length, start, end
            )
            
            texts.append(chunk_text)
            timelines.append({'start': chunk_start_time, 'end': chunk_end_time})
    
    return {'texts': texts, 'timelines': timelines}

def _calculate_chunk_timeline(chunk_idx, num_chunks, chunk_start, chunk_end, length, start, end):
    """计算单个片段的时间线"""
    if length > 1:
        chunk_rel_start = float(chunk_start) / float(length - 1)
        chunk_rel_end = float(chunk_end - 1) / float(length - 1)
    else:
        chunk_rel_start = 0.5
        chunk_rel_end = 0.5
    
    chunk_start_time = start + chunk_rel_start * (end - start)
    chunk_end_time = start + chunk_rel_end * (end - start)
    
    return chunk_start_time, chunk_end_time

def _ensure_valid_char_timelines(char_timelines: list[dict]):
    """确保字符级时间线有效（start < end，且差值 >= 1ms）"""
    MIN_DURATION = 1000  # 1ms = 1000 微秒
    
    if not char_timelines:
        return
    
    # 第 1 轮：确保每个时间线都有正的持续时间
    for i in range(len(char_timelines)):
        duration = char_timelines[i]['end'] - char_timelines[i]['start']
        
        if duration < MIN_DURATION:
            # 需要调整
            if i < len(char_timelines) - 1:
                # 不是最后一个：从下一个字符借时间
                next_start = char_timelines[i+1]['start']
                needed_duration = MIN_DURATION
                
                if next_start - char_timelines[i]['start'] > needed_duration:
                    # 有足够空间
                    char_timelines[i]['end'] = char_timelines[i]['start'] + needed_duration
                else:
                    # 空间不足：取中点
                    mid = (char_timelines[i]['start'] + next_start) // 2
                    char_timelines[i]['end'] = mid
                    char_timelines[i+1]['start'] = mid
            else:
                # 最后一个字符：延长结束时间
                char_timelines[i]['end'] = char_timelines[i]['start'] + MIN_DURATION
    
    # 第 2 轮：确保连续性（无间隙、无重叠）
    for i in range(1, len(char_timelines)):
        if char_timelines[i]['start'] < char_timelines[i-1]['end']:
            # 有重叠：调整为相等
            char_timelines[i]['start'] = char_timelines[i-1]['end']
        
        # 再次检查持续时间
        duration = char_timelines[i]['end'] - char_timelines[i]['start']
        if duration < MIN_DURATION:
            char_timelines[i]['end'] = char_timelines[i]['start'] + MIN_DURATION
    
    # 第 3 轮：确保第一个字符从合理时间开始
    if char_timelines[0]['start'] < 0:
        char_timelines[0]['start'] = 0
    
    # 第 4 轮：重新检查所有持续时间
    for i in range(len(char_timelines)):
        duration = char_timelines[i]['end'] - char_timelines[i]['start']
        if duration < MIN_DURATION:
            char_timelines[i]['end'] = char_timelines[i]['start'] + MIN_DURATION

def _global_optimize_timelines(timelines: list[dict], min_time: float, max_time: float):
    """
    全局优化时间戳，消除累积误差
    
    策略：
    1. 确保严格递增和连续
    2. 重新分配不均匀的时间间隔
    3. 确保首尾精确对齐
    """
    if not timelines:
        return
    
    MIN_DURATION = 1000  # 1ms
    n = len(timelines)
    
    # 第 1 轮：确保边界有效
    for t in timelines:
        t['start'] = max(min_time, min(t['start'], max_time))
        t['end'] = max(min_time, min(t['end'], max_time))
    
    # 第 2 轮：确保连续性（前向传递）
    for i in range(1, n):
        if timelines[i]['start'] < timelines[i-1]['end']:
            timelines[i]['start'] = timelines[i-1]['end']
    
    # 第 3 轮：检查并修复大间隙（后向传递）
    for i in range(n - 2, -1, -1):
        gap = timelines[i+1]['start'] - timelines[i]['end']
        if gap > 100000:  # 间隙 > 100ms
            # 将间隙平均分配到两个片段
            adjustment = gap / 2
            timelines[i]['end'] += adjustment
            timelines[i+1]['start'] -= adjustment
    
    # 第 4 轮：确保最小持续时间
    for i in range(n):
        duration = timelines[i]['end'] - timelines[i]['start']
        if duration < MIN_DURATION:
            if i < n - 1:
                # 从下一个片段借时间
                next_gap = timelines[i+1]['end'] - timelines[i+1]['start']
                if next_gap > MIN_DURATION * 3:
                    timelines[i]['end'] = timelines[i]['start'] + MIN_DURATION
                    timelines[i+1]['start'] = timelines[i]['end']
                else:
                    # 取中点
                    mid = (timelines[i]['start'] + timelines[i+1]['start']) / 2
                    timelines[i]['end'] = mid
                    timelines[i+1]['start'] = mid
            else:
                # 最后一个片段
                timelines[i]['end'] = max_time
    
    # 第 5 轮：确保最后一个结束于总时长
    if timelines[-1]['end'] < max_time:
        gap = max_time - timelines[-1]['end']
        if gap < 2000000:  # 小于 2 秒
            timelines[-1]['end'] = max_time
    
    # 第 6 轮：最终验证无重叠
    for i in range(n - 1):
        if timelines[i]['end'] > timelines[i+1]['start']:
            # 取精确中点
            mid = (timelines[i]['end'] + timelines[i+1]['start']) / 2
            timelines[i]['end'] = mid
            timelines[i+1]['start'] = mid
    
    # 第 7 轮：全局平滑（可选）
    # 如果时间间隔差异太大，进行平滑处理
    if n > 2:
        durations = [t['end'] - t['start'] for t in timelines]
        avg_duration = sum(durations) / n
        
        # 检查是否有极端不均匀的情况
        for i in range(n):
            if durations[i] > avg_duration * 3 or durations[i] < avg_duration * 0.3:
                # 存在极端不均匀，但不调整（保留原始特征）
                pass

def _convert_to_microseconds(timelines: list[dict]):
    """将时间戳转换为整数微秒"""
    for t in timelines:
        t['start'] = int(round(t['start']))
        t['end'] = int(round(t['end']))

def _cleanup_audio_file(audio_file: str):
    """清理临时音频文件"""
    if audio_file and os.path.exists(audio_file):
        try:
            os.remove(audio_file)
            logger.info(f"Temporary audio file cleaned up: {audio_file}")
        except Exception as e:
            logger.error(f"Failed to remove temporary audio file {audio_file}: {str(e)}")
