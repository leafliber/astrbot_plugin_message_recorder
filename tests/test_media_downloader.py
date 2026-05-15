"""media_downloader.py 单元测试"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from astrbot_plugin_message_recorder.media_downloader import (
    MediaDownloader,
    MEDIA_TYPE_MAP,
)


class TestMediaTypeMap:
    def test_all_types(self):
        assert "Image" in MEDIA_TYPE_MAP
        assert "Record" in MEDIA_TYPE_MAP
        assert "Video" in MEDIA_TYPE_MAP
        assert "File" in MEDIA_TYPE_MAP

    def test_values_are_directories(self):
        for v in MEDIA_TYPE_MAP.values():
            assert isinstance(v, str)
            assert len(v) > 0


class TestMediaDownloaderInit:
    def test_init(self, tmp_path):
        with patch(
            "astrbot_plugin_message_recorder.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            md = MediaDownloader("test_plugin")
            assert md.media_base_path == tmp_path / "test_plugin" / "media"
            assert md.max_retries == 2
            assert md.retry_delay == 1.0


class TestExtractMediaPaths:
    def test_delegates_to_serializer(self):
        chain = json.dumps([{"type": "Image", "local_path": "images/test.jpg"}])
        result = MediaDownloader.extract_media_paths(chain)
        assert "images/test.jpg" in result

    def test_none_input(self):
        assert MediaDownloader.extract_media_paths(None) == []

    def test_empty_string(self):
        assert MediaDownloader.extract_media_paths("") == []


class TestDeleteMediaFile:
    def test_delete_existing(self, tmp_path):
        with patch(
            "astrbot_plugin_message_recorder.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            md = MediaDownloader("test_plugin")
            test_file = tmp_path / "test_plugin" / "media" / "images" / "test.jpg"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("fake image")

            assert md.delete_media_file("images/test.jpg") is True
            assert not test_file.exists()

    def test_delete_nonexistent(self, tmp_path):
        with patch(
            "astrbot_plugin_message_recorder.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            md = MediaDownloader("test_plugin")
            assert md.delete_media_file("images/nonexistent.jpg") is False

    def test_delete_empty_path(self, tmp_path):
        with patch(
            "astrbot_plugin_message_recorder.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            md = MediaDownloader("test_plugin")
            assert md.delete_media_file("") is False


class TestDeleteMediaFiles:
    def test_delete_multiple(self, tmp_path):
        with patch(
            "astrbot_plugin_message_recorder.media_downloader.get_astrbot_plugin_data_path",
            return_value=str(tmp_path),
        ):
            md = MediaDownloader("test_plugin")
            media_dir = tmp_path / "test_plugin" / "media" / "images"
            media_dir.mkdir(parents=True, exist_ok=True)

            f1 = media_dir / "a.jpg"
            f2 = media_dir / "b.jpg"
            f1.write_text("a")
            f2.write_text("b")

            deleted = md.delete_media_files(["images/a.jpg", "images/b.jpg", "images/c.jpg"])
            assert deleted == 2
