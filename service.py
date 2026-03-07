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

def align_text_with_audio(audio_url: str, text: str, max_chars_per_line: int = 15) -> tuple[list[str], list[dict]]:
    """
    根据音频对齐文本时间线 - 优化版本
    
    Args:
        audio_url: 音频 URL
        text: 需要对齐的文本
        max_chars_per_line: 每行最大字数
    
    Returns:
        tuple: (texts 列表，timelines 列表)
    
    Raises:
        CustomException: 自定义异常
    """
    audio_file = None
    try:
        # 1. 下载音频文件
        audio_file = helper.download(audio_url, config.TEMP_DIR)
        
        # 2. 使用模型生成识别结果（获取时间戳）
        result = model.generate(input=audio_file)
        
        # 3. 提取 ASR 结果
        asr_text, timestamps = extract_asr_result(result)
        
        if asr_text is None or not timestamps:
            logger.warning("No valid ASR result or timestamps")
            return [text], [{"start": 0, "end": 30000000}]
        
        logger.info(f"ASR recognized text length: {len(asr_text)}, timestamps count: {len(timestamps)}")
        
        # 4. 将用户文本与 ASR 文本进行匹配，找到最佳分割点
        user_sentences = split_text_by_punctuation_without_symbols(text)
        
        # 5. 基于累积分布函数 (CDF) 的精确对齐
        final_texts, timelines = _cdf_based_alignment(
            user_sentences, 
            timestamps,
            max_chars_per_line
        )
        
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

def _cdf_based_alignment(
    user_sentences: list[str], 
    timestamps: list[list],
    max_chars_per_line: int
) -> tuple[list[str], list[dict]]:
    """
    基于累积分布函数 (CDF) 的时间戳对齐 - 优化版本
    
    核心改进：
    1. 使用更精确的浮点数运算减少取整误差
    2. 全局优化时间戳分配，避免局部最优
    3. 增强的后处理验证机制
    """
    if not user_sentences or not timestamps:
        return [], []
    
    # 过滤有效时间戳
    valid_timestamps = filter_valid_timestamps(timestamps)
    if not valid_timestamps:
        return [], []
    
    # 构建 ASR 词汇时间轴（毫秒转微秒）
    asr_words = []
    for ts in valid_timestamps:
        asr_words.append({
            'start': float(ts[0] * 1000),
            'end': float(ts[1] * 1000)
        })
    
    num_asr_words = len(asr_words)
    total_start = asr_words[0]['start']
    total_end = asr_words[-1]['end']
    total_duration = total_end - total_start
    
    logger.info(f"ASR words: {num_asr_words}, duration: {total_duration/1000000:.2f}s")
    
    # 合并所有用户句子
    full_user_text = ''.join(user_sentences)
    total_text_length = len(full_user_text)
    
    if total_text_length == 0:
        return [], []
    
    # 计算每个字符的累积位置
    char_positions = []
    for i, char in enumerate(full_user_text):
        char_positions.append({
            'index': i,
            'normalized_pos': float(i) / float(total_text_length - 1) if total_text_length > 1 else 0.5
        })
    
    # 为每个句子计算精确的时间戳
    sentence_timelines = []
    
    for sentence_idx, sentence in enumerate(user_sentences):
        sent_len = len(sentence)
        
        # 找到这个句子在完整文本中的起始和结束字符索引
        start_char_idx = sum(len(s) for s in user_sentences[:sentence_idx])
        end_char_idx = start_char_idx + sent_len - 1
        
        # 计算归一化位置
        start_norm = float(start_char_idx) / float(max(1, total_text_length - 1))
        end_norm = float(end_char_idx) / float(max(1, total_text_length - 1))
        
        # 映射到 ASR 词汇索引（使用更精确的方法）
        # 关键改进：使用 (num_asr_words - 1) 而不是 num_asr_words
        start_float_idx = start_norm * float(num_asr_words - 1)
        end_float_idx = end_norm * float(num_asr_words - 1)
        
        # 获取时间戳（不取整，保持浮点精度）
        # 使用线性插值提高边界精度
        if num_asr_words > 1:
            # 对于非整数索引，使用相邻词汇的加权平均
            start_floor = int(start_float_idx)
            start_frac = start_float_idx - start_floor
            
            if start_floor < num_asr_words - 1:
                start_time = (asr_words[start_floor]['start'] * (1 - start_frac) + 
                             asr_words[start_floor + 1]['start'] * start_frac)
            else:
                start_time = asr_words[start_floor]['start']
            
            end_floor = int(end_float_idx)
            end_frac = end_float_idx - end_floor
            
            if end_floor < num_asr_words - 1:
                end_time = (asr_words[end_floor]['start'] * (1 - end_frac) + 
                           asr_words[end_floor + 1]['start'] * end_frac)
            else:
                end_time = asr_words[end_floor]['start']
        else:
            start_time = asr_words[0]['start']
            end_time = asr_words[0]['end']
        
        sentence_timelines.append({
            'text': sentence,
            'start': start_time,
            'end': end_time,
            'length': sent_len
        })
    
    # 进一步分割长句子
    final_texts = []
    final_timelines = []
    
    for sent_info in sentence_timelines:
        text = sent_info['text']
        sentence_start = sent_info['start']
        sentence_end = sent_info['end']
        sentence_len = sent_info['length']
        
        if len(text) <= max_chars_per_line:
            # 不需要分割
            final_texts.append(text)
            final_timelines.append({
                'start': sentence_start,
                'end': sentence_end
            })
        else:
            # 需要分割成多个片段
            num_chunks = (len(text) + max_chars_per_line - 1) // max_chars_per_line
            
            # 为每个片段计算精确的时间戳
            for i in range(num_chunks):
                chunk_start_char = i * max_chars_per_line
                chunk_end_char = min((i + 1) * max_chars_per_line, len(text))
                chunk_len = chunk_end_char - chunk_start_char
                
                # 计算该片段的相对位置
                chunk_rel_start = float(chunk_start_char) / float(max(1, sentence_len - 1)) if sentence_len > 1 else 0.5
                chunk_rel_end = float(chunk_end_char - 1) / float(max(1, sentence_len - 1)) if sentence_len > 1 else 0.5
                
                # 映射到绝对时间
                chunk_start_time = sentence_start + chunk_rel_start * (sentence_end - sentence_start)
                
                if i == num_chunks - 1:
                    # 最后一个片段，确保结束时间正确
                    chunk_end_time = sentence_end
                else:
                    chunk_end_time = sentence_start + chunk_rel_end * (sentence_end - sentence_start)
                
                chunk_text = text[chunk_start_char:chunk_end_char]
                
                if chunk_text.strip():
                    final_texts.append(chunk_text)
                    final_timelines.append({
                        'start': chunk_start_time,
                        'end': chunk_end_time
                    })
    
    # 后处理：全局优化时间戳
    _global_optimize_timelines(final_timelines, total_start, total_end)
    
    # 转换为整数微秒
    for t in final_timelines:
        t['start'] = int(round(t['start']))
        t['end'] = int(round(t['end']))
    
    return final_texts, final_timelines

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
