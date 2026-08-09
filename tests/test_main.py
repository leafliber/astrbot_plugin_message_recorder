"""消息监听与事件生命周期相关测试。"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from astrbot_plugin_message_recorder.main import MessageRecorder
from astrbot_plugin_message_recorder.message_recorder.media_downloader import (
    MediaDownloader,
)


class Image:
    """只提供序列化与下载所需字段的图片组件。"""

    def __init__(self, file: str, url: str, path: str):
        self.file = file
        self.url = url
        self.path = path


class _BlockingDatabase:
    """让数据库写入停在后台，以便模拟事件结束后的临时文件清理。"""

    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.records = []

    async def save_message(self, record):
        self.started.set()
        await self.release.wait()
        self.records.append(record)
        return 1


def _make_recorder(tmp_path) -> tuple[MessageRecorder, _BlockingDatabase]:
    recorder = MessageRecorder.__new__(MessageRecorder)
    recorder.config = {
        "save_message_chain": True,
        "save_media_files": True,
        "save_raw_message": False,
    }
    recorder._initialized = True
    recorder._init_error = None
    recorder._pending_tasks = set()
    recorder._save_semaphore = asyncio.Semaphore(8)
    recorder._download_semaphore = asyncio.Semaphore(4)
    recorder._db = _BlockingDatabase()

    with patch(
        "astrbot_plugin_message_recorder.message_recorder.media_downloader."
        "get_astrbot_plugin_data_path",
        return_value=str(tmp_path / "plugin-data"),
    ):
        recorder._media_downloader = MediaDownloader(
            "astrbot_plugin_message_recorder",
            max_retries=0,
        )

    async def read_local_media(media_ref, _component_type):
        return await asyncio.to_thread(Path(media_ref).read_bytes)

    recorder._media_downloader._fetch_via_media_resolver = AsyncMock(
        side_effect=read_local_media
    )

    return recorder, recorder._db


async def test_on_message_persists_temp_media_before_background_save(tmp_path):
    """handler 返回后源文件即使被 AstrBot 删除，后台保存仍使用持久副本。"""
    recorder, database = _make_recorder(tmp_path)
    temp_image = tmp_path / "media_image_event_owned.jpg"
    temp_image.write_bytes(b"event-owned-image")

    component = Image(
        file=str(temp_image),
        url=str(temp_image),
        path=str(temp_image),
    )
    message_obj = SimpleNamespace(
        timestamp=1_754_730_000_000,
        sender=SimpleNamespace(user_id="user-1", nickname="Tester"),
        group_id="group-1",
        message_id="message-1",
        session_id="session-1",
        message=[component],
        raw_message=None,
        type=None,
    )
    event = SimpleNamespace(
        message_obj=message_obj,
        message_str="[图片]",
        get_platform_name=lambda: "aiocqhttp",
    )

    await recorder.on_message(event)

    # 模拟 PipelineScheduler 在 handler 返回后清理事件所属临时文件。
    temp_image.unlink()
    await database.started.wait()
    database.release.set()
    await asyncio.gather(*recorder._pending_tasks)

    assert len(database.records) == 1
    chain = json.loads(database.records[0].message_chain)
    local_path = chain[0]["local_path"]
    persisted_path = recorder._media_downloader.get_media_base_path() / local_path
    assert persisted_path.read_bytes() == b"event-owned-image"
