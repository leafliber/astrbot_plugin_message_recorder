"""导入任务执行模块"""

import asyncio
import json
import csv
import time
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from ..database import Database
from ..models import MessageRecord, PLUGIN_DIR_NAME
from ..time_utils import normalize_timestamp
from .constants import DB_OPERATION_TIMEOUT, IMPORT_RECORD_TIMEOUT
from .storage import get_import_tasks
from .utils import safe_remove_file


async def execute_import_task(task_id: str, db: Database, file_path: str, mode: str):
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

    task = get_import_tasks().get(task_id)
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
        error_details: list = []

        if mode == "skip_duplicates":
            platform_message_map: dict = {}
            invalid_records: list = []

            for i, record in enumerate(records):
                sanitized = sanitize_import_record(record)
                if sanitized is None:
                    errors += 1
                    invalid_records.append((i, record))
                    continue

                platform = sanitized["platform"]
                message_id = sanitized["message_id"]
                if message_id:
                    if platform not in platform_message_map:
                        platform_message_map[platform] = {}
                    platform_message_map[platform][message_id] = (i, sanitized)
                else:
                    invalid_records.append((i, record, sanitized))

            for i, record in invalid_records:
                if len(error_details) < 50:
                    error_details.append({
                        "index": i,
                        "error": "无效的记录格式",
                        "record_preview": str(record)[:200] if record else None
                    })

            existing_ids_by_platform: dict = {}
            for platform, msg_map in platform_message_map.items():
                try:
                    existing_ids = await asyncio.wait_for(
                        db.get_existing_message_ids(list(msg_map.keys()), platform),
                        timeout=DB_OPERATION_TIMEOUT
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
                        normalized_timestamp = normalize_timestamp(sanitized["timestamp"])
                        normalized_created_at = normalize_timestamp(sanitized["created_at"])

                        msg_record = MessageRecord(
                            platform=platform,
                            message_id=message_id,
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

                        await asyncio.wait_for(
                            db.save_message(msg_record),
                            timeout=IMPORT_RECORD_TIMEOUT
                        )
                        imported += 1
                    except asyncio.TimeoutError:
                        errors += 1
                        error_msg = f"操作超时 ({IMPORT_RECORD_TIMEOUT}s)"
                        logger.warning(f"[MessageRecorder Web] 导入记录 #{original_index} 超时")
                        if len(error_details) < 50:
                            error_details.append({
                                "index": original_index,
                                "error": error_msg,
                                "record_preview": str(records[original_index])[:200] if original_index < len(records) else None
                            })
                    except Exception as e:
                        errors += 1
                        error_msg = str(e)
                        logger.warning(f"[MessageRecorder Web] 导入记录 #{original_index} 失败: {error_msg}")
                        if len(error_details) < 50:
                            error_details.append({
                                "index": original_index,
                                "error": error_msg,
                                "record_preview": str(records[original_index])[:200] if original_index < len(records) else None
                            })

        else:
            for i, record in enumerate(records):
                task["processed"] = i + 1

                try:
                    sanitized = sanitize_import_record(record)
                    if sanitized is None:
                        errors += 1
                        error_details.append({
                            "index": i,
                            "error": "无效的记录格式",
                            "record_preview": str(record)[:200] if record else None
                        })
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

                    if mode == "merge":
                        record_id = await asyncio.wait_for(
                            db.save_message(msg_record),
                            timeout=IMPORT_RECORD_TIMEOUT
                        )
                        if record_id == 0 and msg_record.message_id:
                            skipped += 1
                        else:
                            imported += 1
                    else:
                        await asyncio.wait_for(
                            db.save_message(msg_record),
                            timeout=IMPORT_RECORD_TIMEOUT
                        )
                        imported += 1

                except asyncio.TimeoutError:
                    errors += 1
                    error_msg = f"操作超时 ({DB_OPERATION_TIMEOUT}s)"
                    logger.warning(f"[MessageRecorder Web] 导入记录 #{i} 超时")
                    if len(error_details) < 50:
                        error_details.append({
                            "index": i,
                            "error": error_msg,
                            "record_preview": str(record)[:200] if record else None
                        })

                except Exception as e:
                    errors += 1
                    error_msg = str(e)
                    logger.warning(f"[MessageRecorder Web] 导入记录 #{i} 失败: {error_msg}")
                    if len(error_details) < 50:
                        error_details.append({
                            "index": i,
                            "error": error_msg,
                            "record_preview": str(record)[:200] if record else None
                        })

        task["status"] = "completed"
        task["imported"] = imported
        task["skipped"] = skipped
        task["errors"] = errors
        task["error_details"] = error_details if error_details else None
        task["media_restored"] = media_restored
        task["completed_at"] = time.time()

        safe_remove_file(file_path)

        if errors > 0:
            logger.warning(
                f"[MessageRecorder Web] 导入任务 {task_id} 完成（有错误）: "
                f"导入 {imported}, 跳过 {skipped}, 错误 {errors}, "
                f"媒体文件 {media_restored}"
            )
        else:
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
