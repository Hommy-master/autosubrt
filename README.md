# 1. 项目介绍
实现语音转SRT格式字幕，提供HTTP接口；推荐使用python3.11运行。

语音识别引擎使用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)（CTranslate2 推理），
替代原有的 FunASR（paraformer-zh + ct-punc），识别结果的结构不变。

> **计费**：所有 ASR 接口需要传入 `apiKey` 并按音频时长扣费，详见 [4.2 计费](#42-计费)。
> 升级时若不希望开启，设置环境变量 `ENABLE_APIKEY=false` 即可恢复为无校验、不扣费的行为。

标点由独立的 [ct-punc](https://modelscope.cn/models/iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch)
（CT-Transformer，ONNX 推理）恢复：whisper 对中文标点不可靠，短音频可能整段没有标点，
因此识别文本会统一过一遍标点模型，**保证接口输出的 `text` 一定带标点**，
分句（`utterances[].text`）同样带标点。

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
3. 运行测试
```
uv run pytest tests -q
```

> 首次启动会自动下载语音识别模型（默认 `large-v3`，约 3GB）和标点模型（ct-punc，约 295MB）到模型目录，
> 需要联网；下载完成后会缓存到 `MODEL_DIR`，后续启动直接复用。
> 容器部署时该目录已挂载到宿主机，不会丢失。

# 4. 接口列表

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/openapi/autosubrt/v1/asr` | 语音 -> 完整文案 + 分句及逐字时间线 |
| POST | `/openapi/autosubrt/v1/asr/text` | 语音 -> 纯文本（自带标点） |
| POST | `/openapi/autosubrt/v1/asr/srt` | 语音 -> SRT 字幕文件（**直接返回文件本体**，见 4.3） |
| POST | `/openapi/autosubrt/v1/asr/text/align` | 语音 + 文本 -> 对齐后的字幕时间线、字级时间线 |
| GET | `/openapi/autosubrt/v1/health` | 健康检查 |

所有 ASR 接口的请求体都可以带一个可选的 `apiKey` 字段（开启计费时必填），例如：

```json
{ "audio_url": "http://example.com/audio.wav", "apiKey": "3f2504e0-4f89-11d3-9a0c-0305e82c3301" }
```

## 4.1 `POST /openapi/autosubrt/v1/asr`

请求：

```json
{ "audio_url": "http://example.com/audio.wav", "apiKey": "3f2504e0-4f89-11d3-9a0c-0305e82c3301" }
```

响应（时间为毫秒）：

```json
{
  "code": 0,
  "message": "成功",
  "data": {
    "text": "你们应该都听过啊，羊毛羊绒当中的软黄金。",
    "utterances": [
      {
        "text": "你们应该都听过啊，",
        "words": [
          { "text": "你", "start_time": 280, "end_time": 400 },
          { "text": "们", "start_time": 400, "end_time": 520 }
        ]
      }
    ]
  }
}
```

说明：

- `data.text` 是完整文案；`data.utterances[].text` 是分句文本，**标点同样计入** `text`（与 `data.text` 出自同一次标点恢复，标点随所属句子走）。
- 其 `words[]` 为该句每个字的时间线，**只包含真实的字，不含标点**；标点没有时间戳。
- 分句规则：**标点优先**，遇到 `。！？，；.!?,;:` 断句；无标点时**静音兜底**，相邻两字间隔超过 500ms 即断句。
- `utterances` 各句按顺序拼接后与 `data.text` **逐字完全一致**（`"".join(u.text) == data.text`）。
- 由静音兜底断出的句子可能没有结尾标点，因为该处标点模型本就没有给出标点；此时**不会**人为补标点，以保证上一条的拼接一致性。
- 响应外层 `{code, message, data}` 为全局统一封装，与其它接口一致。

## 4.2 计费

开启后（默认开启）所有 ASR 接口都要传 `apiKey`，并按音频时长扣费，与兄弟服务 capcut-mate 共用同一套积分体系。

| 项 | 说明 |
| --- | --- |
| 单价 | **0.00022 积分/秒** |
| 计费依据 | 音频实际时长（秒），由识别引擎给出 |
| 扣费时机 | 识别**成功之后**才扣费；识别失败不扣费 |
| 计费接口 | `/asr`、`/asr/text`、`/asr/srt`、`/asr/text/align`（`/health` 不计费） |
| 余额门槛 | 调用前要求账户积分**大于 1**，否则直接拒绝 |

费用 = 时长（秒）× 0.00022，保留 6 位小数，例如：

| 音频时长 | 费用（积分） |
| --- | --- |
| 10 秒 | 0.002200 |
| 60 秒 | 0.013200 |
| 1 小时 | 0.792000 |

`apiKey` 必须是合法 UUID，可登录官网 <https://jcaigc.cn> 获取。

错误码：

| 错误码 | 含义 |
| --- | --- |
| `1001` | apiKey 不是合法 UUID（参数校验失败） |
| `2035` | 账户余额不足（调用前积分需大于 1） |
| `2036` | 未传 apiKey |

说明：

- **apiKey 格式校验与 `ENABLE_APIKEY` 开关无关**：关闭计费时传入非法格式的 apiKey 依然会返回 `1001`。
- **扣费失败不会让请求失败**：识别结果照常返回，扣费失败只记录日志（如积分服务临时不可用）。
- **不区分重试**：同一段音频重复调用会重复扣费，客户端请勿在超时后盲目重试。
- **`ENABLE_APIKEY` 只认 `true`**：写成 `ENABLE_APIKEY=1` 会被当成 `false` 从而**关闭计费**，服务启动日志里会打印生效值，请留意。

## 4.3 `POST /openapi/autosubrt/v1/asr/srt` 的返回形式

请求体同其它接口，但**响应不再是一个 JSON 里的下载链接，而是 SRT 文件本体**（服务端不落盘，
不产生任何需要清理的静态文件），调用方按文件保存即可：

```
HTTP/1.1 200 OK
Content-Type: application/x-subrip; charset=utf-8
Content-Disposition: attachment; filename="subtitle.srt"

1
00:00:02,810 --> 00:00:03,330
多谢
...
```

说明：

- 文件内容为 **UTF-8 编码的 SRT**，行尾为 `\n`。
- **失败时仍返回统一的 JSON 错误体**（`{code, message}`，HTTP 200），因此调用方需要按
  `Content-Type` 区分：`application/x-subrip` 是字幕文件，`application/json` 是错误。
- 该改动是**破坏性变更**：旧版本返回 `data.srt_url`（一个静态文件链接），消费方需同步调整。
- 单次请求的音频临时文件仍在请求结束时删除，与之前的其它接口一致。

# 5. 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FILE_SIZE_LIMIT` | `104857600` | 下载文件大小限制（字节），默认 100MB |
| `LOG_DIR` | 项目下的 `logs` 目录 | 日志目录；容器内为 `/app/logs`，已挂载到宿主机，详见 7.6 |
| `LOG_MAX_BYTES` | `10485760` | 单个日志文件的大小上限（字节），默认 10MB，超过后轮转 |
| `LOG_BACKUP_COUNT` | `10` | 轮转后保留的历史日志文件数量 |
| `MODEL_DIR` | 项目下的 `models` 目录 | 语音识别模型目录，首次启动自动下载到此处 |
| `TEMP_CLEAN_ON_START` | `true` | 启动时清空临时目录，回收上次进程被强杀时残留的音频文件；仅当临时目录为进程私有（单进程、未挂载）时可开启，详见 7.5 |
| `TEMP_RETENTION_SECONDS` | `21600` | 兜底清理：删除临时目录中超过该时长（秒）未更新的文件；`0` 表示关闭 |
| `CLEANUP_INTERVAL_SECONDS` | `1800` | 后台清理任务的执行间隔（秒）；`0` 表示不启动该任务 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | 模型下载源；海外部署可改为 `https://huggingface.co` |
| `HF_HUB_DISABLE_XET` | 非官方源为 `1`，官方源为 `0` | 是否启用 Xet 传输协议。Xet 不受 `HF_ENDPOINT` 影响，块数据要直连 `cas-server.xethub.hf.co`，用镜像时会被拒（401）导致大文件下载失败，因此非官方源下自动关闭 |
| `ASR_MODEL` | `large-v3` | 模型：`large-v3` / `large-v3-turbo` / `medium` / `small`，也可填本地模型路径 |
| `ASR_DEVICE` | `auto` | 推理设备：`auto` / `cpu` / `cuda`；`auto` 表示有 GPU 用 GPU，否则用 CPU |
| `ASR_COMPUTE_TYPE` | `auto` | 计算精度：`auto` / `int8` / `float16` / `float32`；`auto` 表示 GPU 用 float16、CPU 用 int8 |
| `ASR_LANGUAGE` | `zh` | 识别语言，`zh` 固定中文；置空表示自动检测语种 |
| `ASR_BEAM_SIZE` | `5` | 解码束宽，越大越准但越慢 |
| `ASR_VAD_FILTER` | `true` | 是否启用 VAD 静音过滤，可抑制空白音频上的幻觉文本 |
| `ASR_CPU_THREADS` | `0` | CPU 推理线程数，`0` 表示自动（容器内按 cgroup 的 CPU 配额）；建议与 `cpus` 配额保持一致 |
| `PUNCT_ENABLED` | `true` | 是否启用标点恢复；关闭后直接返回 whisper 自带的标点（不保证有标点） |
| `PUNCT_MODEL` | `csukuangfj/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12` | 标点模型：下载源上的仓库名，或本地模型目录；默认约 295MB |
| `PUNCT_MODEL_FILE` | `model.onnx` | 标点模型文件名（本地目录里也按该名字查找） |
| `PUNCT_CPU_THREADS` | `0` | 标点模型的 ONNX 推理线程数，`0` 表示自动（容器内按 cgroup 的 CPU 配额） |
| `ENABLE_APIKEY` | `true` | 是否启用 apiKey 校验与计费；置 `false` 则无需 apiKey、不扣费。**只认 `true`/`false`**，写 `1` 会被当成 `false` |
| `POINTS_PER_SECOND` | `0.00022` | 计费单价（积分/秒） |

# 6. 标点恢复说明

- **只插入标点，绝不改动原字符**：输入里已有的标点会先被剔除，再统一由标点模型决定，
  不会出现重复标点；数字、`~`、大写字母等模型词表外的字符原样保留。
- 模型可输出 `，` `。` `？` `、` 四种标点，与分句逻辑共用同一套标点表。
- **`data.text` 只补一次标点**：分句时按字区间把这份带标点的文案切开，而不是每句各自再跑一次模型
  （每句单独跑会丢掉上下文，标点质量更差），因此各句拼接与 `data.text` 逐字完全一致。
- 模型按 20 字一段推理；段内找不到句末标点时向后累积，超过 200 字才强制断句。
- 已知局限：模型按词表判断，偶尔会在词组中间断句（例如把「保暖性」断成「保暖。性」）。

# 7. 部署注意事项

## 7.1 启动耗时
**Python 依赖已全部打进镜像，启动阶段不会联网安装任何依赖**：构建时用 `uv sync --no-dev` 装好，
启动命令直接用镜像内 `.venv` 的 `python`（不再走 `uv run`——它会隐式执行一次 `uv sync`，
且默认带上 dev 组去 PyPI 补装 `pytest` 等依赖，导致每次启动都要联网、在国内网络下长时间卡在下载）。
启动阶段唯一需要联网的是**首次下载模型**（`large-v3` 约 3GB），下载完成后仍需把模型加载进内存。
模型越大加载越久，请给容器留出足够长的启动/健康检查宽限期，避免被编排系统判定为启动失败。

如果启动耗时不可接受，可以预先在 `MODEL_DIR` 中放一份已经转换好的 CTranslate2 模型，
并把 `ASR_MODEL` 指向该目录的绝对路径，跳过每台机器各自的转换过程。

## 7.2 内存与 CPU
- `large-v3` 的 int8 模型约 1.5GB，CPU 推理需要预留内存；
  `docker-compose.yaml` 中已限制 8G 内存、3.5 个 CPU，并设置 `ASR_CPU_THREADS=3` 与之匹配。
- **线程数不要超过 CPU 配额**：线程数远超配额会加剧线程争抢，实测模型加载耗时可以从 67s 恶化到 173s
  （复现方式：16 核机器上分别用 `ASR_CPU_THREADS=4` 和默认值加载 `small` 模型）。
  `ASR_CPU_THREADS=0` 时容器内会按 cgroup 的 CPU 配额自动设置，跨环境迁移时建议显式指定。

## 7.3 GPU
`ASR_DEVICE=auto` 时如果机器上有 GPU 但容器内缺少 CUDA 运行库，模型虽然能加载成功，
但真正推理时会报 `Library cublas64_12.dll is not found`。程序会在启动阶段用一段静音做推理自检，
发现 GPU 不可用就自动回退到 CPU 并打印告警，不会出现「启动成功但每次识别都失败」的假健康状态。

## 7.4 多进程
`Dockerfile` 的启动命令里 `--workers 4` 目前不会被 `main.py` 解析（等价于单进程）。
如果需要多进程提升吞吐，请注意每个进程都会各自加载一份模型，内存成倍增长。

## 7.5 磁盘清理
服务只在请求处理期间把音频下载到 `TEMP_DIR`（`temp/` 目录），并在请求结束时（含各种失败路径）删除。
但进程被强杀时 `finally` 不会执行，文件会留在磁盘上再无引用，因此还有两道兜底：

| 时机 | 行为 |
| --- | --- |
| 启动时 | `TEMP_CLEAN_ON_START=true` 时清空整个 `temp/` 目录（此时没有请求在跑，残留一定是上一个进程的） |
| 运行期 | 每 `CLEANUP_INTERVAL_SECONDS` 清理一次，删除 `temp/` 中超过 `TEMP_RETENTION_SECONDS` 没有更新的文件 |

说明：

- 正在下载的文件每收到一个分片就会刷新 mtime，清理阈值又远大于单个请求的文件存活时长，
  因此**不会误删正在处理的请求**；清理只针对普通文件，不递归子目录、不动符号链接。
- **`temp/` 必须是进程私有目录**：如果将来启用多 worker，或把 `TEMP_DIR` 挂载到多个容器共享的卷，
  每个进程启动时都会删掉别人在途的文件，此时必须设置 `TEMP_CLEAN_ON_START=false`（周期清理可以保留）。
- `temp/` 位于容器可写层（未挂载到宿主机），除日志（见 7.6）外服务不往宿主机写任何文件；
  compose 中原先挂载站点 `output` 目录的配置已随之移除，宿主机上历史遗留的 SRT 文件不再被覆盖，可自行清理。

## 7.6 日志

日志**同时写 stdout 和文件**，文件默认落在 `logs/` 目录（容器内 `/app/logs`，由 `LOG_DIR` 控制）。
单个文件超过 `LOG_MAX_BYTES`（默认 10MB）后轮转为 `autosubrt.log.1`，
最多保留 `LOG_BACKUP_COUNT`（默认 10）个历史文件，即总量上限约 110MB。

- 文件日志由 `logger.py` 里的 `RotatingFileHandler` 输出，格式与 `docker logs` 完全一致。
- uvicorn 的启动与访问日志同样落盘：`uvicorn.run(..., log_config=None)` 不让 uvicorn 用自带配置
  覆盖 `logger.py` 中的 handler，否则这些日志只会打在 stdout 上。
- `docker-compose.yaml` 把 `./logs` 挂载到 `/app/logs`，宿主机可直接 `tail -f logs/autosubrt.log`，
  容器重建（`docker compose down` 后再 `up`）日志也不丢；去掉该挂载则日志只存在于容器内。
- `docker-compose.yaml` 里容器标准输出（json-file）也做了轮转（`max-size=10m, max-file=3`），
  避免 json-file 日志无限增长。注意该轮转会**删除**旧的 `docker logs`，需要长期保留请看日志文件。
- **多进程下日志文件会有轮转竞争**（每个进程各自轮转同一个文件），将来启用多 worker 时需另行处理，详见 7.4。
