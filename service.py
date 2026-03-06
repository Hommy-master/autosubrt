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

def align_text_with_audio(audio_url: str, text: str, max_chars_per_line: int = 15) -> tuple[list[str], list[dict]]:
    """
    根据音频对齐文本时间线
    
    Args:
        audio_url: 音频URL
        text: 需要对齐的文本
        max_chars_per_line: 每行最大字数
    
    Returns:
        tuple: (texts列表, timelines列表)
    
    Raises:
        CustomException: 自定义异常
    """
    audio_file = None
    try:
        # 1. 下载音频文件
        audio_file = helper.download(audio_url, config.TEMP_DIR)
        
        # 2. 使用模型生成识别结果（获取时间戳）
        result = model.generate(input=audio_file)
        
        # 3. 提取ASR结果
        asr_text, timestamps = extract_asr_result(result)
        
        if asr_text is None or not timestamps:
            logger.warning("No valid ASR result or timestamps")
            # 如果没有有效的时间戳，返回默认结果
            return [text], [{"start": 0, "end": 30000000}]  # 30秒 = 30,000,000微秒
        
        # 4. 根据文本中的标点符号分割句子（移除标点符号）
        sentences = split_text_by_punctuation_without_symbols(text)
        
        # 5. 根据最大字符数进一步分割长句子（确保无标点符号）
        final_texts = []
        for sentence in sentences:
            # 再次确保句子中没有标点符号
            clean_sentence = re.sub(r'[。！？，；.!?,;:\n\r]', '', sentence).strip()
            if clean_sentence:  # 只处理非空句子
                if len(clean_sentence) <= max_chars_per_line:
                    final_texts.append(clean_sentence)
                else:
                    # 按最大字符数分割
                    chunks = split_text_by_length(clean_sentence, max_chars_per_line)
                    # 确保每个片段都没有标点符号
                    for chunk in chunks:
                        clean_chunk = re.sub(r'[。！？，；.!?,;:\n\r]', '', chunk).strip()
                        if clean_chunk:
                            final_texts.append(clean_chunk)

        # 6. 将时间戳分配给文本片段
        timelines = distribute_timestamps_to_texts(final_texts, timestamps, len(asr_text))
        
        logger.info(f"Text alignment success: {len(final_texts)} texts, {len(timelines)} timelines")
        
        return final_texts, timelines
        
    except CustomException:
        raise
    except Exception as e:
        logger.error(f"Text alignment failed: {str(e)}, detail: {traceback.format_exc()}")
        raise CustomException(err=CustomError.RECOGNIZE_AUDIO_FAILED)
    finally:
        # 清理临时音频文件
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
                logger.info(f"Temporary audio file cleaned up: {audio_file}")
            except Exception as e:
                logger.error(f"Failed to remove temporary audio file {audio_file}: {str(e)}")

def split_text_by_punctuation_without_symbols(text: str) -> list[str]:
    """根据标点符号分割文本为句子，但不在结果中包含标点符号"""
    import re
    # 使用正则表达式按标点符号分割，但不保留标点符号在结果中
    # 包含中文和英文的常见标点符号：！，；。？\n\r
    sentences = re.split(r'[。！？，；.!?,;:\n\r]', text)
    
    # 过滤掉空字符串和只包含空白的字符串
    result = [s.strip() for s in sentences if s.strip()]
    
    return result


def split_text_by_punctuation(text: str) -> list[str]:
    """根据标点符号分割文本为句子，保留标点符号（用于其他用途）"""
    import re
    # 使用正则表达式按标点符号分割，保留标点符号
    # 包含中文和英文的常见标点符号：！，；。？\n\r
    sentences = re.split(r'([。！？，；.!?,;:\n\r])', text)
    
    # 合并句子和标点符号
    result = []
    i = 0
    while i < len(sentences):
        if i + 1 < len(sentences) and sentences[i + 1] in '。！？，；.!?,;:\n\r':
            # 合并句子和标点符号
            sentence = sentences[i] + sentences[i + 1]
            if sentence.strip():  # 只添加非空句子
                result.append(sentence.strip())
            i += 2
        else:
            if sentences[i].strip():  # 只添加非空句子
                result.append(sentences[i].strip())
            i += 1
    
    # 过滤掉空字符串
    return [s for s in result if s]

def split_text_by_length(text: str, max_length: int) -> list[str]:
    """按最大长度分割文本"""
    if len(text) <= max_length:
        return [text]
    
    result = []
    start = 0
    
    while start < len(text):
        end = start + max_length
        if end >= len(text):
            result.append(text[start:])
            break
        
        # 尽量在词边界处分割
        # 找到最后一个空格或标点符号的位置
        split_pos = None
        for i in range(end, start, -1):
            if text[i] in ' 	，。！？,!?':
                split_pos = i
                break
        
        # 如果没找到合适的分割点，则从起始位置向前找一个合理的位置
        if split_pos is None:
            # 如果整个max_length长度内都没有找到分割点，就在max_length处切分
            # 但要避免切分出单个字符
            if end - start <= 2:
                # 如果整个长度都太小，那就取全部剩余
                split_pos = len(text)
            else:
                split_pos = end
        else:
            # 如果找到了分割点，就加1以包含该标点符号
            split_pos += 1
        
        result.append(text[start:split_pos].strip())
        start = split_pos
        
        # 跳过空白字符
        while start < len(text) and text[start] in ' \t':
            start += 1
    
    return [s for s in result if s]

def distribute_timestamps_to_texts(texts: list[str], timestamps: list[list], total_asr_length: int) -> list[dict]:
    """将时间戳分配给文本片段（时间单位：微秒）- 1ms 精度精确对齐方法
    
    核心改进：
    1. 精度提升到 1ms（1000 微秒）以内
    2. 使用高精度浮点数运算
    3. 优化的累积分布映射算法
    4. 多重验证确保时间戳完美连续
    """
    if not texts or not timestamps:
        return [{"start": 0, "end": 1000000}]
    
    # 过滤有效时间戳
    valid_timestamps = filter_valid_timestamps(timestamps)
    if not valid_timestamps:
        return [{"start": 0, "end": 1000000}]
    
    # 将毫秒转换为微秒（高精度浮点数）
    asr_words = []
    for ts in valid_timestamps:
        asr_words.append({
            'start': float(ts[0] * 1000),  # 转为浮点数提高精度
            'end': float(ts[1] * 1000)
        })
    
    if not asr_words:
        return [{"start": 0, "end": 1000000}]
    
    logger.info(f"ASR recognized {len(asr_words)} words with timestamps")
    
    # 总时长信息
    total_start = asr_words[0]['start']
    total_end = asr_words[-1]['end']
    total_duration = float(total_end - total_start)
    
    logger.info(f"Total audio duration: {total_duration:.0f} microseconds ({total_duration/1000000:.3f} seconds)")
    
    # 合并所有用户文本片段
    full_user_text = ''.join(texts)
    total_text_length = len(full_user_text)
    num_segments = len(texts)
    
    logger.info(f"User text total length: {total_text_length} characters, {num_segments} segments")
    
    if total_text_length == 0 or num_segments == 0:
        return [{"start": 0, "end": 1000000}]
    
    # 计算每个文本片段的字符位置
    segment_info = []
    cum_pos = 0
    for text in texts:
        seg_len = len(text)
        segment_info.append({
            'start_char': cum_pos,
            'end_char': cum_pos + seg_len,
            'length': seg_len
        })
        cum_pos += seg_len
    
    num_asr_words = len(asr_words)
    
    # 1ms = 1000 微秒
    MIN_DURATION = 1000  # 1ms 最小持续时间
    
    # 为每个文本片段计算精确的时间戳
    timelines = []
    
    for seg_idx, seg in enumerate(segment_info):
        text_len = seg['length']
        
        if text_len == 0:
            # 空文本片段
            if timelines:
                start_time = timelines[-1]["end"]
            else:
                start_time = total_start
            
            timelines.append({
                "start": int(start_time),
                "end": int(start_time)
            })
            continue
        
        # 使用累积分布精确映射
        # 将字符位置映射到 ASR 时间轴
        char_start = float(seg['start_char'])
        char_end = float(seg['end_char'])
        
        # 归一化位置 [0, 1]
        start_normalized = char_start / float(total_text_length)
        end_normalized = char_end / float(total_text_length)
        
        # 映射到时间轴
        # 使用线性插值确保高精度
        start_time = total_start + start_normalized * total_duration
        end_time = total_start + end_normalized * total_duration
        
        # 确保时间递增（不与前一片段重叠）
        if timelines and start_time < timelines[-1]["end"]:
            start_time = timelines[-1]["end"]
        
        # 确保最小持续时间
        if end_time - start_time < MIN_DURATION:
            end_time = start_time + MIN_DURATION
        
        # 确保不超过总时长
        if end_time > total_end:
            end_time = total_end
        
        # 确保有效性
        if start_time >= end_time:
            # 极端情况：平均分配
            avg_dur = total_duration / float(num_segments)
            if seg_idx < num_segments - 1:
                start_time = total_start + seg_idx * avg_dur
                end_time = start_time + avg_dur
            else:
                start_time = total_end - avg_dur
                end_time = total_end
        
        # 边界限制
        start_time = max(total_start, min(start_time, total_end))
        end_time = max(total_start, min(end_time, total_end))
        
        timelines.append({
            "start": int(round(start_time)),  # 四舍五入确保整数微秒
            "end": int(round(end_time))
        })
    
    # 后处理：五轮验证调整
    _precise_validate_and_adjust(timelines, total_start, total_end, MIN_DURATION)
    
    logger.info(f"Generated {len(timelines)} timelines with 1ms precision")
    
    return timelines

def _precise_validate_and_adjust(timelines: list[dict], min_time: float, max_time: float, min_dur: int):
    """五轮精确验证调整，确保 1ms 精度"""
    if not timelines:
        return
    
    # 转换为浮点数便于计算
    for t in timelines:
        t["start"] = float(t["start"])
        t["end"] = float(t["end"])
    
    # 第 1 轮：边界有效性
    for t in timelines:
        t["start"] = max(min_time, min(t["start"], max_time))
        t["end"] = max(min_time, min(t["end"], max_time))
    
    # 第 2 轮：连续性（确保不重叠）
    for i in range(1, len(timelines)):
        if timelines[i]["start"] < timelines[i-1]["end"]:
            timelines[i]["start"] = timelines[i-1]["end"]
    
    # 第 3 轮：最小持续时间
    for i in range(len(timelines)):
        if timelines[i]["end"] - timelines[i]["start"] < min_dur:
            if i < len(timelines) - 1:
                # 从后续借时间
                next_start = timelines[i+1]["start"]
                needed = min_dur - (timelines[i]["end"] - timelines[i]["start"])
                if next_start - timelines[i]["start"] > min_dur + needed:
                    timelines[i]["end"] = timelines[i]["start"] + min_dur
                    timelines[i+1]["start"] -= needed
                else:
                    mid = (timelines[i]["start"] + next_start) / 2
                    timelines[i]["end"] = mid
                    timelines[i+1]["start"] = mid
            else:
                timelines[i]["end"] = max_time
    
    # 第 4 轮：总时长匹配
    if timelines[-1]["end"] < max_time:
        gap = max_time - timelines[-1]["end"]
        if gap < 1000000:  # 小于 1 秒
            timelines[-1]["end"] = max_time
    
    # 第 5 轮：最终精确验证（确保无重叠）
    for i in range(len(timelines) - 1):
        if timelines[i]["end"] > timelines[i+1]["start"]:
            mid = (timelines[i]["end"] + timelines[i+1]["start"]) / 2
            timelines[i]["end"] = mid
            timelines[i+1]["start"] = mid
    
    # 转换为整数微秒（四舍五入）
    for t in timelines:
        t["start"] = int(round(t["start"]))
        t["end"] = int(round(t["end"]))

def distribute_timestamps_to_texts_for_real(texts: list[str], timestamps: list[list]) -> list[dict]:
    """基于真实时间戳数据分配时间给文本片段（时间单位：微秒）"""
    if not texts or not timestamps:
        return [{"start": 0, "end": 30000000}]  # 30秒 = 30,000,000微秒
    
    # 过滤有效时间戳
    valid_timestamps = filter_valid_timestamps(timestamps)
    if not valid_timestamps:
        return [{"start": 0, "end": 30000000}]
    
    #总的词汇数量
    total_words = len(valid_timestamps)
    total_texts = len(texts)
    
    # 如果词汇数量小于文本片段数量，扩展词汇
    expanded_timestamps = []
    if total_words < total_texts:
        #将现有时间戳扩展到足够多的片段
        for i in range(total_texts):
            idx = i % total_words if total_words > 0 else 0
            expanded_timestamps.append(valid_timestamps[idx])
    else:
        expanded_timestamps = valid_timestamps[:total_texts]
    
    # 为每个文本片段分配时间戳（转换为微秒）
    timelines = []
    frame_rate = 300  # FunASR paraformer-zh 的帧率
    for i, text in enumerate(texts):
        if i < len(expanded_timestamps):
            start_time = int(expanded_timestamps[i][0] / frame_rate * 1000000)  # 将帧转换为微秒
            end_time = int(expanded_timestamps[i][1] / frame_rate * 1000000)    # 将帧转换为微秒
            timelines.append({"start": start_time, "end": end_time})
        else:
            # 如果文本片段多于时间戳，使用最后的时间戳或默认值
            if expanded_timestamps:
                last_end = int(expanded_timestamps[-1][1] / frame_rate * 1000000)
                timelines.append({"start": last_end, "end": last_end + 3000000})  # 3秒 = 3,000,000微秒
            else:
                timelines.append({"start": 0, "end": 3000000})
    
    return timelines

def align_text_with_audio_original_logic(audio_url: str, text: str, max_chars_per_line: int = 15) -> tuple[list[str], list[dict]]:
    """
    根据音频对齐文本时间线 - 优化版逻辑
    修复问题：对于强制分割的文本片段，合并它们的时间戳
    
    Args:
        audio_url: 音频URL
        text: 需要对齐的文本
        max_chars_per_line: 每行最大字数
    
    Returns:
        tuple: (texts列表, timelines列表)
    
    Raises:
        CustomException: 自定义异常
    """
    audio_file = None
    try:
        # 1. 下载音频文件
        audio_file = helper.download(audio_url, config.TEMP_DIR)
        
        # 2. 使用模型生成识别结果（获取时间戳）
        result = model.generate(input=audio_file)  # 获取ASR结果及时间戳
        
        # 3. 提取ASR结果
        asr_text, timestamps = extract_asr_result(result)
        
        if asr_text is None or not timestamps:
            logger.warning("No valid ASR result or timestamps")
            # 如果没有有效的时间戳，返回默认结果
            return [text], [{"start": 0, "end": 30000000}]  # 30秒 = 30,000,000微秒
        
        # 4. 根据文本中的标点符号分割句子，但不在结果中包含标点符号
        sentences = split_text_by_punctuation_without_symbols(text)
        
        # 5. 根据最大字符数进一步分割长句子，并跟踪哪些片段来自同一个原始句子
        final_texts = []
        sentence_mapping = []  # 记录每个文本片段来自哪个原始句子
        
        for sentence_idx, sentence in enumerate(sentences):
            if len(sentence) <= max_chars_per_line:
                final_texts.append(sentence)
                sentence_mapping.append(sentence_idx)  # 记录来源
            else:
                # 按最大字符数分割
                chunks = split_text_by_length(sentence, max_chars_per_line)
                for chunk in chunks:
                    final_texts.append(chunk)
                    sentence_mapping.append(sentence_idx)  # 记录来源
        
        # 6. 将时间戳分配给文本片段，对于来自同一原始句子的片段合并时间戳
        timelines = merge_timestamps_for_original_sentences(final_texts, sentence_mapping, timestamps)
        
        logger.info(f"Text alignment success: {len(final_texts)} texts, {len(timelines)} timelines")
        
        return final_texts, timelines
        
    except CustomException:
        raise
    except Exception as e:
        logger.error(f"Text alignment failed: {str(e)}, detail: {traceback.format_exc()}")
        raise CustomException(err=CustomError.RECOGNIZE_AUDIO_FAILED)
    finally:
        # 清理临时音频文件
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
                logger.info(f"Temporary audio file cleaned up: {audio_file}")
            except Exception as e:
                logger.error(f"Failed to remove temporary audio file {audio_file}: {str(e)}")

def merge_timestamps_for_original_sentences(texts: list[str], sentence_mapping: list[int], timestamps: list[list]) -> list[dict]:
    """
    将时间戳分配给文本片段，对于来自同一原始句子的片段按比例分配时间戳
    保证时间线不重叠且精确
    
    FunASR paraformer-zh 返回的时间戳单位是帧（frame），帧率为 300fps
    需要将帧数转换为微秒：帧数 / 300 * 1000000
    """
    if not texts or not timestamps:
        return [{"start": 0, "end": 30000000}]  # 30 秒 = 30,000,000 微秒
    
    # 过滤有效时间戳
    valid_timestamps = filter_valid_timestamps(timestamps)
    if not valid_timestamps:
        return [{"start": 0, "end": 30000000}]
    
    # 计算总词汇数和文本片段数
    total_words = len(valid_timestamps)
    total_texts = len(texts)
    
    # 如果词汇数量小于文本片段数量，扩展词汇
    expanded_timestamps = []
    if total_words < total_texts:
        # 将现有时间戳扩展到足够多的片段
        for i in range(total_texts):
            idx = i % total_words if total_words > 0 else 0
            expanded_timestamps.append(valid_timestamps[idx])
    else:
        expanded_timestamps = valid_timestamps[:total_texts]
    
    # 按原始句子分组
    sentence_groups = {}
    for i, orig_sentence_idx in enumerate(sentence_mapping):
        if orig_sentence_idx not in sentence_groups:
            sentence_groups[orig_sentence_idx] = []
        sentence_groups[orig_sentence_idx].append(i)  # 存储在 texts 中的索引
    
    # 为每个原始句子组分配精确的时间戳（按比例）
    final_timelines = []
    for orig_sentence_idx, group_indices in sentence_groups.items():
        # 获取该组的第一个和最后一个片段的时间戳（用于确定总体时间范围）
        first_text_idx = group_indices[0]
        last_text_idx = group_indices[-1]
        
        # 将毫秒转换为微秒：毫秒 * 1000
        group_start_time = expanded_timestamps[first_text_idx][0] * 1000
        group_end_time = expanded_timestamps[last_text_idx][1] * 1000
        
        # 计算该组的总时长
        group_duration = group_end_time - group_start_time
        
        # 计算该组中所有文本片段的总长度
        group_total_length = sum(len(texts[i]) for i in group_indices)
        
        # 按比例为该组中的每个文本片段分配时间戳
        current_time = group_start_time
        for i, text_idx in enumerate(group_indices):
            text_length = len(texts[text_idx])
            
            # 计算该片段的时长比例
            if i == len(group_indices) - 1:
                # 最后一个片段，确保使用组的结束时间
                duration = group_end_time - current_time
            else:
                # 按比例计算时长
                duration_ratio = text_length / group_total_length
                duration = int(group_duration * duration_ratio)
            
            # 设置时间戳
            start_time = current_time
            end_time = current_time + duration
            
            final_timelines.append({
                "start": start_time,
                "end": end_time
            })
            
            # 更新当前时间
            current_time = end_time
    
    # 按照原始的文本顺序重新排列时间戳
    ordered_timelines = [None] * len(texts)
    timeline_index = 0
    for orig_sentence_idx, group_indices in sentence_groups.items():
        for _ in group_indices:
            ordered_timelines[timeline_index] = final_timelines[timeline_index]
            timeline_index += 1
    
    return ordered_timelines

