"""
标点恢复（ct-punc / CT-Transformer ONNX）

whisper 对中文的标点不可靠：短音频可能整段没有任何标点，逗号的位置也不稳定。
因此识别文本在返回前统一过一次标点恢复模型，保证接口输出的 text 一定带标点。

模型是 FunASR 的 ct-punc（punc_ct-transformer_zh-cn-common-vocab272727），
已导出为 ONNX，用 onnxruntime 推理，不需要 torch。

两个关键约定：

1. 只插入标点，绝不改动原字符。输入里已有的标点会先被剔除，统一由模型重新决定，
   避免出现「whisper 的句号 + 模型的句号」叠在一起；
2. 逐字 tokenize。该模型的词表来自语音识别，不含数字、~、大写字母等，
   词表外的字符只用一个 unk 占位参与推理，输出时仍还原为原字符，
   避免被替换成 <unk> 而丢失信息。
"""

import os

import numpy as np
import onnxruntime

import config  # noqa: F401  # 必须先于 huggingface_hub 导入：config 中会设置 HF_ENDPOINT / HF_HUB_DISABLE_XET
import helper
from exceptions import CustomError, CustomException
from logger import logger


# 标点集合：既用于剔除输入里已有的标点，也用于补标点后的判断。
# 需覆盖 whisper 可能输出的标点，以及模型能输出的标点（，。？、）
PUNCTUATIONS = set("。！？，、；：.!?,;:")

# 模型元数据里表示「该位置不加标点」的标记
_NO_PUNCT = "_"
# 模型元数据里表示「未知」的标记
_UNK = "<unk>"

# 分段推理参数，与 sherpa-onnx 的参考实现保持一致：
# 每段最多 SEGMENT_SIZE 个字，段内找不到句末标点时向后累积，直到超过 MAX_LEN 强制断句
_SEGMENT_SIZE = 20
_MAX_LEN = 200

# 模型实例（进程内只加载一次）
_session: onnxruntime.InferenceSession = None
_token2id: dict[str, int] = {}
_id2punct: list[str] = []
_unk_id = 0
_unk_punct = 0
_label_dot = 0
_label_comma = 0
_label_quest = 0
_label_none = 0

def load_model() -> None:
    """加载标点恢复模型

    Raises:
        Exception: 模型加载失败（PUNCT_ENABLED 为 false 时不加载）
    """
    global _session
    if _session is not None or not config.PUNCT_ENABLED:
        return

    model_path = _resolve_model_path()

    try:
        options = onnxruntime.SessionOptions()
        # 只保留 error 级别日志，避免 ONNX Runtime 的告警刷屏
        options.log_severity_level = 3
        # 0 表示自动：容器内按 CPU 配额，避免线程数远超配额引起争抢
        threads = config.PUNCT_CPU_THREADS or helper.cgroup_cpu_quota()
        if threads:
            options.intra_op_num_threads = threads

        session = onnxruntime.InferenceSession(model_path, options)
        _init_metadata(session)
    except Exception as e:
        logger.error(f"punctuation model load failed: {str(e)}, model: {model_path}")
        raise

    _session = session
    logger.info(
        f"punctuation model load success, model: {config.PUNCT_MODEL}, "
        f"punctuations: {''.join(_id2punct)}"
    )

def _resolve_model_path() -> str:
    """返回 onnx 模型的本地路径，必要时从下载源拉取

    Returns:
        str: onnx 模型文件路径

    Raises:
        CustomException: 模型下载失败
    """
    # 本地目录：直接使用其中的 onnx 文件
    if os.path.isdir(config.PUNCT_MODEL):
        return _find_onnx(config.PUNCT_MODEL)

    logger.info(
        f"download punctuation model: {config.PUNCT_MODEL}, model_dir: {config.MODEL_DIR}"
    )

    try:
        os.makedirs(config.MODEL_DIR, exist_ok=True)
        from huggingface_hub import snapshot_download

        # 复用语音识别模型的缓存目录，首次启动下载后即被缓存
        local_dir = snapshot_download(
            repo_id=config.PUNCT_MODEL,
            cache_dir=config.MODEL_DIR,
            allow_patterns=[config.PUNCT_MODEL_FILE],
        )
    except Exception as e:
        logger.error(f"punctuation model download failed: {str(e)}")
        raise CustomException(
            err=CustomError.RECOGNIZE_AUDIO_FAILED,
            detail=f"punctuation model download failed: {str(e)}",
        )

    return _find_onnx(local_dir)

def _find_onnx(directory: str) -> str:
    """在目录中查找 onnx 模型文件

    Args:
        directory: 目录路径

    Returns:
        str: onnx 模型文件路径

    Raises:
        CustomException: 目录中没有 onnx 文件
    """
    expected = os.path.join(directory, config.PUNCT_MODEL_FILE)
    if os.path.isfile(expected):
        return expected

    for name in sorted(os.listdir(directory)):
        if name.endswith(".onnx"):
            return os.path.join(directory, name)

    raise CustomException(
        err=CustomError.RECOGNIZE_AUDIO_FAILED,
        detail=f"no onnx model found in {directory}",
    )

def _init_metadata(session: onnxruntime.InferenceSession) -> None:
    """从模型的元数据里读取标点表与词表

    该模型把 punctuations / tokens 存在 ONNX 的 metadata 中，因此无需额外的词表文件。

    Args:
        session: ONNX 推理会话
    """
    global _token2id, _id2punct, _unk_id, _unk_punct
    global _label_dot, _label_comma, _label_quest, _label_none

    meta = session.get_modelmeta().custom_metadata_map
    _id2punct = meta["punctuations"].split("|")
    punct2id = {p: i for i, p in enumerate(_id2punct)}

    tokens = meta["tokens"].split("|")
    _token2id = {t: i for i, t in enumerate(tokens)}
    _unk_id = _token2id[meta["unk_symbol"]]

    _label_none = punct2id[_NO_PUNCT]
    _unk_punct = punct2id[_UNK]
    _label_dot = punct2id["。"]
    _label_comma = punct2id["，"]
    _label_quest = punct2id["？"]

def restore(text: str) -> str:
    """给纯文本补标点

    Args:
        text: 待补标点的文本；已有的标点会被剔除，统一由模型重新决定

    Returns:
        str: 带标点的文本；未启用或模型未加载时原样返回

    Raises:
        CustomException: 标点恢复失败
    """
    if _session is None:
        return text

    # 逐字 tokenize：空白与标点不参与推理，词表外字符用 unk 占位
    ids = [
        _token2id.get(char, _unk_id)
        for char in text
        if not char.isspace() and char not in PUNCTUATIONS
    ]
    if not ids:
        return text

    try:
        labels = _predict(ids)
    except Exception as e:
        logger.error(f"punctuation restore failed: {str(e)}")
        raise CustomException(err=CustomError.RECOGNIZE_AUDIO_FAILED)

    # 按原字符回填：空白原样保留，原标点丢弃，模型给出的标点插在对应字之后
    parts = []
    index = 0
    for char in text:
        if char.isspace():
            parts.append(char)
            continue
        if char in PUNCTUATIONS:
            continue

        parts.append(char)
        if index < len(labels):
            label = labels[index]
            if label != _label_none and label != _unk_punct:
                parts.append(_id2punct[label])
        index += 1

    result = "".join(parts).rstrip()

    # 收尾兜底：模型偶尔在结尾不给标点，而接口要求 text 一定带标点
    if result and result[-1] not in PUNCTUATIONS:
        result += "。"

    return result

def _predict(ids: list[int]) -> list[int]:
    """对逐字 id 序列做标点预测

    模型按段推理，段内若找不到句末标点，就把这一段并入下一段（look back）继续找，
    直到超过 _MAX_LEN 才强制断句，避免出现超长的无标点文本。

    Args:
        ids: 逐字 token id

    Returns:
        list[int]: 与 ids 等长的标点标签
    """
    input_name = _session.get_inputs()[0].name
    length_name = _session.get_inputs()[1].name
    output_name = _session.get_outputs()[0].name

    num_segments = (len(ids) + _SEGMENT_SIZE - 1) // _SEGMENT_SIZE
    labels: list[int] = []
    start_of_segment = -1

    for i in range(num_segments):
        start = i * _SEGMENT_SIZE
        end = min(start + _SEGMENT_SIZE, len(ids))
        if start_of_segment != -1:
            start = start_of_segment

        inputs = ids[start:end]
        if not inputs:
            break

        output = _session.run(
            [output_name],
            {
                input_name: np.array(inputs, dtype=np.int32).reshape(1, -1),
                length_name: np.array([len(inputs)], dtype=np.int32),
            },
        )[0][0]
        predicted = output.argmax(axis=-1).tolist()

        # 从后往前找句末标点；同时记下最后一个逗号，供超长文本兜底
        dot_index = -1
        comma_index = -1
        for k in range(len(predicted) - 1, 1, -1):
            if predicted[k] in (_label_dot, _label_quest):
                dot_index = k
                break
            if comma_index == -1 and predicted[k] == _label_comma:
                comma_index = k

        if dot_index == -1 and len(inputs) >= _MAX_LEN and comma_index != -1:
            dot_index = comma_index
            predicted[dot_index] = _label_dot

        if dot_index == -1:
            # 这一段没有句末标点：并入下一段继续找；已是最后一段则收尾断句
            if start_of_segment == -1:
                start_of_segment = start
            if i == num_segments - 1:
                dot_index = len(inputs) - 1
        else:
            start_of_segment = start + dot_index + 1

        if dot_index != -1:
            labels += predicted[: dot_index + 1]

    return labels
