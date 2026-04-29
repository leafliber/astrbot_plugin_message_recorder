"""导出 API 路由"""

import os
import uuid
import time
import asyncio
from quart import Blueprint, jsonify, request, send_file

from astrbot.api import logger

from ..constants import MAX_EXPORT_FILE_AGE
from ..storage import get_export_tasks
from ..utils import build_query_filter_from_dict, estimate_size, safe_remove_file
from ..export_task import execute_export_task


def register_export_routes(bp: Blueprint, get_db):
    @bp.route("/api/export", methods=["POST"])
    async def api_export():
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            data = await request.get_json()
            format_type = data.get("format", "json")
            filters = data.get("filters", {})
            options = data.get("options", {})

            query_filter = build_query_filter_from_dict(filters)

            estimated_count = await get_db().count_messages(query_filter)

            task_id = f"export_{uuid.uuid4().hex[:12]}"

            get_export_tasks()[task_id] = {
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
        task = get_export_tasks().get(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        return jsonify({
            "success": True,
            "data": task
        })

    @bp.route("/api/export/download/<task_id>")
    async def api_export_download(task_id: str):
        task = get_export_tasks().get(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        if task["status"] != "completed":
            return jsonify({"success": False, "error": "导出未完成"}), 400

        completed_at = task.get("completed_at", 0)
        file_age = time.time() - completed_at
        if file_age > MAX_EXPORT_FILE_AGE:
            file_path = task.get("file_path")
            if file_path and os.path.exists(file_path):
                safe_remove_file(file_path)
            get_export_tasks().pop(task_id, None)
            return jsonify({
                "success": False,
                "error": "导出文件已过期，请重新导出"
            }), 410

        file_path = task.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return jsonify({"success": False, "error": "文件不存在"}), 404

        format_type = task.get("format", "json")
        ext = "zip" if format_type == "json" and task.get("options", {}).get("include_media") else format_type
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(completed_at))
        filename = f"messages_export_{timestamp}.{ext}"

        mime_types = {
            "json": "application/json",
            "csv": "text/csv",
            "txt": "text/plain",
            "zip": "application/zip"
        }
        mimetype = mime_types.get(ext, "application/octet-stream")

        return await send_file(
            file_path,
            mimetype=mimetype,
            as_attachment=True,
            attachment_filename=filename
        )
