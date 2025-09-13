from funasr import AutoModel
import pysrt
import os
import uuid
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import traceback
from contextlib import asynccontextmanager
import router
from logger import logger


# 创建FastAPI应用
app = FastAPI(title="AutoSubRT API", description="语音转SRT字幕服务")

# 1. 注册路由
app.include_router(router.router, prefix="/openapi", tags=["autosubrt"])

# 创建临时目录用于存储音频和SRT文件
TEMP_DIR = "temp_files"
OUTPUT_DIR = "output"

# 确保目录存在
for dir_path in [TEMP_DIR, OUTPUT_DIR]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        logger.info(f"创建目录: {dir_path}")

# 数据模型
class AudioRequest(BaseModel):
    audio_url: str

class SubtitleResponse(BaseModel):
    srt_url: str
    message: str

# 加载模型（只加载一次）
model = None

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---------------- 启动 ----------------
    # await create_db_pool()
    # await start_redis()
    print("✅ app start")
    # 在应用启动时加载模型
    load_model()
    yield
    # ---------------- 关闭 ----------------
    # await close_db_pool()
    # await stop_redis()
    print("❌ app shutdown")

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

def download_audio(audio_url):
    """下载音频文件到临时目录"""
    try:
        logger.info(f"开始下载音频文件: {audio_url}")
        # 生成唯一文件名
        file_id = str(uuid.uuid4())
        file_extension = os.path.splitext(audio_url)[1] or '.mp3'
        temp_file_path = os.path.join(TEMP_DIR, f"{file_id}{file_extension}")
        
        # 下载文件
        response = requests.get(audio_url, stream=True, timeout=60)
        response.raise_for_status()
        
        with open(temp_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"音频文件下载完成，保存至: {temp_file_path}")
        return temp_file_path
    except Exception as e:
        logger.error(f"下载音频文件失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=f"下载音频文件失败: {str(e)}")

def process_audio_to_srt(audio_path):
    """处理音频文件并生成SRT字幕"""
    try:
        logger.info(f"开始处理音频文件: {audio_path}")
        
        # 使用模型生成识别结果
        result = model.generate(input=audio_path)
        
        # 转换为SRT
        subs = pysrt.SubRipFile()
        
        # 根据实际的result结构处理
        if isinstance(result, list) and len(result) > 0 and "text" in result[0]:
            item = result[0]
            text = item["text"]
            timestamps = item.get("timestamp", [])
            
            # 打印时间戳信息（调试用）
            logger.info(f"识别文本长度: {len(text)}")
            logger.info(f"时间戳数量: {len(timestamps)}")
            
            # 拆分文本为句子级别的SRT条目
            sentences = split_text_by_timestamp(text, timestamps)
            
            # 创建SRT条目
            for i, (start_ms, end_ms, sentence_text) in enumerate(sentences, 1):
                start_time = ms_to_subrip_time(start_ms)
                end_time = ms_to_subrip_time(end_ms)
                subs.append(pysrt.SubRipItem(index=i, start=start_time, end=end_time, text=sentence_text))
                
            logger.info(f"成功创建了{len(sentences)}个SRT条目")
        else:
            logger.warning("无法识别result的结构，保存空的SRT文件")
        
        # 生成唯一的SRT文件名
        srt_id = str(uuid.uuid4())
        srt_file_path = os.path.join(OUTPUT_DIR, f"{srt_id}.srt")
        
        # 保存SRT文件
        subs.save(srt_file_path)
        logger.info(f"SRT文件已保存为: {srt_file_path}")
        
        # 返回相对于output目录的路径
        return os.path.basename(srt_file_path)
    except Exception as e:
        logger.error(f"处理音频文件失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"处理音频文件失败: {str(e)}")

# API端点
@app.post("/generate-subtitle", response_model=SubtitleResponse, summary="生成音频字幕")
def generate_subtitle(request: AudioRequest):
    """
    根据提供的音频URL生成SRT格式字幕
    
    - **audio_url**: 音频文件的URL地址
    - **返回**: 包含srt_url和message的JSON响应
    """
    try:
        # 下载音频文件
        audio_path = download_audio(request.audio_url)
        
        try:
            # 处理音频并生成SRT
            srt_filename = process_audio_to_srt(audio_path)
            
            # 构建SRT文件的URL（假设通过/output/路径访问）
            # 实际部署时可能需要根据环境变量或配置调整
            srt_url = f"/output/{srt_filename}"
            
            return SubtitleResponse(
                srt_url=srt_url,
                message="字幕生成成功"
            )
        finally:
            # 清理临时音频文件
            if os.path.exists(audio_path):
                os.remove(audio_path)
                logger.info(f"已清理临时音频文件: {audio_path}")
    except HTTPException:
        # 已记录的HTTP异常直接抛出
        raise
    except Exception as e:
        logger.error(f"生成字幕时发生未预期错误: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="生成字幕时发生错误")

# 提供SRT文件下载
@app.get("/output/{filename}", summary="下载SRT字幕文件")
def get_subtitle_file(filename: str):
    """
    下载生成的SRT字幕文件
    
    - **filename**: SRT文件名
    - **返回**: SRT文件下载
    """
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="text/plain"
    )

if __name__ == "__main__":
    import uvicorn
    
    # 运行FastAPI应用 - 移除workers参数以便直接通过脚本运行
    # 在生产环境中，建议使用命令：uvicorn main:app --host 0.0.0.0 --port 60000 --workers 4
    logger.info("Start AutoSubRT Service ...")
    uvicorn.run(app, host="0.0.0.0", port=60000)