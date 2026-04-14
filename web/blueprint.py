"""Quart Blueprint 定义"""

import os
import asyncio
import shutil
import uuid
import time
import json
import csv
import zipfile
import secrets
import hashlib
import string
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from quart import Blueprint, jsonify, request, render_template, send_file, session

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from ..database import Database
from ..models import QueryFilter, MessageRecord, PLUGIN_DIR_NAME
from ..time_utils import parse_time_range, normalize_timestamp
from ..media_downloader import MediaDownloader


# 安全配置
MAX_IMPORT_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
MAX_EXPORT_FILE_AGE = 3600  # 导出文件有效期 1 小时
ALLOWED_IMPORT_EXTENSIONS = {".json", ".csv", ".mrpkg"}
CHUNK_SIZE = 5 * 1024 * 1024  # 分片大小 5MB

# 验证码配置
CAPTCHA_LENGTH = 6
CAPTCHA_EXPIRE_SECONDS = 300  # 验证码有效期 5 分钟
AUTH_TOKEN_EXPIRE_SECONDS = 1800  # 认证 token 有效期 30 分钟

# 验证码存储: {captcha_id: {"code": "xxxx", "created_at": timestamp}}
_captcha_store: Dict[str, Dict[str, Any]] = {}

# 认证 token 存储: {token_hash: {"created_at": timestamp}}
_auth_tokens: Dict[str, Dict[str, Any]] = {}

# 导出任务存储
_export_tasks: Dict[str, Dict[str, Any]] = {}

# 分片上传会话存储
_chunk_sessions: Dict[str, Dict[str, Any]] = {}
_import_tasks: Dict[str, Dict[str, Any]] = {}

# 当前模块所在目录（web/blueprint.py 的父目录的父目录就是插件根目录）
_current_dir = Path(__file__).resolve().parent.parent


def get_plugin_dir() -> Path:
    """获取插件目录路径（使用当前模块位置）"""
    return _current_dir


def get_plugin_data_dir() -> Path:
    """获取插件数据目录路径"""
    return Path(get_astrbot_plugin_data_path()) / PLUGIN_DIR_NAME


def _safe_remove_file(file_path: str, max_retries: int = 3, delay: float = 0.5) -> bool:
    """安全删除文件，带重试机制"""
    for attempt in range(max_retries):
        try:
            os.remove(file_path)
            return True
        except OSError as e:
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                logger.debug(f"[MessageRecorder Web] 清理临时文件失败（重试 {max_retries} 次）: {file_path}, {e}")
                return False
    return False


def _cleanup_temp_dir():
    """启动时清理残留的临时文件"""
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


def _generate_captcha_code(length: int = CAPTCHA_LENGTH) -> str:
    """生成随机验证码"""
    return "".join(secrets.choice(string.digits) for _ in range(length))


def _generate_captcha_id() -> str:
    """生成验证码 ID"""
    return uuid.uuid4().hex[:16]


def _generate_auth_token() -> str:
    """生成认证 token"""
    return secrets.token_urlsafe(32)


def _hash_token(token: str) -> str:
    """对 token 进行哈希"""
    return hashlib.sha256(token.encode()).hexdigest()


def _create_captcha() -> str:
    """创建验证码，返回 captcha_id，验证码打印到控制台"""
    captcha_id = _generate_captcha_id()
    code = _generate_captcha_code()
    _captcha_store[captcha_id] = {
        "code": code,
        "created_at": time.time(),
    }
    logger.info(f"[MessageRecorder Web] 验证码: {code} (ID: {captcha_id})")
    return captcha_id


def _verify_captcha(captcha_id: str, code: str) -> bool:
    """验证验证码"""
    captcha = _captcha_store.get(captcha_id)
    if not captcha:
        return False

    if time.time() - captcha["created_at"] > CAPTCHA_EXPIRE_SECONDS:
        _captcha_store.pop(captcha_id, None)
        return False

    if captcha["code"] != code:
        return False

    _captcha_store.pop(captcha_id, None)
    return True


def _create_auth_token() -> str:
    """创建认证 token"""
    token = _generate_auth_token()
    token_hash = _hash_token(token)
    _auth_tokens[token_hash] = {
        "created_at": time.time(),
    }
    return token


def _verify_auth_token(token: str) -> bool:
    """验证认证 token"""
    if not token:
        return False

    token_hash = _hash_token(token)
    auth = _auth_tokens.get(token_hash)

    if not auth:
        return False

    if time.time() - auth["created_at"] > AUTH_TOKEN_EXPIRE_SECONDS:
        _auth_tokens.pop(token_hash, None)
        return False

    return True


def _cleanup_expired_captchas_and_tokens():
    """清理过期的验证码和 token"""
    current_time = time.time()

    expired_captchas = [
        cid for cid, c in _captcha_store.items()
        if current_time - c["created_at"] > CAPTCHA_EXPIRE_SECONDS
    ]
    for cid in expired_captchas:
        _captcha_store.pop(cid, None)

    expired_tokens = [
        th for th, a in _auth_tokens.items()
        if current_time - a["created_at"] > AUTH_TOKEN_EXPIRE_SECONDS
    ]
    for th in expired_tokens:
        _auth_tokens.pop(th, None)


def create_blueprint(plugin_instance) -> Blueprint:
    """创建消息记录器 Web Blueprint"""
    plugin_dir = get_plugin_dir()

    logger.info(f"[MessageRecorder Web] 插件目录: {plugin_dir}")

    _cleanup_temp_dir()

    bp = Blueprint(
        "message_recorder_web",
        __name__,
        template_folder=str(plugin_dir / "templates"),
        static_folder=str(plugin_dir / "static"),
        static_url_path="/static"
    )

    def get_db() -> Optional[Database]:
        return plugin_instance._db

    _WRITE_ENDPOINT_PREFIXES = ("/api/import",)

    @bp.before_request
    async def check_write_auth():
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return None
        if not any(request.path.startswith(prefix) for prefix in _WRITE_ENDPOINT_PREFIXES):
            return None

        if request.path in ("/api/captcha", "/api/captcha/verify"):
            return None

        token = request.headers.get("X-Auth-Token", "") or request.args.get("auth_token", "")
        if not _verify_auth_token(token):
            return jsonify({
                "success": False,
                "error": "需要验证码鉴权",
                "require_captcha": True
            }), 401

    # 主页面 - 仪表盘
    @bp.route("/")
    async def index():
        try:
            return await render_template("index.html")
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 渲染主页模板失败: {e}")
            return f"<h1>模板渲染错误</h1><p>{str(e)}</p><p>模板目录: {bp.template_folder}</p>", 500

    # 搜索页面
    @bp.route("/search")
    async def search_page():
        return await render_template("search.html")

    # 导出页面
    @bp.route("/export")
    async def export_page():
        return await render_template("export.html")

    # 导入页面
    @bp.route("/import")
    async def import_page():
        return await render_template("import.html")

    # ========== 统计 API ==========

    @bp.route("/api/stats")
    async def api_stats():
        """获取总体统计信息"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            stats = await get_db().get_stats()

            # 格式化时间
            time_range = {}
            if stats.oldest_timestamp:
                time_range["start"] = format_timestamp(stats.oldest_timestamp)
            if stats.newest_timestamp:
                time_range["end"] = format_timestamp(stats.newest_timestamp)

            return jsonify({
                "success": True,
                "data": {
                    "total_count": stats.total_count,
                    "group_message_count": stats.group_message_count,
                    "private_message_count": stats.private_message_count,
                    "platform_stats": stats.platform_stats,
                    "platform_count": len(stats.platform_stats),
                    "oldest_timestamp": stats.oldest_timestamp,
                    "newest_timestamp": stats.newest_timestamp,
                    "time_range": time_range
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取统计失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/stats/timeline")
    async def api_stats_timeline():
        """获取时间趋势数据"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            interval = request.args.get("interval", "day")
            platform = request.args.get("platform")
            group_id = request.args.get("group_id")
            start_time = request.args.get("start_time")
            end_time = request.args.get("end_time")

            # 解析时间参数
            start_ts = int(start_time) if start_time else None
            end_ts = int(end_time) if end_time else None

            points = await get_db().get_timeline_stats(
                interval=interval,
                start_time=start_ts,
                end_time=end_ts,
                platform=platform,
                group_id=group_id
            )

            return jsonify({
                "success": True,
                "data": {
                    "interval": interval,
                    "points": points,
                    "total_points": len(points)
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取时间趋势失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/stats/senders")
    async def api_stats_senders():
        """获取发送者排行"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            limit = int(request.args.get("limit", 20))
            time_range = request.args.get("time")
            platform = request.args.get("platform")
            group_id = request.args.get("group_id")

            start_time, end_time = None, None
            if time_range:
                start_time, end_time = parse_time_range(time_range)

            senders = await get_db().get_sender_ranking(
                limit=limit,
                start_time=start_time,
                end_time=end_time,
                platform=platform,
                group_id=group_id
            )

            return jsonify({
                "success": True,
                "data": {
                    "senders": senders,
                    "total": len(senders)
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取发送者排行失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/stats/groups")
    async def api_stats_groups():
        """获取群组活跃统计"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            limit = int(request.args.get("limit", 20))
            time_range = request.args.get("time")
            platform = request.args.get("platform")

            start_time, end_time = None, None
            if time_range:
                start_time, end_time = parse_time_range(time_range)

            groups = await get_db().get_group_ranking(
                limit=limit,
                start_time=start_time,
                end_time=end_time,
                platform=platform
            )

            return jsonify({
                "success": True,
                "data": {
                    "groups": groups,
                    "total": len(groups)
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取群组统计失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # ========== 消息查询 API ==========

    @bp.route("/api/messages")
    async def api_messages():
        """查询消息列表"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            # 构建查询过滤器
            query_filter = build_query_filter(request.args)

            # 查询消息
            messages = await get_db().query_messages(query_filter)

            # 获取总数（用于分页）
            total = await get_db().count_messages(query_filter)

            # 格式化消息数据
            formatted_messages = [format_message(msg) for msg in messages]

            return jsonify({
                "success": True,
                "data": {
                    "messages": formatted_messages,
                    "pagination": {
                        "total": total,
                        "limit": query_filter.limit,
                        "offset": query_filter.offset,
                        "has_more": query_filter.offset + query_filter.limit < total
                    }
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 查询消息失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/messages/<int:message_id>")
    async def api_message_detail(message_id: int):
        """获取单条消息详情"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            message = await get_db().get_message_by_id(message_id)

            if not message:
                return jsonify({"success": False, "error": "消息不存在"}), 404

            return jsonify({
                "success": True,
                "data": format_message_detail(message)
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取消息详情失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/messages/<int:message_id>/context")
    async def api_message_context(message_id: int):
        """获取消息上下文"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            before = int(request.args.get("before", 5))
            after = int(request.args.get("after", 5))

            context = await get_db().get_context_messages(message_id, before, after)

            return jsonify({
                "success": True,
                "data": {
                    "target": format_message_detail(await get_db().get_message_by_id(message_id)),
                    "before": [format_message(m) for m in context["before"]],
                    "after": [format_message(m) for m in context["after"]]
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取消息上下文失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # ========== 搜索 API ==========

    @bp.route("/api/search")
    async def api_search():
        """关键词搜索"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            keyword = request.args.get("keyword", "")
            if not keyword:
                return jsonify({"success": False, "error": "缺少关键词"}), 400

            query_filter = build_query_filter(request.args)
            query_filter.keyword = keyword

            messages = await get_db().query_messages(query_filter)
            total = await get_db().count_messages(query_filter)

            return jsonify({
                "success": True,
                "data": {
                    "messages": [format_message(msg) for msg in messages],
                    "pagination": {
                        "total": total,
                        "limit": query_filter.limit,
                        "offset": query_filter.offset,
                        "has_more": query_filter.offset + query_filter.limit < total
                    },
                    "keyword": keyword
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 搜索失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # ========== 导出 API ==========

    @bp.route("/api/export", methods=["POST"])
    async def api_export():
        """创建导出任务"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            data = await request.get_json()
            format_type = data.get("format", "json")
            filters = data.get("filters", {})
            options = data.get("options", {})

            # 构建查询过滤器
            query_filter = build_query_filter_from_dict(filters)

            # 获取预估数量
            estimated_count = await get_db().count_messages(query_filter)

            # 创建任务 ID
            task_id = f"export_{uuid.uuid4().hex[:12]}"

            # 创建任务记录
            _export_tasks[task_id] = {
                "status": "pending",
                "format": format_type,
                "filter": filters,
                "options": options,
                "estimated_count": estimated_count,
                "created_at": time.time(),
                "completed_at": None,
                "file_path": None,
                "error": None
            }

            # 异步执行导出
            asyncio.create_task(
                execute_export_task(task_id, get_db(), query_filter, format_type, options)
            )

            return jsonify({
                "success": True,
                "data": {
                    "task_id": task_id,
                    "status": "pending",
                    "estimated_count": estimated_count,
                    "estimated_size": estimate_size(estimated_count, format_type)
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 创建导出任务失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/export/status/<task_id>")
    async def api_export_status(task_id: str):
        """获取导出任务状态"""
        task = _export_tasks.get(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        return jsonify({
            "success": True,
            "data": task
        })

    @bp.route("/api/export/download/<task_id>")
    async def api_export_download(task_id: str):
        """下载导出文件"""
        task = _export_tasks.get(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        if task["status"] != "completed":
            return jsonify({"success": False, "error": "导出未完成"}), 400

        # 安全检查：时效限制
        completed_at = task.get("completed_at", 0)
        file_age = time.time() - completed_at
        if file_age > MAX_EXPORT_FILE_AGE:
            # 删除过期文件
            file_path = task.get("file_path")
            if file_path and os.path.exists(file_path):
                _safe_remove_file(file_path)
            _export_tasks.pop(task_id, None)
            return jsonify({
                "success": False,
                "error": "导出文件已过期，请重新导出"
            }), 410  # 410 Gone

        file_path = task.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return jsonify({"success": False, "error": "文件不存在"}), 404

        actual_ext = Path(file_path).suffix.lstrip(".")
        filename = f"message_export_{task_id}.{actual_ext}"

        return await send_file(file_path, as_attachment=True, attachment_filename=filename)

    # ========== 验证码鉴权 API ==========

    @bp.route("/api/captcha", methods=["GET"])
    async def api_get_captcha():
        """获取验证码 ID，验证码打印到控制台"""
        _cleanup_expired_captchas_and_tokens()

        captcha_id = _create_captcha()
        return jsonify({
            "success": True,
            "captcha_id": captcha_id,
            "expires_in": CAPTCHA_EXPIRE_SECONDS
        })

    @bp.route("/api/captcha/verify", methods=["POST"])
    async def api_verify_captcha():
        """验证验证码并获取认证 token"""
        data = await request.get_json(silent=True) or {}
        captcha_id = data.get("captcha_id", "")
        code = data.get("code", "")

        if not captcha_id or not code:
            return jsonify({"success": False, "error": "缺少验证码参数"}), 400

        if not _verify_captcha(captcha_id, code):
            return jsonify({"success": False, "error": "验证码错误或已过期"}), 400

        token = _create_auth_token()
        return jsonify({
            "success": True,
            "auth_token": token,
            "expires_in": AUTH_TOKEN_EXPIRE_SECONDS
        })

    # ========== 导入 API ==========

    @bp.route("/api/import", methods=["POST"])
    async def api_import():
        """创建导入任务"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            # 获取上传文件
            files = await request.files
            if "file" not in files:
                return jsonify({"success": False, "error": "缺少文件"}), 400

            file = files["file"]
            mode = request.form.get("mode", "merge")

            # 安全检查：文件大小限制
            if file.content_length and file.content_length > MAX_IMPORT_FILE_SIZE:
                return jsonify({
                    "success": False,
                    "error": f"文件大小超过限制（最大 {MAX_IMPORT_FILE_SIZE // (1024*1024)}MB）"
                }), 400

            # 安全检查：文件名处理（防止路径遍历）
            original_filename = file.filename or "unknown"
            safe_filename = Path(original_filename).name  # 只取文件名，去除路径部分
            file_ext = Path(safe_filename).suffix.lower()

            # 安全检查：文件扩展名白名单
            if file_ext not in ALLOWED_IMPORT_EXTENSIONS:
                return jsonify({
                    "success": False,
                    "error": f"不支持的文件格式，仅支持 JSON、CSV 和 MRPKG"
                }), 400

            # 创建任务 ID
            task_id = f"import_{uuid.uuid4().hex[:12]}"

            # 保存临时文件（使用安全的文件名）
            temp_dir = get_plugin_data_dir() / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file = temp_dir / f"{task_id}{file_ext}"  # 只使用 task_id + 扩展名，不包含原始文件名

            await file.save(str(temp_file))

            # 再次检查文件大小（实际保存后）
            actual_size = temp_file.stat().st_size
            if actual_size > MAX_IMPORT_FILE_SIZE:
                # 删除超大的临时文件
                temp_file.unlink()
                return jsonify({
                    "success": False,
                    "error": f"文件大小超过限制（最大 {MAX_IMPORT_FILE_SIZE // (1024*1024)}MB）"
                }), 400

            # 创建任务记录
            _import_tasks[task_id] = {
                "status": "pending",
                "mode": mode,
                "filename": safe_filename,  # 存储安全的文件名用于显示
                "file_path": str(temp_file),
                "created_at": time.time(),
                "total_records": 0,
                "processed": 0,
                "imported": 0,
                "skipped": 0,
                "errors": 0,
                "completed_at": None,
                "error": None
            }

            # 异步执行导入
            asyncio.create_task(
                execute_import_task(task_id, get_db(), str(temp_file), mode)
            )

            return jsonify({
                "success": True,
                "data": {
                    "task_id": task_id,
                    "status": "pending",
                    "filename": safe_filename,
                    "mode": mode,
                    "file_size": actual_size
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 创建导入任务失败: {e}")
            return jsonify({"success": False, "error": "服务器内部错误"}), 500

    @bp.route("/api/import/status/<task_id>")
    async def api_import_status(task_id: str):
        """获取导入任务状态"""
        task = _import_tasks.get(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        return jsonify({
            "success": True,
            "data": task
        })

    # ========== 分片上传 API ==========

    @bp.route("/api/import/chunk/init", methods=["POST"])
    async def api_chunk_init():
        """初始化分片上传会话"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            data = await request.get_json()
            filename = data.get("filename", "")
            file_size = data.get("file_size", 0)
            mode = data.get("mode", "merge")

            if file_size > MAX_IMPORT_FILE_SIZE:
                max_gb = MAX_IMPORT_FILE_SIZE // (1024 * 1024 * 1024)
                return jsonify({
                    "success": False,
                    "error": f"文件大小超过限制（最大 {max_gb}GB）"
                }), 400

            safe_filename = Path(filename).name
            file_ext = Path(safe_filename).suffix.lower()
            if file_ext not in ALLOWED_IMPORT_EXTENSIONS:
                return jsonify({
                    "success": False,
                    "error": "不支持的文件格式，仅支持 JSON、CSV 和 MRPKG"
                }), 400

            session_id = f"chunk_{uuid.uuid4().hex[:12]}"
            total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE if file_size > 0 else 1

            temp_dir = get_plugin_data_dir() / "temp" / "chunks"
            temp_dir.mkdir(parents=True, exist_ok=True)
            chunks_dir = temp_dir / session_id
            chunks_dir.mkdir(parents=True, exist_ok=True)

            _chunk_sessions[session_id] = {
                "filename": safe_filename,
                "file_size": file_size,
                "file_ext": file_ext,
                "mode": mode,
                "total_chunks": total_chunks,
                "uploaded_chunks": [],
                "chunks_dir": str(chunks_dir),
                "created_at": time.time(),
            }

            return jsonify({
                "success": True,
                "data": {
                    "session_id": session_id,
                    "total_chunks": total_chunks,
                    "chunk_size": CHUNK_SIZE,
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 初始化分片上传失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/import/chunk/upload", methods=["POST"])
    async def api_chunk_upload():
        """上传单个分片"""
        try:
            files = await request.files
            if "chunk" not in files:
                return jsonify({"success": False, "error": "缺少分片数据"}), 400

            session_id = request.form.get("session_id", "")
            chunk_index = int(request.form.get("chunk_index", -1))

            session = _chunk_sessions.get(session_id)
            if not session:
                return jsonify({"success": False, "error": "上传会话不存在或已过期"}), 404

            if chunk_index < 0 or chunk_index >= session["total_chunks"]:
                return jsonify({"success": False, "error": "无效的分片索引"}), 400

            chunk_file = files["chunk"]
            chunk_path = Path(session["chunks_dir"]) / f"{chunk_index:06d}"
            await chunk_file.save(str(chunk_path))

            if chunk_index not in session["uploaded_chunks"]:
                session["uploaded_chunks"].append(chunk_index)

            return jsonify({
                "success": True,
                "data": {
                    "session_id": session_id,
                    "chunk_index": chunk_index,
                    "uploaded_count": len(session["uploaded_chunks"]),
                    "total_chunks": session["total_chunks"],
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 上传分片失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/import/chunk/complete", methods=["POST"])
    async def api_chunk_complete():
        """完成分片上传，组装文件并开始导入"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            data = await request.get_json()
            session_id = data.get("session_id", "")

            session = _chunk_sessions.get(session_id)
            if not session:
                return jsonify({"success": False, "error": "上传会话不存在或已过期"}), 404

            if len(session["uploaded_chunks"]) < session["total_chunks"]:
                missing = set(range(session["total_chunks"])) - set(session["uploaded_chunks"])
                return jsonify({
                    "success": False,
                    "error": f"尚有 {len(missing)} 个分片未上传"
                }), 400

            task_id = f"import_{uuid.uuid4().hex[:12]}"
            temp_dir = get_plugin_data_dir() / "temp"
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
                return jsonify({
                    "success": False,
                    "error": f"文件大小超过限制（最大 {max_gb}GB）"
                }), 400

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
                "error": None
            }

            asyncio.create_task(
                execute_import_task(task_id, get_db(), str(assembled_file), session["mode"])
            )

            return jsonify({
                "success": True,
                "data": {
                    "task_id": task_id,
                    "status": "pending",
                    "filename": session["filename"],
                    "mode": session["mode"],
                    "file_size": actual_size,
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 完成分片上传失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # ========== 元数据 API ==========

    @bp.route("/api/platforms")
    async def api_platforms():
        """获取所有平台列表"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            platforms = await get_db().get_distinct_platforms()
            return jsonify({
                "success": True,
                "data": {"platforms": platforms}
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取平台列表失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/senders")
    async def api_senders():
        """获取发送者列表"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            platform = request.args.get("platform")
            group_id = request.args.get("group_id")
            limit = int(request.args.get("limit", 50))

            senders = await get_db().get_distinct_senders(platform=platform, group_id=group_id, limit=limit)
            return jsonify({
                "success": True,
                "data": {"senders": senders}
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取发送者列表失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/groups")
    async def api_groups():
        """获取群组列表"""
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            platform = request.args.get("platform")
            limit = int(request.args.get("limit", 50))

            groups = await get_db().get_distinct_groups(platform=platform, limit=limit)
            return jsonify({
                "success": True,
                "data": {"groups": groups}
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取群组列表失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/media/<path:rel_path>")
    async def api_media(rel_path: str):
        """访问媒体文件"""
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

    return bp


# ========== 辅助函数 ==========

def format_timestamp(ts: int) -> str:
    """格式化时间戳"""
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")


def format_message(msg: MessageRecord) -> dict:
    """格式化消息（简化版）"""
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


def format_message_detail(msg: MessageRecord) -> dict:
    """格式化消息详情（完整版）"""
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


def build_query_filter(args: dict) -> QueryFilter:
    """从请求参数构建查询过滤器"""
    # 处理平台参数
    platform = args.get("platform")
    platforms_str = args.get("platforms")
    platforms = platforms_str.split(",") if platforms_str else None

    # 处理发送者参数
    sender_id = args.get("sender_id")
    sender_ids_str = args.get("sender_ids")
    sender_ids = sender_ids_str.split(",") if sender_ids_str else None

    # 处理群组参数
    group_id = args.get("group_id")
    group_ids_str = args.get("group_ids")
    group_ids = group_ids_str.split(",") if group_ids_str else None

    # 处理会话参数
    session_id = args.get("session_id")
    session_ids_str = args.get("session_ids")
    session_ids = session_ids_str.split(",") if session_ids_str else None

    # 处理时间参数
    time_range = args.get("time")
    start_time = int(args.get("start_time", 0)) if args.get("start_time") else None
    end_time = int(args.get("end_time", 0)) if args.get("end_time") else None

    # 处理分页参数
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


def build_query_filter_from_dict(data: dict) -> QueryFilter:
    """从字典构建查询过滤器"""
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
        limit=min(data.get("limit", 1000), 10000),
        offset=data.get("offset", 0),
        order=data.get("order", "desc")
    )


def estimate_size(count: int, format_type: str) -> str:
    """预估导出文件大小"""
    # 埇 rough estimates
    avg_size_per_record = {
        "json": 500,  # JSON 格式较大
        "csv": 200,   # CSV 较紧凑
        "txt": 150    # TXT 最简洁
    }
    estimated_bytes = count * avg_size_per_record.get(format_type, 500)

    if estimated_bytes < 1024:
        return f"{estimated_bytes} B"
    elif estimated_bytes < 1024 * 1024:
        return f"{estimated_bytes / 1024:.1f} KB"
    else:
        return f"{estimated_bytes / (1024 * 1024):.1f} MB"


async def execute_export_task(task_id: str, db: Database, query_filter: QueryFilter, format_type: str, options: dict):
    """执行导出任务"""
    import json
    import csv
    import io

    task = _export_tasks.get(task_id)
    if not task:
        return

    try:
        task["status"] = "processing"

        messages = await db.query_messages(query_filter)

        export_dir = get_plugin_data_dir() / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        include_chain = options.get("include_chain", True)
        include_raw = options.get("include_raw", False)
        include_media = options.get("include_media", False)

        if include_media and format_type == "json":
            file_path = await _export_with_media(
                task_id, db, messages, export_dir,
                include_chain, include_raw, task,
            )
        elif format_type == "json":
            export_data = {
                "export_info": {
                    "plugin": "astrbot_plugin_message_recorder",
                    "version": "1.0.0",
                    "export_time": int(time.time() * 1000),
                    "filters": task["filter"],
                    "total_records": len(messages)
                },
                "messages": []
            }

            for msg in messages:
                msg_dict = format_message_detail(msg) if include_chain or include_raw else format_message(msg)
                if not include_chain:
                    msg_dict.pop("message_chain", None)
                if not include_raw:
                    msg_dict.pop("raw_message", None)
                export_data["messages"].append(msg_dict)

            file_path = export_dir / f"{task_id}.{format_type}"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

        elif format_type == "csv":
            file_path = export_dir / f"{task_id}.{format_type}"
            with open(file_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "id", "platform", "sender_id", "sender_name", "group_id",
                    "message_type", "message_str", "timestamp", "created_at"
                ])
                for msg in messages:
                    writer.writerow([
                        msg.id, msg.platform, msg.sender_id, msg.sender_name or "",
                        msg.group_id or "", msg.message_type, msg.message_str or "",
                        msg.timestamp, msg.created_at
                    ])

        elif format_type == "txt":
            file_path = export_dir / f"{task_id}.{format_type}"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("=== 导出信息 ===\n")
                f.write(f"插件: astrbot_plugin_message_recorder\n")
                f.write(f"导出时间: {format_timestamp(int(time.time() * 1000))}\n")
                f.write(f"总记录数: {len(messages)}\n\n")
                f.write("=== 消息记录 ===\n\n")

                for msg in messages:
                    time_str = format_timestamp(msg.timestamp)
                    group_info = f"[群聊:{msg.group_id}]" if msg.group_id else "[私聊]"
                    sender = msg.sender_name or msg.sender_id
                    content = msg.message_str or "[非文本消息]"
                    platform_icon = get_platform_icon(msg.platform)

                    f.write(f"[{time_str}] {platform_icon} {group_info} {sender}: {content}\n")
        else:
            file_path = export_dir / f"{task_id}.{format_type}"

        task["status"] = "completed"
        task["file_path"] = str(file_path)
        task["completed_at"] = time.time()
        task["actual_count"] = len(messages)

        logger.info(f"[MessageRecorder Web] 导出任务 {task_id} 完成，共 {len(messages)} 条记录")

    except Exception as e:
        logger.error(f"[MessageRecorder Web] 导出任务 {task_id} 失败: {e}")
        task["status"] = "failed"
        task["error"] = str(e)
        task["completed_at"] = time.time()


async def _export_with_media(
    task_id: str,
    db: Database,
    messages: list,
    export_dir: Path,
    include_chain: bool,
    include_raw: bool,
    task: dict,
) -> Path:
    """导出为包含媒体文件的 .mrpkg (zip) 包"""
    media_base = Path(get_astrbot_plugin_data_path()) / PLUGIN_DIR_NAME / "media"

    export_data = {
        "export_info": {
            "plugin": "astrbot_plugin_message_recorder",
            "version": "1.0.0",
            "export_time": int(time.time() * 1000),
            "filters": task["filter"],
            "total_records": len(messages),
            "include_media": True,
        },
        "messages": [],
    }

    media_files_collected: List[str] = []

    for msg in messages:
        msg_dict = format_message_detail(msg) if include_chain or include_raw else format_message(msg)
        if not include_chain:
            msg_dict.pop("message_chain", None)
        if not include_raw:
            msg_dict.pop("raw_message", None)

        if include_chain and msg.message_chain:
            try:
                chain = json.loads(msg.message_chain)
                if isinstance(chain, list):
                    for comp in chain:
                        if isinstance(comp, dict) and "local_path" in comp:
                            lp = comp["local_path"]
                            if isinstance(lp, str) and lp:
                                media_files_collected.append(lp)
            except (json.JSONDecodeError, TypeError):
                pass

        export_data["messages"].append(msg_dict)

    pkg_path = export_dir / f"{task_id}.mrpkg"

    with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(export_data, ensure_ascii=False, indent=2))

        for rel_path in media_files_collected:
            abs_path = media_base / rel_path
            if abs_path.exists() and abs_path.is_file():
                try:
                    zf.write(abs_path, f"media/{rel_path}")
                except Exception as e:
                    logger.warning(
                        f"[MessageRecorder Web] 打包媒体文件失败 {rel_path}: {e}"
                    )

    task["media_count"] = len(media_files_collected)
    logger.info(
        f"[MessageRecorder Web] 导出含媒体包，共 {len(media_files_collected)} 个媒体文件"
    )

    return pkg_path


async def execute_import_task(task_id: str, db: Database, file_path: str, mode: str):
    """执行导入任务"""
    import json
    import csv

    MAX_FIELD_LENGTH = 65535
    VALID_MESSAGE_TYPES = {"group", "private"}

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

        return {
            "platform": platform,
            "message_id": str(record.get("message_id", ""))[:128],
            "session_id": str(record.get("session_id", ""))[:128],
            "group_id": str(record.get("group_id"))[:128] if record.get("group_id") else None,
            "sender_id": str(record.get("sender_id", ""))[:128],
            "sender_name": sender_name,
            "message_type": message_type,
            "message_str": message_str,
            "message_chain": message_chain,
            "raw_message": raw_message,
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

        for i, record in enumerate(records):
            task["processed"] = i + 1

            try:
                sanitized = sanitize_import_record(record)
                if sanitized is None:
                    errors += 1
                    continue

                normalized_timestamp = normalize_timestamp(sanitized["timestamp"])
                normalized_created_at = normalize_timestamp(sanitized["created_at"])

                msg_record = MessageRecord(
                    platform=sanitized["platform"],
                    message_id=sanitized["message_id"],
                    session_id=sanitized["session_id"],
                    group_id=sanitized["group_id"],
                    sender_id=sanitized["sender_id"],
                    sender_name=sanitized["sender_name"],
                    message_type=sanitized["message_type"],
                    message_str=sanitized["message_str"],
                    message_chain=json.dumps(sanitized["message_chain"]) if sanitized["message_chain"] else None,
                    raw_message=json.dumps(sanitized["raw_message"]) if sanitized["raw_message"] else None,
                    timestamp=normalized_timestamp,
                    created_at=normalized_created_at
                )

                if mode == "skip_duplicates" or mode == "merge":
                    await db.save_message(msg_record)
                    imported += 1

            except Exception as e:
                errors += 1
                logger.debug(f"[MessageRecorder Web] 导入记录失败: {e}")

        task["status"] = "completed"
        task["imported"] = imported
        task["skipped"] = skipped
        task["errors"] = errors
        task["media_restored"] = media_restored
        task["completed_at"] = time.time()

        _safe_remove_file(file_path)

        logger.info(
            f"[MessageRecorder Web] 导入任务 {task_id} 完成: "
            f"导入 {imported}, 跳过 {skipped}, 错误 {errors}, "
            f"媒体文件 {media_restored}"
        )

    except Exception as e:
        logger.error(f"[MessageRecorder Web] 导入任务 {task_id} 失败: {e}")
        task["status"] = "failed"
        task["error"] = str(e)
        task["completed_at"] = time.time()


async def _import_mrpkg(file_path: str) -> tuple:
    """从 .mrpkg 包导入数据和媒体文件，返回 (records, media_restored_count)"""
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
                logger.warning(
                    f"[MessageRecorder Web] 跳过可疑路径: {rel_path}"
                )
                continue

            target_path = media_base / rel_path

            try:
                target_path.resolve().relative_to(media_base.resolve())
            except ValueError:
                logger.warning(
                    f"[MessageRecorder Web] 路径遍历尝试被阻止: {rel_path}"
                )
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                with zf.open(name) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                media_restored += 1
            except Exception as e:
                logger.warning(
                    f"[MessageRecorder Web] 恢复媒体文件失败 {rel_path}: {e}"
                )

    logger.info(
        f"[MessageRecorder Web] 从 .mrpkg 恢复了 {media_restored} 个媒体文件"
    )

    return records, media_restored


def get_platform_icon(platform: str) -> str:
    """获取平台图标标识"""
    icons = {
        "telegram": "[TG]",
        "discord": "[DC]",
        "qq_official": "[QQ]",
        "qq_private": "[QQ]",
        "wechat": "[WX]",
    }
    return icons.get(platform, f"[{platform}]")


async def cleanup_expired_export_files():
    """定期清理过期的导出文件、导入任务和分片上传会话"""
    CHUNK_SESSION_MAX_AGE = 3600  # 分片上传会话最大有效期 1 小时

    while True:
        try:
            await asyncio.sleep(600)

            current_time = time.time()

            # 清理过期的导出任务
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

            # 清理过期的分片上传会话
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

            if expired_sessions:
                logger.info(f"[MessageRecorder Web] 已清理 {len(expired_sessions)} 个过期分片上传会话")

            # 清理过期的导入任务记录
            expired_imports = []
            for task_id, task in list(_import_tasks.items()):
                completed_at = task.get("completed_at", 0)
                if completed_at and current_time - completed_at > MAX_EXPORT_FILE_AGE:
                    expired_imports.append(task_id)

            for task_id in expired_imports:
                _import_tasks.pop(task_id, None)

            if expired_imports:
                logger.info(f"[MessageRecorder Web] 已清理 {len(expired_imports)} 个过期导入任务记录")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 清理过期文件任务出错: {e}")