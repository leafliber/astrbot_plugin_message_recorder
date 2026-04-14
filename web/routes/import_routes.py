"""导入 API 路由"""

import os
import uuid
import time
import asyncio
import shutil
from pathlib import Path
from quart import Blueprint, jsonify, request

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from ...models import PLUGIN_DIR_NAME
from ..constants import MAX_IMPORT_FILE_SIZE, CHUNK_SIZE
from ..storage import get_chunk_sessions, get_import_tasks
from ..utils import get_plugin_data_dir
from ..import_task import execute_import_task


def register_import_routes(bp: Blueprint, get_db):
    @bp.route("/api/import/init", methods=["POST"])
    async def api_import_init():
        try:
            data = await request.get_json()
            filename = data.get("filename", "")
            file_size = data.get("file_size", 0)
            mode = data.get("mode", "skip_duplicates")

            if file_size > MAX_IMPORT_FILE_SIZE:
                max_gb = MAX_IMPORT_FILE_SIZE // (1024 * 1024 * 1024)
                return jsonify({
                    "success": False,
                    "error": f"文件大小超过限制（最大 {max_gb}GB）"
                }), 400

            file_ext = Path(filename).suffix.lower()
            if file_ext not in {".json", ".csv", ".mrpkg"}:
                return jsonify({
                    "success": False,
                    "error": "不支持的文件格式，仅支持 .json, .csv, .mrpkg"
                }), 400

            total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE if file_size > 0 else 1

            session_id = uuid.uuid4().hex
            temp_dir = get_plugin_data_dir() / "temp" / "chunks" / session_id
            temp_dir.mkdir(parents=True, exist_ok=True)

            get_chunk_sessions()[session_id] = {
                "filename": filename,
                "file_ext": file_ext,
                "file_size": file_size,
                "total_chunks": total_chunks,
                "uploaded_chunks": [],
                "mode": mode,
                "chunks_dir": str(temp_dir),
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
        try:
            files = await request.files
            if "chunk" not in files:
                return jsonify({"success": False, "error": "缺少分片数据"}), 400

            session_id = request.form.get("session_id", "")
            chunk_index = int(request.form.get("chunk_index", -1))

            session = get_chunk_sessions().get(session_id)
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
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            data = await request.get_json()
            session_id = data.get("session_id", "")

            session = get_chunk_sessions().get(session_id)
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
            get_chunk_sessions().pop(session_id, None)

            actual_size = assembled_file.stat().st_size
            if actual_size > MAX_IMPORT_FILE_SIZE:
                assembled_file.unlink()
                max_gb = MAX_IMPORT_FILE_SIZE // (1024 * 1024 * 1024)
                return jsonify({
                    "success": False,
                    "error": f"文件大小超过限制（最大 {max_gb}GB）"
                }), 400

            get_import_tasks()[task_id] = {
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

    @bp.route("/api/import/status/<task_id>")
    async def api_import_status(task_id: str):
        task = get_import_tasks().get(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        return jsonify({
            "success": True,
            "data": task
        })
