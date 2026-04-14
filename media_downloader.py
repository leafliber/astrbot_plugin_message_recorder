"""多媒体文件下载与保存模块"""

import asyncio
import hashlib
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import aiohttp
from PIL import Image

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


MEDIA_TYPE_MAP = {
    "Image": "images",
    "Record": "records",
    "Video": "videos",
    "File": "files",
}

CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/amr": ".amr",
    "audio/flac": ".flac",
    "audio/silk": ".silk",
    "application/octet-stream": ".bin",
}

KNOWN_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg",
    "mp4", "avi", "mkv", "mov", "webm",
    "mp3", "wav", "ogg", "amr", "flac", "silk", "aac",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "zip", "rar", "7z", "tar", "gz",
    "txt", "json", "xml", "csv",
}

THUMBNAIL_MAX_SIZE = 320


class MediaDownloader:
    """多媒体文件下载器"""

    def __init__(self, plugin_name: str, image_save_mode: str = "original"):
        self.plugin_name = plugin_name
        self.image_save_mode = image_save_mode
        self.media_base_path = (
            Path(get_astrbot_data_path())
            / "plugin_data"
            / plugin_name
            / "media"
        )
        self.media_base_path.mkdir(parents=True, exist_ok=True)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def get_media_base_path(self) -> Path:
        return self.media_base_path

    async def download_media(
        self,
        url: str,
        component_type: str,
        filename: Optional[str] = None,
    ) -> Optional[str]:
        if not url or not url.startswith("http"):
            return None

        media_subdir = MEDIA_TYPE_MAP.get(component_type, "files")

        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"[MediaDownloader] 下载失败: HTTP {resp.status}, URL: {url[:100]}"
                    )
                    return None

                content = await resp.read()
                if not content:
                    logger.warning("[MediaDownloader] 下载内容为空")
                    return None

                content_type = resp.headers.get("Content-Type", "")
                ext = self._determine_extension(url, content_type, component_type)

                content_hash = hashlib.sha256(content).hexdigest()[:16]

                if not filename:
                    filename = f"{content_hash}{ext}"

                date_dir = self._get_date_dir(media_subdir)
                date_dir.mkdir(parents=True, exist_ok=True)

                file_path = date_dir / filename

                if file_path.exists():
                    rel_path = file_path.relative_to(self.media_base_path)
                    logger.debug(
                        f"[MediaDownloader] 文件已存在，跳过保存: {rel_path}"
                    )
                    return str(rel_path)

                if component_type == "Image" and self.image_save_mode == "thumbnail":
                    content = self._create_thumbnail(content)
                    content_hash = hashlib.sha256(content).hexdigest()[:16]
                    filename = f"{content_hash}{ext}"
                    file_path = date_dir / filename

                    if file_path.exists():
                        rel_path = file_path.relative_to(self.media_base_path)
                        logger.debug(
                            f"[MediaDownloader] 缩略图已存在，跳过保存: {rel_path}"
                        )
                        return str(rel_path)

                file_path.write_bytes(content)

                rel_path = file_path.relative_to(self.media_base_path)
                logger.debug(
                    f"[MediaDownloader] 文件已保存: {rel_path} "
                    f"({len(content)} bytes)"
                )
                return str(rel_path)

        except asyncio.TimeoutError:
            logger.warning(f"[MediaDownloader] 下载超时: {url[:100]}")
            return None
        except Exception as e:
            logger.warning(f"[MediaDownloader] 下载出错: {e}")
            return None

    def _create_thumbnail(self, image_data: bytes) -> bytes:
        try:
            img = Image.open(io.BytesIO(image_data))
            img.thumbnail((THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE), Image.LANCZOS)
            output = io.BytesIO()
            img_format = img.format or "JPEG"
            if img_format == "PNG" and img.mode in ("RGBA", "LA", "P"):
                img.save(output, format="PNG", optimize=True)
            else:
                img = img.convert("RGB")
                img.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue()
        except Exception as e:
            logger.warning(
                f"[MediaDownloader] 缩略图生成失败，使用原图: {e}"
            )
            return image_data

    def _get_date_dir(self, media_subdir: str) -> Path:
        date_str = datetime.now().strftime("%Y-%m")
        return self.media_base_path / media_subdir / date_str

    def _determine_extension(
        self, url: str, content_type: str, component_type: str
    ) -> str:
        url_path = url.split("?")[0]
        if "." in url_path:
            ext = url_path.rsplit(".", 1)[-1].lower()
            if ext in KNOWN_EXTENSIONS:
                return f".{ext}"

        for ct, ext in CONTENT_TYPE_EXT.items():
            if ct in content_type:
                return ext

        defaults = {
            "Image": ".jpg",
            "Record": ".wav",
            "Video": ".mp4",
            "File": ".bin",
        }
        return defaults.get(component_type, ".bin")

    def delete_media_file(self, relative_path: str) -> bool:
        if not relative_path:
            return False
        try:
            file_path = self.media_base_path / relative_path
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                logger.debug(f"[MediaDownloader] 已删除媒体文件: {relative_path}")
                return True
            return False
        except Exception as e:
            logger.warning(f"[MediaDownloader] 删除媒体文件失败: {e}")
            return False

    def delete_media_files(self, relative_paths: List[str]) -> int:
        deleted = 0
        for path in relative_paths:
            if self.delete_media_file(path):
                deleted += 1
        return deleted

    @staticmethod
    def extract_media_paths(message_chain_json: Optional[str]) -> List[str]:
        if not message_chain_json:
            return []
        try:
            chain = json.loads(message_chain_json)
            if not isinstance(chain, list):
                return []
            paths = []
            for comp in chain:
                if isinstance(comp, dict) and "local_path" in comp:
                    lp = comp["local_path"]
                    if isinstance(lp, str) and lp:
                        paths.append(lp)
            return paths
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    def cleanup_orphaned_media(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        import time as _time

        cutoff = _time.time() - retention_days * 86400
        deleted = 0

        for subdir in MEDIA_TYPE_MAP.values():
            type_dir = self.media_base_path / subdir
            if not type_dir.exists():
                continue
            for date_dir in type_dir.iterdir():
                if not date_dir.is_dir():
                    continue
                for file_path in date_dir.iterdir():
                    if not file_path.is_file():
                        continue
                    try:
                        if file_path.stat().st_mtime < cutoff:
                            file_path.unlink()
                            deleted += 1
                    except OSError:
                        pass

        if deleted > 0:
            logger.info(
                f"[MediaDownloader] 已清理 {deleted} 个过期媒体文件"
            )
        return deleted
