# 项目常量定义
import os


# 临时目录，用在缓存临时文件
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
VIDEO_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "video")
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
