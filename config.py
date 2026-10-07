# 项目常量定义
import os


# 临时目录，用在缓存临时文件
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
SRT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "srt")
# 语音识别模型目录，首次启动会自动下载模型到此处
MODEL_DIR = os.getenv("MODEL_DIR", os.path.join(os.path.dirname(__file__), "models"))

# 将容器内的文件路径转成一个下载路径，执行替换操作，即将/app/ -> https://autosubrt.jcaigc.cn/
DOWNLOAD_URL = os.getenv("DOWNLOAD_URL", "https://autosubrt.jcaigc.cn/")

# 文件大小限制，默认为100MB (100 * 1024 * 1024 字节)
FILE_SIZE_LIMIT = int(os.getenv("FILE_SIZE_LIMIT", str(100 * 1024 * 1024)))

# ===== 语音识别（faster-whisper）配置 =====

# 模型下载源，默认使用国内镜像 hf-mirror，部署在海外时可改为 https://huggingface.co
# 该环境变量必须在导入 huggingface_hub 之前设置，因此统一放在 config 中处理
os.environ.setdefault("HF_ENDPOINT", os.getenv("HF_ENDPOINT", "https://hf-mirror.com"))

# Xet 传输协议（hf_xet）不受 HF_ENDPOINT 影响：元数据从下载源获取，块数据却要直连
# cas-server.xethub.hf.co，镜像拿到的是匿名令牌，该服务会直接返回 401 Unauthorized。
# Xet 只覆盖部分大文件（large-v3 的 model.bin、标点模型的 model.onnx），症状是
# 「小文件能下、大文件 401、服务启动失败」，因此非官方源一律关闭，回退到下载源支持的
# 普通 HTTP 下载（resolve 302 到带签名的直链，无需令牌）；直连官方源时保留 Xet 以享受
# 分块去重。同样必须在导入 huggingface_hub 之前设置，可用 HF_HUB_DISABLE_XET 显式覆盖
if "HF_HUB_DISABLE_XET" not in os.environ:
    os.environ["HF_HUB_DISABLE_XET"] = (
        "0" if "huggingface.co" in os.environ["HF_ENDPOINT"] else "1"
    )

# 模型名称或本地模型路径，可选：large-v3 / large-v3-turbo / medium / small
ASR_MODEL = os.getenv("ASR_MODEL", "large-v3")
# 推理设备：auto / cpu / cuda，auto 表示有 GPU 用 GPU，否则用 CPU
ASR_DEVICE = os.getenv("ASR_DEVICE", "auto")
# 计算精度：auto / int8 / float16 / float32，auto 表示 GPU 用 float16、CPU 用 int8
ASR_COMPUTE_TYPE = os.getenv("ASR_COMPUTE_TYPE", "auto")
# 识别语言，zh 表示固定中文（与原 paraformer-zh 模型行为一致），置空表示自动检测语种
ASR_LANGUAGE = os.getenv("ASR_LANGUAGE", "zh")
# 解码束宽，值越大越准确但越慢
ASR_BEAM_SIZE = int(os.getenv("ASR_BEAM_SIZE", "5"))
# 是否启用 VAD 静音过滤，可有效抑制空白音频上产生的幻觉文本
ASR_VAD_FILTER = os.getenv("ASR_VAD_FILTER", "true").lower() in ("1", "true", "yes", "on")
# CPU 推理线程数，0 表示自动（容器内按 cgroup 的 CPU 配额，否则交给 CTranslate2 自行决定）；
# 线程数远超 CPU 配额会加剧线程争抢，反而拖慢模型加载，容器内建议显式设置
ASR_CPU_THREADS = int(os.getenv("ASR_CPU_THREADS", "0"))

# ===== 标点恢复（ct-punc ONNX）配置 =====

# 是否启用标点恢复。whisper 对中文标点不可靠，开启后识别文本会统一过一遍标点模型，
# 保证接口输出的 text 一定带标点；置为 false 则直接返回 whisper 自带的标点
PUNCT_ENABLED = os.getenv("PUNCT_ENABLED", "true").lower() in ("1", "true", "yes", "on")
# 标点模型：下载源上的仓库名，或本地模型目录
PUNCT_MODEL = os.getenv(
    "PUNCT_MODEL", "csukuangfj/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12"
)
# 标点模型文件名（本地目录里也按该名字查找）
PUNCT_MODEL_FILE = os.getenv("PUNCT_MODEL_FILE", "model.onnx")
# ONNX 推理线程数，0 表示自动（容器内按 cgroup 的 CPU 配额）
PUNCT_CPU_THREADS = int(os.getenv("PUNCT_CPU_THREADS", "0"))

# ===== 计费（积分）配置 =====

# 是否启用 apiKey 校验与计费：开启后所有 ASR 接口必须传 apiKey 并按音频时长扣费；
# 关闭则接口无需 apiKey、不扣费（行为与计费功能上线前一致）
# 注意：只认 "true"，写 ENABLE_APIKEY=1 会被当成 false（与 capcut-mate 保持一致）
ENABLE_APIKEY = os.getenv("ENABLE_APIKEY", "true").strip().lower() == "true"
# 计费单价：积分/秒
POINTS_PER_SECOND = float(os.getenv("POINTS_PER_SECOND", "0.00022"))
