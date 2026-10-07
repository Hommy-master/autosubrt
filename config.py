# 项目常量定义
import os


# 临时目录，用在缓存临时文件
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
# 语音识别模型目录，首次启动会自动下载模型到此处
MODEL_DIR = os.getenv("MODEL_DIR", os.path.join(os.path.dirname(__file__), "models"))

# 文件大小限制，默认为100MB (100 * 1024 * 1024 字节)
FILE_SIZE_LIMIT = int(os.getenv("FILE_SIZE_LIMIT", str(100 * 1024 * 1024)))

# ===== 并发限流配置 =====

# ASR 接口的最大并发请求数，超出后直接返回「服务器忙」，不排队。
# 单个请求的峰值内存与音频时长成正比（解码后的 float32 音频、VAD 的整段拷贝、逐段梅尔特征、
# 推理工作区），长音频下可到 1GB 量级，而模型本身还常驻约 1.5GB；FastAPI 的同步端点默认
# 最多 40 个线程并发，不限流时几个长音频同时进来就会顶到容器内存上限被 OOM 杀掉。
# 取值需结合 mem_limit 估算：MAX_CONCURRENCY × 单请求峰值 + 模型常驻 < mem_limit
# <= 0 表示不限流
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "6"))

# ===== 日志配置 =====

# 日志目录，默认项目下的 logs 目录；容器部署时该目录已挂载到宿主机，容器重建日志也不丢
LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.dirname(__file__), "logs"))
# 单个日志文件的大小上限（字节），默认 10MB，超过后轮转
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
# 轮转后保留的历史文件数量，默认 10 个（autosubrt.log.1 ~ autosubrt.log.10）
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "10"))

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

# ===== 磁盘清理配置 =====

# 正常情况下临时音频文件会在请求结束时删除，只有进程被强杀（OOM、重新部署）时才会残留。
# 残留文件再无任何引用，且年龄可能只有几分钟，因此启动时直接清空 temp 目录。
# 前提是 TEMP_DIR 为进程私有（当前单进程运行，且该目录不挂载到宿主机）；
# 若将来启用多 worker 或把该目录挂到共享卷，必须置为 false，否则会删掉其它进程在途的文件。
TEMP_CLEAN_ON_START = os.getenv("TEMP_CLEAN_ON_START", "true").strip().lower() == "true"
# 兜底清理：删除 temp 目录中超过该时长（秒）没有更新的文件。该值需远大于单个请求的
# 文件存活时长（下载超时 90s × 重试 + 音频解码），且下载中的文件 mtime 会被持续刷新，
# 因此不会误删在途文件；<= 0 表示关闭周期清理
TEMP_RETENTION_SECONDS = int(os.getenv("TEMP_RETENTION_SECONDS", str(6 * 3600)))
# 周期清理的执行间隔（秒），<= 0 表示不启动后台清理任务
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", str(30 * 60)))

# ===== 计费（积分）配置 =====

# 是否启用 apiKey 校验与计费：开启后所有 ASR 接口必须传 apiKey 并按音频时长扣费；
# 关闭则接口无需 apiKey、不扣费（行为与计费功能上线前一致）
# 注意：只认 "true"，写 ENABLE_APIKEY=1 会被当成 false（与 capcut-mate 保持一致）
ENABLE_APIKEY = os.getenv("ENABLE_APIKEY", "true").strip().lower() == "true"
# 计费单价：积分/秒
POINTS_PER_SECOND = float(os.getenv("POINTS_PER_SECOND", "0.00022"))
