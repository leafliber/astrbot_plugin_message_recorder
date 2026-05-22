"""Web API 注册模块 - 使用 AstrBot Plugin Pages 的 register_web_api"""

import os
import json
import csv
import time
import uuid
import shutil
import asyncio
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

import base64

from quart import jsonify, request, send_file

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .database import Database
from .models import QueryFilter, MessageRecord, MessageStats, PLUGIN_DIR_NAME, SCHEMA_VERSION
from .time_utils import parse_time_range, normalize_timestamp

MAX_IMPORT_FILE_SIZE = 4 * 1024 * 1024 * 1024
MAX_EXPORT_FILE_AGE = 3600
MAX_DOWNLOAD_DATA_SIZE = 50 * 1024 * 1024
ALLOWED_IMPORT_EXTENSIONS = {".json", ".csv", ".mrpkg"}
CHUNK_SIZE = 5 * 1024 * 1024
CHUNK_SESSION_MAX_AGE = 3600
DB_OPERATION_TIMEOUT = 30
IMPORT_RECORD_TIMEOUT = 5

_export_tasks: Dict[str, Dict[str, Any]] = {}
_chunk_sessions: Dict[str, Dict[str, Any]] = {}
_import_tasks: Dict[str, Dict[str, Any]] = {}


def _get_plugin_data_dir() -> Path:
    return Path(get_astrbot_plugin_data_path()) / PLUGIN_DIR_NAME


def _format_timestamp(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _format_message(msg: MessageRecord) -> Dict[str, Any]:
    return {
        "id": msg.id,
        "platform": msg.platform,
        "sender_id": msg.sender_id,
        "sender_name": msg.sender_name,
        "group_id": msg.group_id,
        "channel_id": msg.channel_id,
        "message_type": msg.message_type,
        "message_str": msg.message_str,
        "reply_to_id": msg.reply_to_id,
        "timestamp": msg.timestamp,
        "formatted_time": _format_timestamp(msg.timestamp),
        "has_chain": bool(msg.message_chain),
        "has_raw": bool(msg.raw_message),
    }


def _format_message_detail(msg: MessageRecord) -> Dict[str, Any]:
    result = _format_message(msg)
    result.update({
        "message_id": msg.message_id,
        "session_id": msg.session_id,
        "created_at": msg.created_at,
        "formatted_created_at": _format_timestamp(msg.created_at) if msg.created_at else None,
    })
    if msg.message_chain:
        try:
            chain = json.loads(msg.message_chain)
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


def _format_message_for_export(msg: MessageRecord, include_chain: bool = True, include_raw: bool = False) -> Dict[str, Any]:
    result = {
        "id": msg.id,
        "platform": msg.platform,
        "sender_id": msg.sender_id,
        "sender_name": msg.sender_name,
        "group_id": msg.group_id,
        "channel_id": msg.channel_id,
        "message_type": msg.message_type,
        "message_str": msg.message_str,
        "reply_to_id": msg.reply_to_id,
        "timestamp": msg.timestamp,
        "formatted_time": _format_timestamp(msg.timestamp),
        "message_id": msg.message_id,
        "session_id": msg.session_id,
        "created_at": msg.created_at,
        "formatted_created_at": _format_timestamp(msg.created_at) if msg.created_at else None,
    }
    if include_chain:
        if msg.message_chain:
            try:
                result["message_chain"] = json.loads(msg.message_chain)
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


def _build_query_filter(args: Dict[str, Any]) -> QueryFilter:
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
        channel_id=args.get("channel_id"),
        message_type=args.get("message_type"),
        time=args.get("time"),
        start_time=start_time,
        end_time=end_time,
        keyword=args.get("keyword"),
        reply_to_id=args.get("reply_to_id"),
        limit=limit,
        offset=offset,
        order=order,
    )


def _build_query_filter_from_dict(data: Dict[str, Any]) -> QueryFilter:
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
        channel_id=data.get("channel_id"),
        message_type=data.get("message_type"),
        time=data.get("time"),
        start_time=data.get("start_time"),
        end_time=data.get("end_time"),
        keyword=data.get("keyword"),
        reply_to_id=data.get("reply_to_id"),
        limit=effective_limit,
        offset=data.get("offset", 0),
        order=data.get("order", "desc"),
    )


def _estimate_size(count: int, format_type: str) -> str:
    avg_size_per_record = {"json": 500, "csv": 200, "txt": 150}
    estimated_bytes = count * avg_size_per_record.get(format_type, 500)
    if estimated_bytes < 1024:
        return f"{estimated_bytes} B"
    elif estimated_bytes < 1024 * 1024:
        return f"{estimated_bytes / 1024:.1f} KB"
    else:
        return f"{estimated_bytes / (1024 * 1024):.1f} MB"


def _get_platform_icon(platform: str) -> str:
    icons = {
        "telegram": "[TG]",
        "discord": "[DC]",
        "qq_official": "[QQ]",
        "qq_private": "[QQ]",
        "wechat": "[WX]",
    }
    return icons.get(platform, f"[{platform}]")


def _safe_remove_file(file_path: str, max_retries: int = 3, delay: float = 0.5) -> bool:
    for attempt in range(max_retries):
        try:
            os.remove(file_path)
            return True
        except OSError:
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                return False
    return False


def _cleanup_temp_dir() -> None:
    temp_dir = _get_plugin_data_dir() / "temp"
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
            logger.warning(f"[MessageRecorder Web] 清理临时文件失败: {item}, {e}")
    if cleaned > 0:
        logger.info(f"[MessageRecorder Web] 清理了 {cleaned} 个残留临时文件/目录")


def register_all_web_apis(context, db: Database):
    _cleanup_temp_dir()

    prefix = f"/{PLUGIN_DIR_NAME}"

    # ========== Stats APIs ==========

    async def api_stats():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            stats = await db.get_stats()
            time_range = {}
            if stats.oldest_timestamp:
                time_range["start"] = _format_timestamp(stats.oldest_timestamp)
            if stats.newest_timestamp:
                time_range["end"] = _format_timestamp(stats.newest_timestamp)
            return jsonify({
                "success": True,
                "data": {
                    "total_count": stats.total_count,
                    "group_message_count": stats.group_message_count,
                    "private_message_count": stats.private_message_count,
                    "channel_message_count": stats.channel_message_count,
                    "platform_stats": stats.platform_stats,
                    "platform_count": len(stats.platform_stats),
                    "oldest_timestamp": stats.oldest_timestamp,
                    "newest_timestamp": stats.newest_timestamp,
                    "time_range": time_range,
                    "schema_version": SCHEMA_VERSION,
                },
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取统计失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_stats_timeline():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            interval = request.args.get("interval", "day")
            platform = request.args.get("platform")
            group_id = request.args.get("group_id")
            start_time = request.args.get("start_time")
            end_time = request.args.get("end_time")
            start_ts = int(start_time) if start_time else None
            end_ts = int(end_time) if end_time else None
            points = await db.get_timeline_stats(
                interval=interval, start_time=start_ts, end_time=end_ts,
                platform=platform, group_id=group_id,
            )
            return jsonify({
                "success": True,
                "data": {"interval": interval, "points": points, "total_points": len(points)},
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取时间趋势失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_stats_senders():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            limit = int(request.args.get("limit", 20))
            time_range = request.args.get("time")
            platform = request.args.get("platform")
            group_id = request.args.get("group_id")
            start_time, end_time = None, None
            if time_range:
                start_time, end_time = parse_time_range(time_range)
            senders = await db.get_sender_ranking(
                limit=limit, start_time=start_time, end_time=end_time,
                platform=platform, group_id=group_id,
            )
            return jsonify({"success": True, "data": {"senders": senders, "total": len(senders)}})
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取发送者排行失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_stats_groups():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            limit = int(request.args.get("limit", 20))
            time_range = request.args.get("time")
            platform = request.args.get("platform")
            start_time, end_time = None, None
            if time_range:
                start_time, end_time = parse_time_range(time_range)
            groups = await db.get_group_ranking(
                limit=limit, start_time=start_time, end_time=end_time, platform=platform,
            )
            return jsonify({"success": True, "data": {"groups": groups, "total": len(groups)}})
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取群组统计失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    # ========== Messages APIs ==========

    async def api_messages():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            query_filter = _build_query_filter(request.args)
            messages = await db.query_messages(query_filter)
            total = await db.count_messages(query_filter)
            return jsonify({
                "success": True,
                "data": {
                    "messages": [_format_message(msg) for msg in messages],
                    "pagination": {
                        "total": total,
                        "limit": query_filter.limit,
                        "offset": query_filter.offset,
                        "has_more": query_filter.offset + query_filter.limit < total,
                    },
                },
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 查询消息失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_message_detail():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            message_id_str = request.args.get("id") or request.args.get("message_id")
            if not message_id_str:
                return jsonify({"success": False, "error": "缺少消息ID"})
            message_id = int(message_id_str)
            message = await db.get_message_by_id(message_id)
            if not message:
                return jsonify({"success": False, "error": "消息不存在"})
            return jsonify({"success": True, "data": _format_message_detail(message)})
        except ValueError:
            return jsonify({"success": False, "error": "消息ID格式无效"})
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取消息详情失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_message_context():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            message_id_str = request.args.get("id") or request.args.get("message_id")
            if not message_id_str:
                return jsonify({"success": False, "error": "缺少消息ID"})
            message_id = int(message_id_str)
            before = int(request.args.get("before", 5))
            after = int(request.args.get("after", 5))
            context = await db.get_context_messages(message_id, before, after)
            target = await db.get_message_by_id(message_id)
            return jsonify({
                "success": True,
                "data": {
                    "target": _format_message_detail(target) if target else None,
                    "before": [_format_message(m) for m in context["before"]],
                    "after": [_format_message(m) for m in context["after"]],
                },
            })
        except ValueError:
            return jsonify({"success": False, "error": "消息ID格式无效"})
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取消息上下文失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    # ========== Search API ==========

    async def api_search():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            keyword = request.args.get("keyword", "")
            if not keyword:
                return jsonify({"success": False, "error": "缺少关键词"})
            query_filter = _build_query_filter(request.args)
            query_filter.keyword = keyword
            messages = await db.query_messages(query_filter)
            total = await db.count_messages(query_filter)
            return jsonify({
                "success": True,
                "data": {
                    "messages": [_format_message(msg) for msg in messages],
                    "pagination": {
                        "total": total,
                        "limit": query_filter.limit,
                        "offset": query_filter.offset,
                        "has_more": query_filter.offset + query_filter.limit < total,
                    },
                    "keyword": keyword,
                },
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 搜索失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    # ========== Export APIs ==========

    async def api_export():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            data = await request.get_json()
            format_type = data.get("format", "json")
            filters = data.get("filters", {})
            options = data.get("options", {})
            query_filter = _build_query_filter_from_dict(filters)
            estimated_count = await db.count_messages(query_filter)
            task_id = f"export_{uuid.uuid4().hex[:12]}"
            _export_tasks[task_id] = {
                "status": "pending",
                "format": format_type,
                "filter": filters,
                "options": options,
                "estimated_count": estimated_count,
                "created_at": time.time(),
                "completed_at": None,
                "file_path": None,
                "error": None,
            }
            asyncio.create_task(_execute_export_task(task_id, db, query_filter, format_type, options))
            return jsonify({
                "success": True,
                "data": {
                    "task_id": task_id,
                    "status": "pending",
                    "estimated_count": estimated_count,
                    "estimated_size": _estimate_size(estimated_count, format_type),
                },
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 创建导出任务失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_export_status():
        task_id = request.args.get("task_id")
        if not task_id:
            return jsonify({"success": False, "error": "缺少任务ID"})
        task = _export_tasks.get(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"})
        return jsonify({"success": True, "data": task})

    async def api_export_download():
        task_id = request.args.get("task_id")
        if not task_id:
            return jsonify({"success": False, "error": "缺少任务ID"}), 400
        task = _export_tasks.get(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404
        if task["status"] != "completed":
            return jsonify({"success": False, "error": "导出未完成"}), 400
        completed_at = task.get("completed_at", 0)
        file_age = time.time() - completed_at
        if file_age > MAX_EXPORT_FILE_AGE:
            file_path = task.get("file_path")
            if file_path and os.path.exists(file_path):
                _safe_remove_file(file_path)
            _export_tasks.pop(task_id, None)
            return jsonify({"success": False, "error": "导出文件已过期，请重新导出"}), 410
        file_path = task.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return jsonify({"success": False, "error": "文件不存在"}), 404
        format_type = task.get("format", "json")
        ext = "zip" if format_type == "json" and task.get("options", {}).get("include_media") else format_type
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(completed_at))
        filename = f"messages_export_{timestamp}.{ext}"
        mime_types = {"json": "application/json", "csv": "text/csv", "txt": "text/plain", "zip": "application/zip"}
        mimetype = mime_types.get(ext, "application/octet-stream")
        response = await send_file(file_path, mimetype=mimetype, as_attachment=True, attachment_filename=filename)
        response.timeout = None
        return response

    async def api_export_download_data():
        task_id = request.args.get("task_id")
        if not task_id:
            return jsonify({"success": False, "error": "缺少任务ID"})
        task = _export_tasks.get(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"})
        if task["status"] != "completed":
            return jsonify({"success": False, "error": "导出未完成"})
        completed_at = task.get("completed_at", 0)
        file_age = time.time() - completed_at
        if file_age > MAX_EXPORT_FILE_AGE:
            file_path = task.get("file_path")
            if file_path and os.path.exists(file_path):
                _safe_remove_file(file_path)
            _export_tasks.pop(task_id, None)
            return jsonify({"success": False, "error": "导出文件已过期，请重新导出"})
        file_path = task.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return jsonify({"success": False, "error": "文件不存在"})
        format_type = task.get("format", "json")
        ext = "zip" if format_type == "json" and task.get("options", {}).get("include_media") else format_type
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(completed_at))
        filename = f"messages_export_{timestamp}.{ext}"
        mime_types = {"json": "application/json", "csv": "text/csv", "txt": "text/plain", "zip": "application/zip"}
        mimetype = mime_types.get(ext, "application/octet-stream")
        file_size = os.path.getsize(file_path)
        if file_size > MAX_DOWNLOAD_DATA_SIZE:
            return jsonify({"success": False, "error": f"文件过大 ({file_size} bytes)，请使用流式下载"}), 400
        try:
            with open(file_path, "rb") as f:
                file_data = f.read()
            b64_data = base64.b64encode(file_data).decode("ascii")
            return jsonify({
                "success": True,
                "data": {
                    "filename": filename,
                    "mimetype": mimetype,
                    "base64": b64_data,
                    "size": len(file_data),
                },
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 读取导出文件失败: {e}")
            return jsonify({"success": False, "error": f"读取文件失败: {e}"})

    # ========== Import APIs ==========

    async def api_import_upload():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            files = await request.files
            if not files or "file" not in files:
                return jsonify({"success": False, "error": "未上传文件"})
            uploaded_file = files["file"]
            filename = uploaded_file.filename or "import.json"
            file_ext = Path(filename).suffix.lower()
            if file_ext not in ALLOWED_IMPORT_EXTENSIONS:
                return jsonify({"success": False, "error": f"不支持的文件格式: {file_ext}"})
            content = uploaded_file.read()
            if len(content) > MAX_IMPORT_FILE_SIZE:
                max_gb = MAX_IMPORT_FILE_SIZE // (1024 * 1024 * 1024)
                return jsonify({"success": False, "error": f"文件大小超过限制（最大 {max_gb}GB）"})
            temp_dir = _get_plugin_data_dir() / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            task_id = f"import_{uuid.uuid4().hex[:12]}"
            temp_file = temp_dir / f"{task_id}{file_ext}"
            temp_file.write_bytes(content)
            mode = request.form.get("mode", "skip_duplicates")
            _import_tasks[task_id] = {
                "status": "pending",
                "mode": mode,
                "filename": filename,
                "file_path": str(temp_file),
                "created_at": time.time(),
                "total_records": 0,
                "processed": 0,
                "imported": 0,
                "skipped": 0,
                "errors": 0,
                "media_restored": 0,
                "completed_at": None,
                "error": None,
            }
            asyncio.create_task(_execute_import_task(task_id, db, str(temp_file), mode))
            return jsonify({
                "success": True,
                "data": {
                    "task_id": task_id,
                    "status": "pending",
                    "filename": filename,
                    "mode": mode,
                    "file_size": len(content),
                },
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 导入上传失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_import_init():
        try:
            data = await request.get_json()
            filename = data.get("filename", "")
            file_size = data.get("file_size", 0)
            chunk_size = data.get("chunk_size", CHUNK_SIZE)
            mode = data.get("mode", "skip_duplicates")
            file_ext = Path(filename).suffix.lower() if filename else ".json"
            if file_ext not in ALLOWED_IMPORT_EXTENSIONS:
                return jsonify({"success": False, "error": f"不支持的文件格式: {file_ext}"})
            if file_size > MAX_IMPORT_FILE_SIZE:
                max_gb = MAX_IMPORT_FILE_SIZE // (1024 * 1024 * 1024)
                return jsonify({"success": False, "error": f"文件大小超过限制（最大 {max_gb}GB）"})
            total_chunks = (file_size + chunk_size - 1) // chunk_size if chunk_size > 0 else 1
            session_id = uuid.uuid4().hex
            chunks_dir = _get_plugin_data_dir() / "temp" / f"chunks_{session_id}"
            chunks_dir.mkdir(parents=True, exist_ok=True)
            _chunk_sessions[session_id] = {
                "filename": filename,
                "file_ext": file_ext,
                "file_size": file_size,
                "chunk_size": chunk_size,
                "total_chunks": total_chunks,
                "mode": mode,
                "chunks_dir": str(chunks_dir),
                "uploaded_chunks": [],
                "created_at": time.time(),
            }
            return jsonify({
                "success": True,
                "data": {
                    "session_id": session_id,
                    "total_chunks": total_chunks,
                    "chunk_size": chunk_size,
                },
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 初始化分片导入失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_import_chunk(session_id, chunk_index):
        session = _chunk_sessions.get(session_id)
        if not session:
            return jsonify({"success": False, "error": "会话不存在或已过期"})
        if chunk_index >= session["total_chunks"] or chunk_index < 0:
            return jsonify({"success": False, "error": "分片索引无效"})
        try:
            files = await request.files
            if not files or "chunk" not in files:
                return jsonify({"success": False, "error": "未上传分片"})
            chunk_file = files["chunk"]
            chunk_data = chunk_file.read()
            chunk_path = Path(session["chunks_dir"]) / f"{chunk_index:06d}"
            chunk_path.write_bytes(chunk_data)
            if chunk_index not in session["uploaded_chunks"]:
                session["uploaded_chunks"].append(chunk_index)
            return jsonify({
                "success": True,
                "data": {
                    "session_id": session_id,
                    "chunk_index": chunk_index,
                    "uploaded_chunks": len(session["uploaded_chunks"]),
                    "total_chunks": session["total_chunks"],
                },
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 上传分片失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_import_complete():
        try:
            data = await request.get_json()
            session_id = data.get("session_id")
            if not session_id:
                return jsonify({"success": False, "error": "缺少会话ID"})
            session = _chunk_sessions.get(session_id)
            if not session:
                return jsonify({"success": False, "error": "会话不存在或已过期"})

            if len(session["uploaded_chunks"]) < session["total_chunks"]:
                missing = set(range(session["total_chunks"])) - set(session["uploaded_chunks"])
                return jsonify({"success": False, "error": f"尚有 {len(missing)} 个分片未上传"})

            task_id = f"import_{uuid.uuid4().hex[:12]}"
            temp_dir = _get_plugin_data_dir() / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            assembled_file = temp_dir / f"{task_id}{session['file_ext']}"

            with open(assembled_file, "wb") as dst:
                for i in range(session["total_chunks"]):
                    chunk_path = Path(session["chunks_dir"]) / f"{i:06d}"
                    if chunk_path.exists():
                        with open(chunk_path, "rb") as src:
                            shutil.copyfileobj(src, dst)

            shutil.rmtree(session["chunks_dir"], ignore_errors=True)
            _chunk_sessions.pop(session_id, None)

            actual_size = assembled_file.stat().st_size
            if actual_size > MAX_IMPORT_FILE_SIZE:
                assembled_file.unlink()
                max_gb = MAX_IMPORT_FILE_SIZE // (1024 * 1024 * 1024)
                return jsonify({"success": False, "error": f"文件大小超过限制（最大 {max_gb}GB）"})

            _import_tasks[task_id] = {
                "status": "pending",
                "mode": session["mode"],
                "filename": session["filename"],
                "file_path": str(assembled_file),
                "created_at": time.time(),
                "total_records": 0,
                "processed": 0,
                "imported": 0,
                "skipped": 0,
                "errors": 0,
                "media_restored": 0,
                "completed_at": None,
                "error": None,
            }

            asyncio.create_task(_execute_import_task(task_id, db, str(assembled_file), session["mode"]))

            return jsonify({
                "success": True,
                "data": {
                    "task_id": task_id,
                    "status": "pending",
                    "filename": session["filename"],
                    "mode": session["mode"],
                    "file_size": actual_size,
                },
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 完成分片上传失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_import_status():
        task_id = request.args.get("task_id")
        if not task_id:
            return jsonify({"success": False, "error": "缺少任务ID"})
        task = _import_tasks.get(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"})
        return jsonify({"success": True, "data": task})

    # ========== Metadata APIs ==========

    async def api_platforms():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            platforms = await db.get_distinct_platforms()
            return jsonify({"success": True, "data": {"platforms": platforms}})
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取平台列表失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_senders():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            platform = request.args.get("platform")
            group_id = request.args.get("group_id")
            limit = int(request.args.get("limit", 50))
            senders = await db.get_distinct_senders(platform=platform, group_id=group_id, limit=limit)
            return jsonify({"success": True, "data": {"senders": senders}})
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取发送者列表失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_groups():
        if not db:
            return jsonify({"success": False, "error": "数据库未初始化"})
        try:
            platform = request.args.get("platform")
            limit = int(request.args.get("limit", 50))
            groups = await db.get_distinct_groups(platform=platform, limit=limit)
            return jsonify({"success": True, "data": {"groups": groups}})
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取群组列表失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def api_media():
        rel_path = request.args.get("path")
        if not rel_path:
            return jsonify({"success": False, "error": "缺少文件路径"}), 400
        media_base = Path(get_astrbot_plugin_data_path()) / PLUGIN_DIR_NAME / "media"
        file_path = media_base / rel_path
        resolved_base = media_base.resolve()
        resolved_path = file_path.resolve()
        try:
            resolved_path.relative_to(resolved_base)
        except ValueError:
            return jsonify({"success": False, "error": "非法路径"}), 403
        if not resolved_path.exists():
            return jsonify({"success": False, "error": "文件不存在"}), 404
        if not resolved_path.is_file():
            return jsonify({"success": False, "error": "非法路径"}), 403
        return await send_file(str(resolved_path))

    async def api_schema_version():
        return jsonify({
            "success": True,
            "data": {
                "schema_version": SCHEMA_VERSION,
                "plugin_version": "2.0.0",
            },
        })

    # ========== Register all APIs ==========

    context.register_web_api(f"{prefix}/stats", api_stats, ["GET"], "获取统计概览")
    context.register_web_api(f"{prefix}/stats/timeline", api_stats_timeline, ["GET"], "获取时间趋势")
    context.register_web_api(f"{prefix}/stats/senders", api_stats_senders, ["GET"], "获取发送者排行")
    context.register_web_api(f"{prefix}/stats/groups", api_stats_groups, ["GET"], "获取群组排行")
    context.register_web_api(f"{prefix}/messages", api_messages, ["GET"], "查询消息列表")
    context.register_web_api(f"{prefix}/message/detail", api_message_detail, ["GET"], "获取消息详情")
    context.register_web_api(f"{prefix}/message/context", api_message_context, ["GET"], "获取消息上下文")
    context.register_web_api(f"{prefix}/search", api_search, ["GET"], "搜索消息")
    context.register_web_api(f"{prefix}/export", api_export, ["POST"], "创建导出任务")
    context.register_web_api(f"{prefix}/export/status", api_export_status, ["GET"], "查询导出状态")
    context.register_web_api(f"{prefix}/export/download", api_export_download, ["GET"], "下载导出文件")
    context.register_web_api(f"{prefix}/export/download_data", api_export_download_data, ["GET"], "获取导出文件数据(base64)")
    context.register_web_api(f"{prefix}/import/upload", api_import_upload, ["POST"], "简单文件导入")
    context.register_web_api(f"{prefix}/import/init", api_import_init, ["POST"], "初始化分片导入")
    context.register_web_api(f"{prefix}/import/chunk/<session_id>/<int:chunk_index>", api_import_chunk, ["POST"], "上传分片")
    context.register_web_api(f"{prefix}/import/complete", api_import_complete, ["POST"], "完成分片导入")
    context.register_web_api(f"{prefix}/import/status", api_import_status, ["GET"], "查询导入状态")
    context.register_web_api(f"{prefix}/platforms", api_platforms, ["GET"], "获取平台列表")
    context.register_web_api(f"{prefix}/senders", api_senders, ["GET"], "获取发送者列表")
    context.register_web_api(f"{prefix}/groups", api_groups, ["GET"], "获取群组列表")
    context.register_web_api(f"{prefix}/media", api_media, ["GET"], "获取媒体文件")
    context.register_web_api(f"{prefix}/schema_version", api_schema_version, ["GET"], "获取数据库Schema版本")

    logger.info(f"[MessageRecorder] 已注册 {21} 个 Web API")


# ========== Export Task Execution ==========

async def _execute_export_task(task_id: str, db: Database, query_filter: QueryFilter, format_type: str, options: dict):
    task = _export_tasks.get(task_id)
    if not task:
        return

    VALID_FORMATS = {"json", "csv", "txt"}
    if format_type not in VALID_FORMATS:
        task["status"] = "failed"
        task["error"] = f"不支持的导出格式: {format_type}"
        task["completed_at"] = time.time()
        return

    try:
        task["status"] = "processing"
        export_dir = _get_plugin_data_dir() / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        include_chain = options.get("include_chain", True)
        include_raw = options.get("include_raw", False)
        include_media = options.get("include_media", False)

        if include_media and format_type == "json":
            file_path = await _export_with_media(task_id, db, query_filter, export_dir, include_chain, include_raw, task)
        elif format_type == "json":
            file_path = await _export_json(task_id, db, query_filter, export_dir, include_chain, include_raw, task)
        elif format_type == "csv":
            file_path = await _export_csv(task_id, db, query_filter, export_dir, task)
        elif format_type == "txt":
            file_path = await _export_txt(task_id, db, query_filter, export_dir, task)

        task["status"] = "completed"
        task["file_path"] = str(file_path)
        task["file_size"] = os.path.getsize(file_path)
        format_type_val = format_type
        ext = "zip" if format_type_val == "json" and options.get("include_media") else format_type_val
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        task["filename"] = f"messages_export_{timestamp}.{ext}"
        task["completed_at"] = time.time()
        logger.info(f"[MessageRecorder Web] 导出任务 {task_id} 完成，共 {task.get('actual_count', 0)} 条记录")
    except asyncio.TimeoutError:
        task["status"] = "failed"
        task["error"] = f"操作超时 ({DB_OPERATION_TIMEOUT}s)"
        task["completed_at"] = time.time()
    except Exception as e:
        logger.error(f"[MessageRecorder Web] 导出任务 {task_id} 失败: {e}")
        task["status"] = "failed"
        task["error"] = str(e)
        task["completed_at"] = time.time()


async def _export_json(task_id, db, query_filter, export_dir, include_chain, include_raw, task):
    file_path = export_dir / f"{task_id}.json"
    count = 0
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("{\n")
        f.write('  "export_info": {\n')
        f.write('    "plugin": "astrbot_plugin_message_recorder",\n')
        f.write('    "version": "2.0.0",\n')
        f.write(f'    "schema_version": {SCHEMA_VERSION},\n')
        f.write(f'    "export_time": {int(time.time() * 1000)},\n')
        f.write(f'    "filters": {json.dumps(task["filter"], ensure_ascii=False)},\n')
        f.write('    "total_records": "PENDING"\n')
        f.write("  },\n")
        f.write('  "messages": [\n')
        first = True
        async for msg in db.query_messages_batch(query_filter):
            if not first:
                f.write(",\n")
            first = False
            msg_dict = _format_message_for_export(msg, include_chain, include_raw)
            f.write("    ")
            f.write(json.dumps(msg_dict, ensure_ascii=False))
            count += 1
            if count % 1000 == 0:
                task["progress"] = f"已导出 {count} 条消息"
        f.write("\n  ]\n")
        f.write("}")
    with open(file_path, "r+", encoding="utf-8") as f:
        content = f.read()
        content = content.replace('"total_records": "PENDING"', f'"total_records": {count}')
        f.seek(0)
        f.write(content)
        f.truncate()
    task["actual_count"] = count
    return file_path


async def _export_csv(task_id, db, query_filter, export_dir, task):
    file_path = export_dir / f"{task_id}.csv"
    count = 0
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "platform", "sender_id", "sender_name", "group_id", "channel_id", "message_type", "message_str", "reply_to_id", "timestamp", "created_at"])
        async for msg in db.query_messages_batch(query_filter):
            writer.writerow([msg.id, msg.platform, msg.sender_id, msg.sender_name or "", msg.group_id or "", msg.channel_id or "", msg.message_type, msg.message_str or "", msg.reply_to_id or "", msg.timestamp, msg.created_at])
            count += 1
            if count % 1000 == 0:
                task["progress"] = f"已导出 {count} 条消息"
    task["actual_count"] = count
    return file_path


async def _export_txt(task_id, db, query_filter, export_dir, task):
    file_path = export_dir / f"{task_id}.txt"
    count = 0
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("=== 导出信息 ===\n")
        f.write("插件: astrbot_plugin_message_recorder\n")
        f.write(f"版本: 2.0.0 (schema v{SCHEMA_VERSION})\n")
        f.write(f"导出时间: {_format_timestamp(int(time.time() * 1000))}\n")
        f.write("总记录数: PENDING\n\n")
        f.write("=== 消息记录 ===\n\n")
        async for msg in db.query_messages_batch(query_filter):
            time_str = _format_timestamp(msg.timestamp)
            group_info = f"[群聊:{msg.group_id}]" if msg.group_id else (f"[频道:{msg.channel_id}]" if msg.channel_id else "[私聊]")
            sender = msg.sender_name or msg.sender_id
            content = msg.message_str or "[非文本消息]"
            platform_icon = _get_platform_icon(msg.platform)
            reply_info = f" ↩{msg.reply_to_id}" if msg.reply_to_id else ""
            f.write(f"[{time_str}] {platform_icon} {group_info} {sender}: {content}{reply_info}\n")
            count += 1
            if count % 1000 == 0:
                task["progress"] = f"已导出 {count} 条消息"
    with open(file_path, "r+", encoding="utf-8") as f:
        content = f.read()
        content = content.replace("总记录数: PENDING", f"总记录数: {count}")
        f.seek(0)
        f.write(content)
        f.truncate()
    task["actual_count"] = count
    return file_path


async def _export_with_media(task_id, db, query_filter, export_dir, include_chain, include_raw, task):
    media_base = Path(get_astrbot_plugin_data_path()) / PLUGIN_DIR_NAME / "media"
    temp_json_path = export_dir / f"{task_id}_temp.json"
    media_files_collected: Dict[str, str] = {}
    count = 0

    with open(temp_json_path, "w", encoding="utf-8") as f:
        f.write("{\n")
        f.write('  "export_info": {\n')
        f.write('    "plugin": "astrbot_plugin_message_recorder",\n')
        f.write('    "version": "2.0.0",\n')
        f.write(f'    "schema_version": {SCHEMA_VERSION},\n')
        f.write(f'    "export_time": {int(time.time() * 1000)},\n')
        f.write(f'    "filters": {json.dumps(task["filter"], ensure_ascii=False)},\n')
        f.write('    "total_records": "PENDING",\n')
        f.write('    "include_media": true\n')
        f.write("  },\n")
        f.write('  "messages": [\n')
        first = True
        async for msg in db.query_messages_batch(query_filter):
            msg_dict = _format_message_for_export(msg, include_chain, include_raw)
            if include_chain:
                chain = msg_dict.get("message_chain")
                if isinstance(chain, list):
                    for comp in chain:
                        if isinstance(comp, dict) and "local_path" in comp:
                            lp = comp["local_path"]
                            if isinstance(lp, str) and lp and lp not in media_files_collected:
                                media_files_collected[lp] = f"media/{lp}"
            if not first:
                f.write(",\n")
            first = False
            f.write("    ")
            f.write(json.dumps(msg_dict, ensure_ascii=False))
            count += 1
            if count % 500 == 0:
                task["progress"] = f"已处理 {count} 条消息"
        f.write("\n  ]\n")
        f.write("}")

    with open(temp_json_path, "r+", encoding="utf-8") as f:
        content = f.read()
        content = content.replace('"total_records": "PENDING"', f'"total_records": {count}')
        f.seek(0)
        f.write(content)
        f.truncate()

    task["progress"] = f"正在打包媒体文件 (共 {len(media_files_collected)} 个)..."

    pkg_path = export_dir / f"{task_id}.zip"
    with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_STORED) as zf:
        zf.write(temp_json_path, "data.json")
        added = 0
        for rel_path, zip_path in media_files_collected.items():
            abs_path = media_base / rel_path
            if abs_path.exists() and abs_path.is_file():
                try:
                    zf.write(abs_path, zip_path)
                    added += 1
                    if added % 100 == 0:
                        task["progress"] = f"已打包 {added}/{len(media_files_collected)} 个媒体文件"
                except Exception as e:
                    logger.warning(f"[MessageRecorder Web] 打包媒体文件失败 {rel_path}: {e}")

    _safe_remove_file(str(temp_json_path))
    task["actual_count"] = count
    task["media_count"] = added
    return pkg_path


# ========== Import Task Execution ==========

async def _execute_import_task(task_id: str, db: Database, file_path: str, mode: str):
    MAX_FIELD_LENGTH = 65535
    VALID_MESSAGE_TYPES = {"group", "private", "channel", "forum"}

    def sanitize_import_record(record: dict) -> Optional[dict]:
        if not isinstance(record, dict):
            return None
        platform = str(record.get("platform", "unknown")).strip()[:64]
        if not platform:
            platform = "unknown"
        message_type = str(record.get("message_type", "group")).strip().lower()
        if message_type not in VALID_MESSAGE_TYPES:
            message_type = "group"
        message_str = record.get("message_str")
        if message_str is not None:
            message_str = str(message_str)[:MAX_FIELD_LENGTH]
        sender_name = record.get("sender_name")
        if sender_name is not None:
            sender_name = str(sender_name)[:256]
        message_chain = record.get("message_chain")
        if message_chain is not None:
            if not isinstance(message_chain, (list, dict)):
                try:
                    message_chain = json.loads(str(message_chain))
                except (json.JSONDecodeError, TypeError):
                    message_chain = None
        raw_message = record.get("raw_message")
        if raw_message is not None:
            if not isinstance(raw_message, (list, dict)):
                try:
                    raw_message = json.loads(str(raw_message))
                except (json.JSONDecodeError, TypeError):
                    raw_message = None
        channel_id = record.get("channel_id")
        if channel_id is not None:
            channel_id = str(channel_id).strip()[:128] or None
        reply_to_id = record.get("reply_to_id")
        if reply_to_id is not None:
            reply_to_id = str(reply_to_id).strip()[:128] or None
        return {
            "platform": platform,
            "message_id": str(record.get("message_id", ""))[:128],
            "session_id": str(record.get("session_id", ""))[:128],
            "group_id": str(record.get("group_id"))[:128] if record.get("group_id") else None,
            "channel_id": channel_id,
            "sender_id": str(record.get("sender_id", ""))[:128],
            "sender_name": sender_name,
            "message_type": message_type,
            "message_str": message_str,
            "message_chain": message_chain,
            "raw_message": raw_message,
            "reply_to_id": reply_to_id,
            "timestamp": record.get("timestamp"),
            "created_at": record.get("created_at"),
        }

    task = _import_tasks.get(task_id)
    if not task:
        return

    try:
        task["status"] = "processing"
        records = []
        file_ext = Path(file_path).suffix.lower()
        media_restored = 0

        if file_ext == ".mrpkg":
            records, media_restored = await _import_mrpkg(file_path)
        elif file_ext == ".json":
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "messages" in data:
                    records = data["messages"]
                elif isinstance(data, list):
                    records = data
        elif file_ext == ".csv":
            with open(file_path, encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                records = list(reader)
        else:
            task["status"] = "failed"
            task["error"] = "不支持的文件格式"
            return

        task["total_records"] = len(records)

        if mode == "replace":
            task["error"] = "replace 模式暂不支持"
            task["status"] = "failed"
            return

        imported = 0
        skipped = 0
        errors = 0

        if mode == "skip_duplicates":
            platform_message_map: dict = {}
            for i, record in enumerate(records):
                sanitized = sanitize_import_record(record)
                if sanitized is None:
                    errors += 1
                    continue
                platform = sanitized["platform"]
                message_id = sanitized["message_id"]
                if message_id:
                    if platform not in platform_message_map:
                        platform_message_map[platform] = {}
                    platform_message_map[platform][message_id] = (i, sanitized)

            existing_ids_by_platform: dict = {}
            for platform, msg_map in platform_message_map.items():
                try:
                    existing_ids = await asyncio.wait_for(
                        db.get_existing_message_ids(list(msg_map.keys()), platform),
                        timeout=DB_OPERATION_TIMEOUT,
                    )
                    existing_ids_by_platform[platform] = existing_ids
                except Exception as e:
                    logger.warning(f"[MessageRecorder Web] 查询平台 {platform} 已存在消息失败: {e}")
                    existing_ids_by_platform[platform] = set()

            for platform, msg_map in platform_message_map.items():
                existing_ids = existing_ids_by_platform.get(platform, set())
                for message_id, (original_index, sanitized) in msg_map.items():
                    task["processed"] = original_index + 1
                    if message_id in existing_ids:
                        skipped += 1
                        continue
                    try:
                        msg_record = MessageRecord(
                            platform=platform,
                            message_id=message_id,
                            session_id=sanitized["session_id"],
                            group_id=sanitized["group_id"],
                            channel_id=sanitized["channel_id"],
                            sender_id=sanitized["sender_id"],
                            sender_name=sanitized["sender_name"],
                            message_type=sanitized["message_type"],
                            message_str=sanitized["message_str"],
                            message_chain=json.dumps(sanitized["message_chain"]) if sanitized["message_chain"] else None,
                            raw_message=json.dumps(sanitized["raw_message"]) if sanitized["raw_message"] else None,
                            reply_to_id=sanitized["reply_to_id"],
                            timestamp=normalize_timestamp(sanitized["timestamp"]),
                            created_at=normalize_timestamp(sanitized["created_at"]),
                        )
                        saved_id = await asyncio.wait_for(db.save_message(msg_record), timeout=IMPORT_RECORD_TIMEOUT)
                        if saved_id == -1:
                            skipped += 1
                        else:
                            imported += 1
                    except asyncio.TimeoutError:
                        errors += 1
                    except Exception:
                        errors += 1
        else:
            for i, record in enumerate(records):
                task["processed"] = i + 1
                try:
                    sanitized = sanitize_import_record(record)
                    if sanitized is None:
                        errors += 1
                        continue
                    msg_record = MessageRecord(
                        platform=sanitized["platform"],
                        message_id=sanitized["message_id"],
                        session_id=sanitized["session_id"],
                        group_id=sanitized["group_id"],
                        channel_id=sanitized["channel_id"],
                        sender_id=sanitized["sender_id"],
                        sender_name=sanitized["sender_name"],
                        message_type=sanitized["message_type"],
                        message_str=sanitized["message_str"],
                        message_chain=json.dumps(sanitized["message_chain"]) if sanitized["message_chain"] else None,
                        raw_message=json.dumps(sanitized["raw_message"]) if sanitized["raw_message"] else None,
                        reply_to_id=sanitized["reply_to_id"],
                        timestamp=normalize_timestamp(sanitized["timestamp"]),
                        created_at=normalize_timestamp(sanitized["created_at"]),
                    )
                    saved_id = await asyncio.wait_for(db.save_message(msg_record), timeout=IMPORT_RECORD_TIMEOUT)
                    if saved_id == -1:
                        skipped += 1
                    else:
                        imported += 1
                except asyncio.TimeoutError:
                    errors += 1
                except Exception:
                    errors += 1

        task["status"] = "completed"
        task["imported"] = imported
        task["skipped"] = skipped
        task["errors"] = errors
        task["media_restored"] = media_restored
        task["completed_at"] = time.time()
        _safe_remove_file(file_path)

        logger.info(f"[MessageRecorder Web] 导入任务 {task_id} 完成: 导入 {imported}, 跳过 {skipped}, 错误 {errors}")
    except Exception as e:
        logger.error(f"[MessageRecorder Web] 导入任务 {task_id} 失败: {e}")
        task["status"] = "failed"
        task["error"] = str(e)
        task["completed_at"] = time.time()


async def _import_mrpkg(file_path: str) -> tuple:
    media_base = Path(get_astrbot_plugin_data_path()) / PLUGIN_DIR_NAME / "media"
    records = []
    media_restored = 0

    with zipfile.ZipFile(file_path, "r") as zf:
        if "data.json" not in zf.namelist():
            raise ValueError("无效的 .mrpkg 包：缺少 data.json")
        with zf.open("data.json") as f:
            data = json.loads(f.read().decode("utf-8"))
        if isinstance(data, dict) and "messages" in data:
            records = data["messages"]
        elif isinstance(data, list):
            records = data

        for name in zf.namelist():
            if not name.startswith("media/"):
                continue
            rel_path = name[len("media/"):]
            if not rel_path:
                continue
            if ".." in Path(rel_path).parts or rel_path.startswith("/"):
                continue
            target_path = media_base / rel_path
            try:
                target_path.resolve().relative_to(media_base.resolve())
            except ValueError:
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with zf.open(name) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                media_restored += 1
            except Exception as e:
                logger.warning(f"[MessageRecorder Web] 恢复媒体文件失败 {rel_path}: {e}")

    return records, media_restored


async def cleanup_expired_tasks():
    while True:
        try:
            await asyncio.sleep(600)
            current_time = time.time()

            expired_tasks = []
            for task_id, task in list(_export_tasks.items()):
                completed_at = task.get("completed_at", 0)
                if completed_at and current_time - completed_at > MAX_EXPORT_FILE_AGE:
                    expired_tasks.append(task_id)
                    file_path = task.get("file_path")
                    if file_path and os.path.exists(file_path):
                        _safe_remove_file(file_path)
            for task_id in expired_tasks:
                _export_tasks.pop(task_id, None)
            if expired_tasks:
                logger.info(f"[MessageRecorder Web] 已清理 {len(expired_tasks)} 个过期导出任务")

            expired_sessions = []
            for session_id, session in list(_chunk_sessions.items()):
                created_at = session.get("created_at", 0)
                if current_time - created_at > CHUNK_SESSION_MAX_AGE:
                    expired_sessions.append(session_id)
                    chunks_dir = session.get("chunks_dir")
                    if chunks_dir and os.path.exists(chunks_dir):
                        try:
                            shutil.rmtree(chunks_dir, ignore_errors=True)
                        except Exception as e:
                            logger.warning(f"[MessageRecorder Web] 清理分片目录失败: {e}")
            for session_id in expired_sessions:
                _chunk_sessions.pop(session_id, None)

            expired_imports = []
            for task_id, task in list(_import_tasks.items()):
                completed_at = task.get("completed_at", 0)
                if completed_at and current_time - completed_at > MAX_EXPORT_FILE_AGE:
                    expired_imports.append(task_id)
            for task_id in expired_imports:
                _import_tasks.pop(task_id, None)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 清理过期文件任务出错: {e}")
