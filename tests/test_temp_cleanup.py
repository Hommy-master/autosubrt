"""临时目录清理：按年龄回收、不误删在途文件、启动清空与开关行为"""

import asyncio
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import cleanup
import config
import helper


CHUNK = b"x" * (256 * 1024)
CHUNK_COUNT = 4
CHUNK_INTERVAL = 0.4  # 秒，让下载耗时足够被周期清理“看到”


def make_file(path, size=1024, age_seconds=0):
    """创建一个文件，age_seconds > 0 时把 mtime 往前拨，模拟遗留文件"""
    with open(path, "wb") as f:
        f.write(b"x" * size)
    if age_seconds:
        stale = time.time() - age_seconds
        os.utime(path, (stale, stale))
    return path


class SlowHandler(BaseHTTPRequestHandler):
    """慢速下载服务器：分片之间留间隔，模拟还在下载中的文件"""

    def log_message(self, *args):
        pass

    def _headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(CHUNK) * CHUNK_COUNT))
        self.end_headers()

    def do_HEAD(self):
        self._headers()

    def do_GET(self):
        self._headers()
        for _ in range(CHUNK_COUNT):
            self.wfile.write(CHUNK)
            self.wfile.flush()
            time.sleep(CHUNK_INTERVAL)


@pytest.fixture
def slow_server():
    server = HTTPServer(("127.0.0.1", 0), SlowHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/slow.mp3"
    server.shutdown()


@pytest.fixture
def temp_dir(tmp_path, monkeypatch):
    """把清理目标指向测试目录，避免碰到仓库里的真实 temp/"""
    target = tmp_path / "temp"
    target.mkdir()
    monkeypatch.setattr(config, "TEMP_DIR", str(target))
    return target


def test_cleanup_dir_removes_only_expired_files(temp_dir):
    expired = make_file(temp_dir / "expired.mp3", age_seconds=7200)
    fresh = make_file(temp_dir / "fresh.mp3")

    removed, freed = helper.cleanup_dir(str(temp_dir), 3600)

    assert removed == 1
    assert freed == 1024
    assert not expired.exists()
    assert fresh.exists()


def test_cleanup_dir_keeps_dirs_links_and_hidden_files(temp_dir):
    """只删普通文件：子目录、符号链接、点开头的文件都不动"""
    # 链接目标保持“年轻”，这样它不会被年龄规则删掉，才能验证清理没有顺着链接删目标
    target = make_file(temp_dir / "target.mp3")
    hidden = make_file(temp_dir / ".hidden", age_seconds=7200)
    sub_dir = temp_dir / "subdir"
    sub_dir.mkdir()
    inner = make_file(sub_dir / "inner.mp3", age_seconds=7200)
    link = temp_dir / "link.mp3"
    os.symlink(target, link)
    stale = time.time() - 7200
    # 只改链接自身的时间（follow_symlinks=False），链接“超期”也不应被清理
    os.utime(link, (stale, stale), follow_symlinks=False)

    removed, _ = helper.cleanup_dir(str(temp_dir), 3600)

    assert removed == 0
    assert target.exists() and hidden.exists() and inner.exists()
    assert link.is_symlink()


def test_cleanup_dir_without_age_limit_clears_everything(temp_dir):
    make_file(temp_dir / "a.mp3")
    make_file(temp_dir / "b.mp3")

    removed, _ = helper.cleanup_dir(str(temp_dir), 0)

    assert removed == 2
    assert list(temp_dir.iterdir()) == []


def test_cleanup_dir_tolerates_missing_dir(tmp_path):
    assert helper.cleanup_dir(str(tmp_path / "not-exists")) == (0, 0)


def test_startup_cleanup_removes_leftovers(temp_dir, monkeypatch):
    """启动清理不看年龄：进程被强杀时残留的文件年龄可能只有几分钟"""
    leftover = make_file(temp_dir / "leftover.mp3", size=2048)
    monkeypatch.setattr(config, "TEMP_CLEAN_ON_START", True)
    monkeypatch.setattr(config, "CLEANUP_INTERVAL_SECONDS", 0)

    asyncio.run(cleanup.start())

    assert not leftover.exists()
    assert cleanup._task is None


def test_startup_cleanup_can_be_disabled(temp_dir, monkeypatch):
    leftover = make_file(temp_dir / "leftover.mp3")
    monkeypatch.setattr(config, "TEMP_CLEAN_ON_START", False)
    monkeypatch.setattr(config, "CLEANUP_INTERVAL_SECONDS", 0)

    asyncio.run(cleanup.start())

    assert leftover.exists()


def test_periodic_cleanup_removes_expired_files(temp_dir, monkeypatch):
    monkeypatch.setattr(config, "TEMP_CLEAN_ON_START", False)
    monkeypatch.setattr(config, "TEMP_RETENTION_SECONDS", 30)
    monkeypatch.setattr(config, "CLEANUP_INTERVAL_SECONDS", 1)

    async def run():
        await cleanup.start()
        stale = make_file(temp_dir / "stale.mp3", age_seconds=60)
        await asyncio.sleep(1.5)
        await cleanup.stop()
        return stale

    stale = asyncio.run(run())

    assert not stale.exists()
    assert cleanup._task is None


def test_cleanup_never_removes_inflight_download(temp_dir, slow_server, monkeypatch):
    """下载中的文件 mtime 被每个分片刷新，即使阈值远小于下载耗时也不会被误删"""
    monkeypatch.setattr(config, "TEMP_CLEAN_ON_START", False)
    monkeypatch.setattr(config, "TEMP_RETENTION_SECONDS", 1)
    monkeypatch.setattr(config, "CLEANUP_INTERVAL_SECONDS", 0.2)

    async def run():
        await cleanup.start()
        audio_file = await asyncio.to_thread(helper.download, slow_server, str(temp_dir))
        await cleanup.stop()
        return audio_file

    audio_file = asyncio.run(run())

    assert os.path.getsize(audio_file) == len(CHUNK) * CHUNK_COUNT
