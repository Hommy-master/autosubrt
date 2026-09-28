# 1. 项目介绍
实现语音转SRT格式字幕，提供HTTP接口；推荐使用python3.11运行。

语音识别引擎使用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)（CTranslate2 推理），
替代原有的 FunASR（paraformer-zh + ct-punc），接口的入参、出参和返回结构完全不变。

# 2. 输出SRT格式字幕
示例：
```
1
00:00:02,810 --> 00:00:03,330
多谢

2
00:00:04,889 --> 00:00:06,009
请入席吧

3
00:00:24,530 --> 00:00:25,730
曹操谢座

4
00:00:26,969 --> 00:00:27,510
列位

5
00:00:28,989 --> 00:00:33,465
请
```

# 3. 运行方法
1. 安装依赖
```
uv sync
```
2. 运行
```
uv run main.py
```

> 首次启动会自动下载语音识别模型（默认 `large-v3`，约 3GB）到模型目录，需要联网；
> 下载完成后会缓存到 `MODEL_DIR`，后续启动直接复用。容器部署时该目录已挂载到宿主机，不会丢失。

# 4. 接口列表

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/openapi/autosubrt/v1/asr/text` | 语音 -> 纯文本（自带标点） |
| POST | `/openapi/autosubrt/v1/asr/srt` | 语音 -> SRT 字幕文件 |
| POST | `/openapi/autosubrt/v1/asr/text/align` | 语音 + 文本 -> 对齐后的字幕时间线、字级时间线 |
| POST | `/openapi/autosubrt/v1/video/add_subtitles` | 为视频添加字幕 |
| GET | `/openapi/autosubrt/v1/health` | 健康检查 |

# 5. 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DOWNLOAD_URL` | `https://autosubrt.jcaigc.cn/` | 容器内文件路径转下载链接，本质是把 `/app/` 替换成该值 |
| `FILE_SIZE_LIMIT` | `104857600` | 下载文件大小限制（字节），默认 100MB |
| `MODEL_DIR` | 项目下的 `models` 目录 | 语音识别模型目录，首次启动自动下载到此处 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | 模型下载源；海外部署可改为 `https://huggingface.co` |
| `ASR_MODEL` | `large-v3` | 模型：`large-v3` / `large-v3-turbo` / `medium` / `small`，也可填本地模型路径 |
| `ASR_DEVICE` | `auto` | 推理设备：`auto` / `cpu` / `cuda`；`auto` 表示有 GPU 用 GPU，否则用 CPU |
| `ASR_COMPUTE_TYPE` | `auto` | 计算精度：`auto` / `int8` / `float16` / `float32`；`auto` 表示 GPU 用 float16、CPU 用 int8 |
| `ASR_LANGUAGE` | `zh` | 识别语言，`zh` 固定中文；置空表示自动检测语种 |
| `ASR_BEAM_SIZE` | `5` | 解码束宽，越大越准但越慢 |
| `ASR_VAD_FILTER` | `true` | 是否启用 VAD 静音过滤，可抑制空白音频上的幻觉文本 |
| `ASR_CPU_THREADS` | `0` | CPU 推理线程数，`0` 表示自动（容器内按 cgroup 的 CPU 配额）；建议与 `cpus` 配额保持一致 |

# 6. 部署注意事项

## 6.1 启动耗时
首次启动需要联网下载模型（`large-v3` 约 3GB），下载完成后仍需把模型加载进内存。
模型越大加载越久，请给容器留出足够长的启动/健康检查宽限期，避免被编排系统判定为启动失败。

如果启动耗时不可接受，可以预先在 `MODEL_DIR` 中放一份已经转换好的 CTranslate2 模型，
并把 `ASR_MODEL` 指向该目录的绝对路径，跳过每台机器各自的转换过程。

## 6.2 内存与 CPU
- `large-v3` 的 int8 模型约 1.5GB，CPU 推理需要预留内存；
  `docker-compose.yaml` 中已限制 8G 内存、3.5 个 CPU，并设置 `ASR_CPU_THREADS=3` 与之匹配。
- **线程数不要超过 CPU 配额**：线程数远超配额会加剧线程争抢，实测模型加载耗时可以从 67s 恶化到 173s
  （复现方式：16 核机器上分别用 `ASR_CPU_THREADS=4` 和默认值加载 `small` 模型）。
  `ASR_CPU_THREADS=0` 时容器内会按 cgroup 的 CPU 配额自动设置，跨环境迁移时建议显式指定。

## 6.3 GPU
`ASR_DEVICE=auto` 时如果机器上有 GPU 但容器内缺少 CUDA 运行库，模型虽然能加载成功，
但真正推理时会报 `Library cublas64_12.dll is not found`。程序会在启动阶段用一段静音做推理自检，
发现 GPU 不可用就自动回退到 CPU 并打印告警，不会出现「启动成功但每次识别都失败」的假健康状态。

## 6.4 多进程
`Dockerfile` 的启动命令里 `--workers 4` 目前不会被 `main.py` 解析（等价于单进程）。
如果需要多进程提升吞吐，请注意每个进程都会各自加载一份模型，内存成倍增长。
