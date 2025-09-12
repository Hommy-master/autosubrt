from funasr import AutoModel
import pysrt


def ms_to_subrip_time(ms):
    """将毫秒转换为pysrt.SubRipTime对象"""
    total_seconds = ms / 1000
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int((total_seconds - int(total_seconds)) * 1000)
    return pysrt.SubRipTime(hours=hours, minutes=minutes, seconds=seconds, milliseconds=milliseconds)


def split_text_by_timestamp(text, timestamps):
    """根据时间戳拆分文本，创建更准确的SRT条目"""
    # 过滤掉只有一个时间点的时间戳（最后一个时间戳可能只有结束时间）
    valid_timestamps = [ts for ts in timestamps if len(ts) >= 2]
    
    # 分割文本为单词列表
    words = text.split()
    
    # 如果没有足够的时间戳或者时间戳和单词数量不匹配，使用更智能的策略
    sentences = []
    
    # 策略1：基于时间间隔分割句子
    # 找出时间戳中的大间隔（超过1秒的间隔）作为句子分割点
    sentence_start_idx = 0
    for i in range(1, len(valid_timestamps)):
        # 计算当前时间戳的结束时间和下一个时间戳的开始时间之间的间隔
        prev_end = valid_timestamps[i-1][1]
        curr_start = valid_timestamps[i][0]
        interval = curr_start - prev_end
        
        # 如果间隔超过1秒，认为是一个句子结束
        if interval > 1000 and i > sentence_start_idx:
            # 创建一个句子
            start_ms = valid_timestamps[sentence_start_idx][0]
            end_ms = valid_timestamps[i-1][1]
            # 获取对应的文本
            sentence_text = ''.join(words[sentence_start_idx:i])
            sentences.append((start_ms, end_ms, sentence_text))
            sentence_start_idx = i
    
    # 添加最后一个句子
    if sentence_start_idx < len(valid_timestamps):
        start_ms = valid_timestamps[sentence_start_idx][0]
        end_ms = valid_timestamps[-1][1]
        sentence_text = ''.join(words[sentence_start_idx:])
        sentences.append((start_ms, end_ms, sentence_text))
    
    # 如果没有分割出句子（可能是因为没有大间隔），使用原始策略
    if not sentences and words and valid_timestamps:
        start_ms = valid_timestamps[0][0]
        end_ms = valid_timestamps[-1][1]
        sentence_text = ''.join(words)
        sentences.append((start_ms, end_ms, sentence_text))
    
    # 如果仍然没有句子，返回一个默认的条目
    if not sentences:
        sentences.append((0, 30000, text))  # 假设30秒的持续时间
    
    return sentences


if __name__ == "__main__":
    # 语音识别
    model = AutoModel(model="paraformer-zh", disable_update=True)
    result = model.generate(input="C:\\workspace\\code\\test\\dea828e6-94f7-44e2-a341-3790ddf0f57a.MP3")
    
    # 转换为SRT
    subs = pysrt.SubRipFile()
    
    # 根据实际的result结构处理
    if isinstance(result, list) and len(result) > 0 and "text" in result[0]:
        item = result[0]
        text = item["text"]
        timestamps = item.get("timestamp", [])
        
        # 打印时间戳信息（调试用）
        print(f"原始文本: {text}")
        print(f"时间戳数量: {len(timestamps)}")
        
        # 拆分文本为句子级别的SRT条目
        sentences = split_text_by_timestamp(text, timestamps)
        
        # 创建SRT条目
        for i, (start_ms, end_ms, sentence_text) in enumerate(sentences, 1):
            start_time = ms_to_subrip_time(start_ms)
            end_time = ms_to_subrip_time(end_ms)
            subs.append(pysrt.SubRipItem(index=i, start=start_time, end=end_time, text=sentence_text))
            
        print(f"成功创建了{len(sentences)}个SRT条目")
    else:
        print("无法识别result的结构，保存空的SRT文件")
    
    subs.save("output.srt")
    print("SRT文件已保存为output.srt")