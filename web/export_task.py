"""导出任务执行模块"""

import json
import csv
import time
import asyncio
import shutil
import zipfile
from pathlib import Path
from typing import List, AsyncGenerator

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from ..database import Database
from ..models import QueryFilter, PLUGIN_DIR_NAME, MessageRecord
from .constants import MAX_EXPORT_FILE_AGE, CHUNK_SESSION_MAX_AGE, DB_OPERATION_TIMEOUT
from .storage import get_export_tasks, get_chunk_sessions, get_import_tasks
from .utils import (
    get_plugin_data_dir,
    format_timestamp,
    format_message,
    format_message_detail,
    format_message_for_export,
    safe_remove_file,
    get_platform_icon,
)


async def execute_export_task(
    task_id: str,
    db: Database,
    query_filter: QueryFilter,
    format_type: str,
    options: dict
):
    task = get_export_tasks().get(task_id)
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

        export_dir = get_plugin_data_dir() / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        include_chain = options.get("include_chain", True)
        include_raw = options.get("include_raw", False)
        include_media = options.get("include_media", False)

        if include_media and format_type == "json":
            file_path = await _export_with_media_streaming(
                task_id, db, query_filter, export_dir,
                include_chain, include_raw, task,
            )
        elif format_type == "json":
            file_path = await _export_json_streaming(
                task_id, db, query_filter, export_dir,
                include_chain, include_raw, task,
            )
        elif format_type == "csv":
            file_path = await _export_csv_streaming(
                task_id, db, query_filter, export_dir, task,
            )
        elif format_type == "txt":
            file_path = await _export_txt_streaming(
                task_id, db, query_filter, export_dir, task,
            )

        task["status"] = "completed"
        task["file_path"] = str(file_path)
        task["completed_at"] = time.time()

        logger.info(f"[MessageRecorder Web] 导出任务 {task_id} 完成，共 {task.get('actual_count', 0)} 条记录")

    except asyncio.TimeoutError:
        logger.error(f"[MessageRecorder Web] 导出任务 {task_id} 超时")
        task["status"] = "failed"
        task["error"] = f"操作超时 ({DB_OPERATION_TIMEOUT}s)"
        task["completed_at"] = time.time()
    except Exception as e:
        logger.error(f"[MessageRecorder Web] 导出任务 {task_id} 失败: {e}")
        task["status"] = "failed"
        task["error"] = str(e)
        task["completed_at"] = time.time()


async def _export_json_streaming(
    task_id: str,
    db: Database,
    query_filter: QueryFilter,
    export_dir: Path,
    include_chain: bool,
    include_raw: bool,
    task: dict,
) -> Path:
    file_path = export_dir / f"{task_id}.json"
    count = 0

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("{\n")
        f.write('  "export_info": {\n')
        f.write('    "plugin": "astrbot_plugin_message_recorder",\n')
        f.write('    "version": "1.0.0",\n')
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

            msg_dict = format_message_for_export(msg, include_chain, include_raw)
            f.write("    ")
            f.write(json.dumps(msg_dict, ensure_ascii=False))
            count += 1

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


async def _export_csv_streaming(
    task_id: str,
    db: Database,
    query_filter: QueryFilter,
    export_dir: Path,
    task: dict,
) -> Path:
    file_path = export_dir / f"{task_id}.csv"
    count = 0

    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "platform", "sender_id", "sender_name", "group_id",
            "message_type", "message_str", "timestamp", "created_at"
        ])

        async for msg in db.query_messages_batch(query_filter):
            writer.writerow([
                msg.id, msg.platform, msg.sender_id, msg.sender_name or "",
                msg.group_id or "", msg.message_type, msg.message_str or "",
                msg.timestamp, msg.created_at
            ])
            count += 1

    task["actual_count"] = count
    return file_path


async def _export_txt_streaming(
    task_id: str,
    db: Database,
    query_filter: QueryFilter,
    export_dir: Path,
    task: dict,
) -> Path:
    file_path = export_dir / f"{task_id}.txt"
    count = 0

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("=== 导出信息 ===\n")
        f.write("插件: astrbot_plugin_message_recorder\n")
        f.write(f"导出时间: {format_timestamp(int(time.time() * 1000))}\n")
        f.write("总记录数: PENDING\n\n")
        f.write("=== 消息记录 ===\n\n")

        async for msg in db.query_messages_batch(query_filter):
            time_str = format_timestamp(msg.timestamp)
            group_info = f"[群聊:{msg.group_id}]" if msg.group_id else "[私聊]"
            sender = msg.sender_name or msg.sender_id
            content = msg.message_str or "[非文本消息]"
            platform_icon = get_platform_icon(msg.platform)

            f.write(f"[{time_str}] {platform_icon} {group_info} {sender}: {content}\n")
            count += 1

    with open(file_path, "r+", encoding="utf-8") as f:
        content = f.read()
        content = content.replace("总记录数: PENDING", f"总记录数: {count}")
        f.seek(0)
        f.write(content)
        f.truncate()

    task["actual_count"] = count
    return file_path


async def _export_with_media_streaming(
    task_id: str,
    db: Database,
    query_filter: QueryFilter,
    export_dir: Path,
    include_chain: bool,
    include_raw: bool,
    task: dict,
) -> Path:
    media_base = Path(get_astrbot_plugin_data_path()) / PLUGIN_DIR_NAME / "media"

    messages_data: List[dict] = []
    media_files_collected: List[str] = []
    count = 0

    async for msg in db.query_messages_batch(query_filter):
        msg_dict = format_message_for_export(msg, include_chain, include_raw)

        if include_chain:
            chain = msg_dict.get("message_chain")
            if isinstance(chain, list):
                for comp in chain:
                    if isinstance(comp, dict) and "local_path" in comp:
                        lp = comp["local_path"]
                        if isinstance(lp, str) and lp:
                            media_files_collected.append(lp)

        messages_data.append(msg_dict)
        count += 1

    export_data = {
        "export_info": {
            "plugin": "astrbot_plugin_message_recorder",
            "version": "1.0.0",
            "export_time": int(time.time() * 1000),
            "filters": task["filter"],
            "total_records": count,
            "include_media": True,
        },
        "messages": messages_data,
    }

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

    task["actual_count"] = count
    task["media_count"] = len(media_files_collected)
    logger.info(
        f"[MessageRecorder Web] 导出含媒体包，共 {len(media_files_collected)} 个媒体文件"
    )

    return pkg_path


async def cleanup_expired_export_files():
    while True:
        try:
            await asyncio.sleep(600)

            current_time = time.time()

            expired_tasks = []

            for task_id, task in list(get_export_tasks().items()):
                completed_at = task.get("completed_at", 0)
                if completed_at and current_time - completed_at > MAX_EXPORT_FILE_AGE:
                    expired_tasks.append(task_id)

                    file_path = task.get("file_path")
                    if file_path and os.path.exists(file_path):
                        safe_remove_file(file_path)

            for task_id in expired_tasks:
                get_export_tasks().pop(task_id, None)

            if expired_tasks:
                logger.info(f"[MessageRecorder Web] 已清理 {len(expired_tasks)} 个过期导出任务")

            expired_sessions = []
            for session_id, session in list(get_chunk_sessions().items()):
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
                get_chunk_sessions().pop(session_id, None)

            if expired_sessions:
                logger.info(f"[MessageRecorder Web] 已清理 {len(expired_sessions)} 个过期分片上传会话")

            expired_imports = []
            for task_id, task in list(get_import_tasks().items()):
                completed_at = task.get("completed_at", 0)
                if completed_at and current_time - completed_at > MAX_EXPORT_FILE_AGE:
                    expired_imports.append(task_id)

            for task_id in expired_imports:
                get_import_tasks().pop(task_id, None)

            if expired_imports:
                logger.info(f"[MessageRecorder Web] 已清理 {len(expired_imports)} 个过期导入任务记录")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 清理过期文件任务出错: {e}")
