"""/asr/srt 直接返回 SRT 文件本体，服务端不产生任何需要清理的文件"""

import io

import pysrt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import asr
import middlewares
import router
import service
from exceptions import CustomError, CustomException


VALID_KEY = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
REQUEST_BODY = {"audio_url": "http://example.com/audio.wav", "apiKey": VALID_KEY}

# 每个字的时间戳（毫秒），间隔都小于断句阈值 250ms，因此会合成一个 SRT 条目
CHARS_TIMESTAMPS = [[280, 400], [400, 520], [600, 720], [720, 840], [840, 960], [960, 1080]]
EXPECTED_SRT_TIME = "00:00:00,280 --> 00:00:01,080"


def build_subs() -> pysrt.SubRipFile:
    """构造一份含中文的 SRT，用于验证渲染结果"""
    subs = pysrt.SubRipFile()
    subs.append(
        pysrt.SubRipItem(
            index=1,
            start=pysrt.SubRipTime(milliseconds=280),
            end=pysrt.SubRipTime(milliseconds=1080),
            text="多谢请入席吧",
        )
    )
    return subs


@pytest.fixture
def client() -> TestClient:
    """不带 lifespan 的应用（避免测试时加载模型），中间件与 main.py 保持一致"""
    app = FastAPI()
    app.include_router(router.router, prefix="/openapi/autosubrt")
    app.add_middleware(middlewares.PrepareMiddleware)
    app.add_middleware(middlewares.ResponseMiddleware)
    return TestClient(app)


def test_rendered_srt_matches_file_output(tmp_path):
    """不落盘的渲染结果与旧版 subs.save() 写出的文件逐字节一致"""
    subs = build_subs()

    legacy_file = tmp_path / "legacy.srt"
    subs.save(str(legacy_file))

    buffer = io.StringIO()
    subs.write_into(buffer)

    assert buffer.getvalue().encode("utf-8") == legacy_file.read_bytes()


def test_process_audio_to_srt_returns_text_without_writing_file(tmp_path, monkeypatch):
    """process_audio_to_srt 返回 (SRT 文本, 时长)，且不再需要文件路径、不落盘"""
    result = asr.RecognitionResult(
        text="多谢请入席吧",
        chars=list("多谢请入席吧"),
        timestamps=CHARS_TIMESTAMPS,
        duration=12.5,
    )
    monkeypatch.setattr(service.asr, "transcribe", lambda audio_path: result)
    # 在空目录里执行：若函数偷偷落盘，下面的断言会立刻失败
    monkeypatch.chdir(tmp_path)

    srt_text, duration = service.process_audio_to_srt("/tmp/not-exists.wav")

    assert duration == 12.5
    assert EXPECTED_SRT_TIME in srt_text
    assert "多谢请入席吧" in srt_text
    assert list(tmp_path.iterdir()) == []


def test_endpoint_returns_srt_file(client, monkeypatch):
    """接口返回文件本体（媒体类型、文件名、内容），而不是 JSON 里的下载链接"""
    srt_text = "1\n00:00:00,280 --> 00:00:01,080\n多谢请入席吧\n"
    monkeypatch.setattr(service, "asr_srt", lambda audio_url, api_key=None: srt_text)

    response = client.post("/openapi/autosubrt/v1/asr/srt", json=REQUEST_BODY)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-subrip")
    assert response.headers["content-disposition"] == 'attachment; filename="subtitle.srt"'
    assert response.content == srt_text.encode("utf-8")


def test_endpoint_returns_json_error_on_failure(client, monkeypatch):
    """失败时仍返回统一的 JSON 错误体，调用方按 Content-Type 区分"""

    def raise_error(audio_url, api_key=None):
        raise CustomException(err=CustomError.RECOGNIZE_AUDIO_FAILED)

    monkeypatch.setattr(service, "asr_srt", raise_error)

    response = client.post("/openapi/autosubrt/v1/asr/srt", json=REQUEST_BODY)

    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["code"] == CustomError.RECOGNIZE_AUDIO_FAILED.code


def test_other_endpoints_keep_json_wrapper(client, monkeypatch):
    """其它接口仍是 {code, message, data} 的 JSON 封装"""
    monkeypatch.setattr(service, "asr_text", lambda audio_url, api_key=None: "纯文本")

    response = client.post("/openapi/autosubrt/v1/asr/text", json=REQUEST_BODY)

    body = response.json()
    assert body["code"] == 0
    assert body["data"] == {"text": "纯文本"}
