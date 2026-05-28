"""平台适配器模块 - 为不同平台提供统一的消息处理接口"""

from typing import Optional, Dict, Type
from astrbot.api import logger


class PlatformAdapter:
    """平台适配器基类"""

    PLATFORM_NAME: str = "generic"

    def normalize_sender_id(self, raw_id: str) -> str:
        return str(raw_id).strip() if raw_id else ""

    def normalize_sender_name(self, raw_name: Optional[str]) -> Optional[str]:
        if not raw_name:
            return None
        return str(raw_name).strip()[:256] or None

    def normalize_group_id(self, raw_group_id: Optional[str]) -> Optional[str]:
        if not raw_group_id:
            return None
        return str(raw_group_id).strip()[:128] or None

    def extract_channel_id(self, message_obj) -> Optional[str]:
        return None

    def normalize_channel_id(self, raw_channel_id: Optional[str]) -> Optional[str]:
        if not raw_channel_id:
            return None
        cid = str(raw_channel_id).strip()
        return cid[:128] if cid else None

    def normalize_message_id(self, raw_message_id: Optional[str]) -> str:
        if not raw_message_id:
            return ""
        return str(raw_message_id).strip()[:128]

    def determine_message_type(self, message_obj) -> str:
        if message_obj.group_id:
            return "group"
        return "private"

    def extract_media_url(self, component, comp_data: dict) -> Optional[str]:
        from .serializer import extract_media_url
        return extract_media_url(comp_data)

    def extract_reply_to_id(self, component, comp_data: dict) -> Optional[str]:
        if comp_data.get("type") == "Reply":
            return comp_data.get("message_id") or comp_data.get("id")
        return None


class TelegramAdapter(PlatformAdapter):
    PLATFORM_NAME = "telegram"

    def normalize_message_id(self, raw_message_id: Optional[str]) -> str:
        if not raw_message_id:
            return ""
        try:
            return str(int(raw_message_id))
        except (ValueError, TypeError):
            return str(raw_message_id).strip()[:128]


class DiscordAdapter(PlatformAdapter):
    PLATFORM_NAME = "discord"

    def extract_channel_id(self, message_obj) -> Optional[str]:
        if hasattr(message_obj, "channel_id") and message_obj.channel_id:
            return str(message_obj.channel_id)
        return None

    def normalize_channel_id(self, raw_channel_id: Optional[str]) -> Optional[str]:
        if not raw_channel_id:
            return None
        cid = str(raw_channel_id).strip()
        return cid[:128] if cid else None

    def determine_message_type(self, message_obj) -> str:
        if message_obj.group_id:
            group_id = str(message_obj.group_id)
            if group_id.startswith("channel_") or group_id.startswith("dm_"):
                return "private"
            return "channel"
        return "private"


class QQOfficialAdapter(PlatformAdapter):
    PLATFORM_NAME = "qq_official"

    def determine_message_type(self, message_obj) -> str:
        if message_obj.group_id:
            return "group"
        return "private"


class QQPrivateAdapter(QQOfficialAdapter):
    PLATFORM_NAME = "qq_private"


class WechatAdapter(PlatformAdapter):
    PLATFORM_NAME = "wechat"

    def normalize_message_id(self, raw_message_id: Optional[str]) -> str:
        if not raw_message_id:
            return ""
        return str(raw_message_id).strip()[:128]


_ADAPTER_REGISTRY: Dict[str, Type[PlatformAdapter]] = {
    "telegram": TelegramAdapter,
    "discord": DiscordAdapter,
    "qq_official": QQOfficialAdapter,
    "qq_private": QQPrivateAdapter,
    "wechat": WechatAdapter,
}

_generic_adapter = PlatformAdapter()
_adapter_cache: Dict[str, PlatformAdapter] = {}


def get_adapter(platform_name: str) -> PlatformAdapter:
    if not platform_name:
        return _generic_adapter

    if platform_name in _adapter_cache:
        return _adapter_cache[platform_name]

    adapter_cls = _ADAPTER_REGISTRY.get(platform_name)
    if adapter_cls:
        adapter = adapter_cls()
    else:
        logger.debug(
            f"[MessageRecorder] 未注册的平台适配器: {platform_name}，使用通用适配器"
        )
        adapter = PlatformAdapter()

    _adapter_cache[platform_name] = adapter
    return adapter


def register_adapter(platform_name: str, adapter_cls: Type[PlatformAdapter]):
    _ADAPTER_REGISTRY[platform_name] = adapter_cls
    _adapter_cache.pop(platform_name, None)
    logger.info(f"[MessageRecorder] 已注册平台适配器: {platform_name}")
