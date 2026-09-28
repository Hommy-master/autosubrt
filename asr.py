"""
语音识别引擎（faster-whisper / CTranslate2）

用 faster-whisper 替换原有的 FunASR（paraformer-zh + ct-punc），对外保持完全一致的结果结构，
上层字幕、对齐业务无需感知底层引擎的差异：

    text        —— 识别文本，自带标点；中文直接拼接，英文单词之间保留空格
    chars       —— 逐字序列，不含任何空白字符
    timestamps  —— 与 chars 一一对应的 [开始毫秒, 结束毫秒]

FunASR 的约定是「纯中文去除字符间空格直接拼接，timestamp 与文本一一对应（毫秒）」，
这里沿用同样的约定，保证 len(timestamps) == len(chars) == len(text_plain)，
下游依赖该约定的字幕断句、字级对齐逻辑才能得到相同的结果。

whisper 只提供词级时间戳，因此每个词的时间区间会按字数均分到它的每个字上，
与原来「字级时间线由词级时间线插值得到」的精度一致。
"""

import os
import traceback
from dataclasses import dataclass, field

import config  # noqa: F401  # 必须先于 huggingface_hub 导入：config 中会设置 HF_ENDPOINT 下载镜像
import helper
from exceptions import CustomError, CustomException
from logger import logger

from faster_whisper import WhisperModel


@dataclass
class RecognitionResult:
    """识别结果"""

    text: str = ""
    chars: list[str] = field(default_factory=list)
    timestamps: list[list[int]] = field(default_factory=list)
    duration: float = 0.0
    language: str = ""

    @property
    def text_plain(self) -> str:
        """不含空白字符的纯字符文本，与 timestamps 一一对应"""
        return "".join(self.chars)


# 模型实例（进程内只加载一次）
_model: WhisperModel = None

# whisper 固定使用 16kHz 采样率
SAMPLE_RATE = 16000

def load_model() -> None:
    """加载语音识别模型

    设备为 auto 时优先尝试 GPU；若 GPU 实际不可用（例如镜像里缺少 CUDA 运行库），
    会自动回退到 CPU，避免出现「启动成功但每次识别都失败」的假健康状态。

    Raises:
        Exception: 模型加载失败
    """
    global _model
    if _model is not None:
        return

    device, compute_type = _resolve_device()
    try:
        _model = _create_model(device, compute_type)
    except Exception as e:
        # 只有 auto 模式才回退；显式指定 cuda 时直接报错，避免掩盖配置问题
        if config.ASR_DEVICE != "auto" or device != "cuda":
            logger.error(f"faster-whisper model load failed: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        logger.warning(f"CUDA is not usable ({str(e)}), fallback to CPU")
        device, compute_type = "cpu", "int8"
        try:
            _model = _create_model(device, compute_type)
        except Exception as cpu_error:
            logger.error(f"faster-whisper model load failed: {str(cpu_error)}")
            logger.error(traceback.format_exc())
            raise

    logger.info(
        f"faster-whisper model load success, model: {config.ASR_MODEL}, "
        f"device: {device}, compute_type: {compute_type}"
    )

def _create_model(device: str, compute_type: str) -> WhisperModel:
    """创建模型实例并做一次推理自检

    Args:
        device: 推理设备
        compute_type: 计算精度

    Returns:
        WhisperModel: 模型实例
    """
    logger.info(
        f"load faster-whisper model: {config.ASR_MODEL}, device: {device}, "
        f"compute_type: {compute_type}, model_dir: {config.MODEL_DIR}"
    )

    os.makedirs(config.MODEL_DIR, exist_ok=True)
    model = WhisperModel(
        config.ASR_MODEL,
        device=device,
        compute_type=compute_type,
        download_root=config.MODEL_DIR,
        # 0 表示自动：容器内按 CPU 配额，否则交给 CTranslate2 自行决定
        cpu_threads=config.ASR_CPU_THREADS or helper.cgroup_cpu_quota(),
    )

    _verify_inference(model)
    return model

def _verify_inference(model: WhisperModel) -> None:
    """用一段静音跑一次最短推理做自检

    缺少 CUDA 运行库时模型依然能加载成功，只有真正推理时才会报错，
    因此必须在加载阶段实际跑一次，才能保证后续请求不会全部失败。

    Args:
        model: 模型实例
    """
    import numpy as np

    silence = np.zeros(SAMPLE_RATE, dtype=np.float32)  # 1 秒静音
    segments, _ = model.transcribe(silence, language=config.ASR_LANGUAGE or None, beam_size=1)

    # 生成器必须消费完才会真正执行推理
    for _ in segments:
        pass

def transcribe(audio_path: str) -> RecognitionResult:
    """音频 -> 识别结果

    Args:
        audio_path: 音频文件路径

    Returns:
        RecognitionResult: 识别结果

    Raises:
        CustomException: 识别音频失败
    """
    if _model is None:
        logger.error("ASR model not loaded")
        raise CustomException(err=CustomError.RECOGNIZE_AUDIO_FAILED, detail="ASR model not loaded")

    try:
        # language 为空表示自动检测语种
        segments, info = _model.transcribe(
            audio_path,
            language=config.ASR_LANGUAGE or None,
            beam_size=config.ASR_BEAM_SIZE,
            word_timestamps=True,
            vad_filter=config.ASR_VAD_FILTER,
        )

        # segments 是生成器，遍历完才会真正执行识别
        result = _collect(segments)
        result.duration = info.duration
        result.language = info.language
    except CustomException:
        raise
    except Exception as e:
        logger.error(f"ASR process failed: {str(e)}, detail: {traceback.format_exc()}")
        raise CustomException(err=CustomError.RECOGNIZE_AUDIO_FAILED)

    logger.info(
        f"ASR success, language: {result.language}, text length: {len(result.chars)}, "
        f"duration: {result.duration:.2f}s"
    )
    return result

def _collect(segments) -> RecognitionResult:
    """整理识别结果，生成逐字时间线

    Args:
        segments: faster-whisper 的识别片段生成器

    Returns:
        RecognitionResult: 识别结果
    """
    chars: list[str] = []
    timestamps: list[list[int]] = []
    parts: list[str] = []

    for segment in segments:
        segment_text = (segment.text or "").strip()
        if segment_text:
            parts.append(segment_text)

        _append_segment(chars, timestamps, segment)

    return RecognitionResult(
        text=_join_parts(parts),
        chars=chars,
        timestamps=timestamps,
    )

def _append_segment(chars: list[str], timestamps: list[list[int]], segment) -> None:
    """把一个识别片段中的词拆解成逐字时间线

    Args:
        chars: 逐字序列，会被原地追加
        timestamps: 逐字时间戳，会被原地追加
        segment: 识别片段
    """
    # 模型没有返回词级时间线时，退化成用句子级时间线按字数均分
    words = getattr(segment, "words", None) or [_FallbackWord(segment)]

    for word in words:
        content = (word.word or "").strip()
        if not content:
            continue

        start_ms = _to_ms(word.start, segment.start)
        end_ms = _to_ms(word.end, segment.end)
        if end_ms <= start_ms:
            end_ms = start_ms + 1

        _append_word(chars, timestamps, content, start_ms, end_ms)

def _append_word(
    chars: list[str],
    timestamps: list[list[int]],
    content: str,
    start_ms: int,
    end_ms: int,
) -> None:
    """把单个词的时间区间按字数均分给它的每一个字

    Args:
        chars: 逐字序列，会被原地追加
        timestamps: 逐字时间戳，会被原地追加
        content: 词文本
        start_ms: 词开始时间（毫秒）
        end_ms: 词结束时间（毫秒）
    """
    # 词内部若还残留空白（如 "10 000"），先按空白切开，再按长度比例分配时长
    tokens = content.split()
    if not tokens:
        return

    token_durations = _allocate(end_ms - start_ms, [len(token) for token in tokens])
    cursor = start_ms

    for token, token_duration in zip(tokens, token_durations):
        token_end = cursor + token_duration
        char_durations = _allocate(token_duration, [1] * len(token))
        char_cursor = cursor

        for char, char_duration in zip(token, char_durations):
            char_end = char_cursor + char_duration
            chars.append(char)
            timestamps.append([char_cursor, max(char_end, char_cursor + 1)])
            char_cursor = char_end

        cursor = token_end

def _allocate(duration: int, weights: list[int]) -> list[int]:
    """按权重把时长（毫秒）整数分配给各个子项，保证分配结果之和等于总时长

    Args:
        duration: 待分配的时长（毫秒）
        weights: 每个子项的权重

    Returns:
        list[int]: 每个子项分到的时长（毫秒）
    """
    total_weight = sum(weights)
    shares = [duration * weight // total_weight for weight in weights]

    # 整除产生的余数逐项补足，避免累计误差
    for index in range(duration - sum(shares)):
        shares[index % len(shares)] += 1

    return shares

def _join_parts(parts: list[str]) -> str:
    """拼接片段文本

    与 FunASR 的后处理规则一致：中日韩字符之间不加空格，
    拉丁字母、数字之间补一个空格，保证英文单词不被粘连。

    Args:
        parts: 片段文本列表

    Returns:
        str: 拼接后的文本
    """
    text = ""
    for part in parts:
        if text and _is_latin(text[-1]) and _is_latin(part[0]):
            text += " "
        text += part

    return text

def _is_latin(char: str) -> bool:
    """判断字符是否为拉丁字母或数字（这类字符之间需要空格分隔）"""
    return char.isascii() and char.isalnum()

def _to_ms(value: float, fallback: float) -> int:
    """秒 -> 毫秒（整数），时间缺失时回退到片段级时间

    Args:
        value: 待转换的秒数，可能为 None
        fallback: value 缺失时使用的秒数

    Returns:
        int: 毫秒
    """
    seconds = value if value is not None else fallback
    return max(0, int(round((seconds or 0) * 1000)))

def _resolve_device() -> tuple[str, str]:
    """解析推理设备与计算精度

    Returns:
        tuple[str, str]: (设备, 计算精度)
    """
    device = config.ASR_DEVICE
    if device == "auto":
        device = "cuda" if _cuda_available() else "cpu"

    compute_type = config.ASR_COMPUTE_TYPE
    if compute_type == "auto":
        # GPU 使用 float16，CPU 使用 int8（体积小、速度快，精度损失可忽略）
        compute_type = "float16" if device == "cuda" else "int8"

    return device, compute_type

def _cuda_available() -> bool:
    """检测是否存在可用的 CUDA 设备（不依赖 torch）"""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception as e:
        logger.warning(f"Failed to detect CUDA device, fallback to CPU: {str(e)}")
        return False


class _FallbackWord:
    """词级时间线缺失时的兜底对象，直接使用句子级时间线"""

    __slots__ = ("word", "start", "end")

    def __init__(self, segment):
        self.word = segment.text or ""
        self.start = segment.start
        self.end = segment.end
