"""并发限流：名额用满即拒绝、异常路径也归还名额、不限流时的行为"""

import threading

import pytest
from fastapi.testclient import TestClient

import concurrency
import main
import service
from exceptions import CustomError, CustomException


@pytest.fixture
def limit_to(monkeypatch):
    """把并发上限替换成指定值，避免依赖 config.MAX_CONCURRENCY 的默认值"""
    def _apply(count):
        monkeypatch.setattr(concurrency, "_semaphore", threading.Semaphore(count))
    return _apply


def test_allow_exactly_limit_number_of_concurrent_requests(limit_to):
    limit_to(2)

    with concurrency.limit():
        with concurrency.limit():
            pass  # 第 2 个名额仍可拿到


def test_reject_request_over_limit(limit_to):
    limit_to(2)

    with concurrency.limit():
        with concurrency.limit():
            with pytest.raises(CustomException) as excinfo:
                with concurrency.limit():
                    pass

    assert excinfo.value.err is CustomError.SERVER_BUSY
    assert excinfo.value.err.code == 9997


def test_release_slot_when_business_raises(limit_to):
    limit_to(1)

    with pytest.raises(ValueError):
        with concurrency.limit():
            raise ValueError("业务异常")

    # 名额已归还：同样的上限下还能再次拿到
    with concurrency.limit():
        pass


def test_no_limit_when_disabled(monkeypatch):
    monkeypatch.setattr(concurrency, "_semaphore", None)

    # 不限流时嵌套任意层都不会被拒绝
    with concurrency.limit():
        with concurrency.limit():
            with concurrency.limit():
                pass


@pytest.fixture
def client(monkeypatch):
    """不进入 TestClient 上下文，避免触发生命周期去加载模型

    识别逻辑整体替换掉，测的是「限流拒绝发生在业务之前、且不返回业务错误」。
    """
    monkeypatch.setattr(service, "asr_text", lambda audio_url, api_key=None: "识别结果")
    return TestClient(main.app)


def test_endpoint_returns_busy_when_all_slots_taken(limit_to, client, monkeypatch):
    limit_to(1)
    payload = {"audio_url": "https://example.com/a.mp3"}

    # 名额被占满时：直接返回「服务器忙」，而不是入队等待或识别失败
    with concurrency.limit():
        resp = client.post("/openapi/autosubrt/v1/asr/text", json=payload)

    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == CustomError.SERVER_BUSY.code
    assert body["message"] == CustomError.SERVER_BUSY.cn_message


def test_endpoint_works_after_slot_released(limit_to, client):
    limit_to(1)

    resp = client.post(
        "/openapi/autosubrt/v1/asr/text", json={"audio_url": "https://example.com/a.mp3"}
    )

    body = resp.json()
    assert body["code"] == CustomError.SUCCESS.code
    assert body["data"]["text"] == "识别结果"
