"""辅助函数模块"""

import os
import time
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from ..models import QueryFilter, MessageRecord, PLUGIN_DIR_NAME


_current_dir = Path(__file__).resolve().parent.parent


def get_plugin_dir() -> Path:
    return _current_dir


def get_plugin_data_dir() -> Path:
    return Path(get_astrbot_plugin_data_path()) / PLUGIN_DIR_NAME


def safe_remove_file(file_path: str, max_retries: int = 3, delay: float = 0.5) -> bool:
    for attempt in range(max_retries):
        try:
            os.remove(file_path)
            return True
        except OSError as e:
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                logger.warning(f"[MessageRecorder Web] 清理临时文件失败（重试 {max_retries} 次）: {file_path}, {e}")
                return False
    return False


def cleanup_temp_dir() -> None:
    temp_dir = get_plugin_data_dir() / "temp"
    if not temp_dir.exists():
        return

    cleaned = 0
    for item in temp_dir.iterdir():
        try:
            if item.is_file():
                item.unlink()
                cleaned += 1
            elif item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
                cleaned += 1
        except Exception as e:
            logger.warning(f"[MessageRecorder Web] 启动清理临时文件失败: {item}, {e}")

    if cleaned > 0:
        logger.info(f"[MessageRecorder Web] 启动时清理了 {cleaned} 个残留临时文件/目录")


def format_timestamp(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")


def format_message(msg: MessageRecord) -> Dict[str, Any]:
    return {
        "id": msg.id,
        "platform": msg.platform,
        "sender_id": msg.sender_id,
        "sender_name": msg.sender_name,
        "group_id": msg.group_id,
        "message_type": msg.message_type,
        "message_str": msg.message_str,
        "timestamp": msg.timestamp,
        "formatted_time": format_timestamp(msg.timestamp),
        "has_chain": bool(msg.message_chain),
        "has_raw": bool(msg.raw_message)
    }


def format_message_for_export(msg: MessageRecord, include_chain: bool = True, include_raw: bool = False) -> Dict[str, Any]:
    import json

    result = {
        "id": msg.id,
        "platform": msg.platform,
        "sender_id": msg.sender_id,
        "sender_name": msg.sender_name,
        "group_id": msg.group_id,
        "message_type": msg.message_type,
        "message_str": msg.message_str,
        "timestamp": msg.timestamp,
        "formatted_time": format_timestamp(msg.timestamp),
        "message_id": msg.message_id,
        "session_id": msg.session_id,
        "created_at": msg.created_at,
        "formatted_created_at": format_timestamp(msg.created_at) if msg.created_at else None
    }

    if include_chain:
        if msg.message_chain:
            try:
                chain = json.loads(msg.message_chain)
                if isinstance(chain, list):
                    for comp in chain:
                        if isinstance(comp, dict) and "local_path" in comp:
                            lp = comp["local_path"]
                            if isinstance(lp, str) and lp:
                                comp["media_url"] = f"/message_recorder/api/media/{lp}"
                result["message_chain"] = chain
            except (json.JSONDecodeError, TypeError):
                result["message_chain"] = None
        else:
            result["message_chain"] = None

    if include_raw:
        if msg.raw_message:
            try:
                result["raw_message"] = json.loads(msg.raw_message)
            except json.JSONDecodeError:
                result["raw_message"] = None
        else:
            result["raw_message"] = None

    return result


def format_message_detail(msg: MessageRecord) -> Dict[str, Any]:
    import json

    result = format_message(msg)
    result.update({
        "message_id": msg.message_id,
        "session_id": msg.session_id,
        "created_at": msg.created_at,
        "formatted_created_at": format_timestamp(msg.created_at) if msg.created_at else None
    })

    if msg.message_chain:
        try:
            chain = json.loads(msg.message_chain)
            if isinstance(chain, list):
                for comp in chain:
                    if isinstance(comp, dict) and "local_path" in comp:
                        lp = comp["local_path"]
                        if isinstance(lp, str) and lp:
                            comp["media_url"] = f"/message_recorder/api/media/{lp}"
            result["message_chain"] = chain
        except json.JSONDecodeError:
            result["message_chain"] = None
    else:
        result["message_chain"] = None

    if msg.raw_message:
        try:
            result["raw_message"] = json.loads(msg.raw_message)
        except json.JSONDecodeError:
            result["raw_message"] = None
    else:
        result["raw_message"] = None

    return result


def build_query_filter(args: Dict[str, Any]) -> QueryFilter:
    platform = args.get("platform")
    platforms_str = args.get("platforms")
    platforms = platforms_str.split(",") if platforms_str else None

    sender_id = args.get("sender_id")
    sender_ids_str = args.get("sender_ids")
    sender_ids = sender_ids_str.split(",") if sender_ids_str else None

    group_id = args.get("group_id")
    group_ids_str = args.get("group_ids")
    group_ids = group_ids_str.split(",") if group_ids_str else None

    session_id = args.get("session_id")
    session_ids_str = args.get("session_ids")
    session_ids = session_ids_str.split(",") if session_ids_str else None

    time_range = args.get("time")
    start_time = int(args.get("start_time", 0)) if args.get("start_time") else None
    end_time = int(args.get("end_time", 0)) if args.get("end_time") else None

    limit = min(int(args.get("limit", 50)), 200)
    offset = int(args.get("offset", 0))
    order = args.get("order", "desc")

    return QueryFilter(
        platform=platform,
        platforms=platforms,
        sender_id=sender_id,
        sender_ids=sender_ids,
        group_id=group_id,
        group_ids=group_ids,
        session_id=session_id,
        session_ids=session_ids,
        message_type=args.get("message_type"),
        time=time_range,
        start_time=start_time,
        end_time=end_time,
        keyword=args.get("keyword"),
        limit=limit,
        offset=offset,
        order=order
    )


def build_query_filter_from_dict(data: Dict[str, Any]) -> QueryFilter:
    limit_val = data.get("limit")
    if limit_val is None or limit_val == 0:
        effective_limit = -1
    else:
        effective_limit = int(limit_val)

    return QueryFilter(
        platform=data.get("platform"),
        platforms=data.get("platforms"),
        sender_id=data.get("sender_id"),
        sender_ids=data.get("sender_ids"),
        group_id=data.get("group_id"),
        group_ids=data.get("group_ids"),
        session_id=data.get("session_id"),
        session_ids=data.get("session_ids"),
        message_type=data.get("message_type"),
        time=data.get("time"),
        start_time=data.get("start_time"),
        end_time=data.get("end_time"),
        keyword=data.get("keyword"),
        limit=effective_limit,
        offset=data.get("offset", 0),
        order=data.get("order", "desc")
    )


def estimate_size(count: int, format_type: str) -> str:
    avg_size_per_record = {
        "json": 500,
        "csv": 200,
        "txt": 150
    }
    estimated_bytes = count * avg_size_per_record.get(format_type, 500)

    if estimated_bytes < 1024:
        return f"{estimated_bytes} B"
    elif estimated_bytes < 1024 * 1024:
        return f"{estimated_bytes / 1024:.1f} KB"
    else:
        return f"{estimated_bytes / (1024 * 1024):.1f} MB"


def get_platform_icon(platform: str) -> str:
    icons = {
        "telegram": "[TG]",
        "discord": "[DC]",
        "qq_official": "[QQ]",
        "qq_private": "[QQ]",
        "wechat": "[WX]",
    }
    return icons.get(platform, f"[{platform}]")
