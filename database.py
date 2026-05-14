"""SQLite 数据库操作模块"""

import asyncio
import aiosqlite
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.api import logger

from .models import MessageRecord, QueryFilter, MessageStats
from .time_utils import parse_time_range
from .media_downloader import MediaDownloader


class Database:
    """SQLite 数据库管理类"""

    def __init__(self, plugin_name: str):
        self.plugin_name = plugin_name
        self.db_path: Optional[Path] = None
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        """初始化数据库"""
        data_path = Path(get_astrbot_data_path())
        plugin_data_dir = data_path / "plugin_data" / self.plugin_name
        plugin_data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = plugin_data_dir / "messages.db"

        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()
        logger.info(f"[MessageRecorder] 数据库初始化完成: {self.db_path}")

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db:
            async with self._lock:
                await self._db.close()
                self._db = None
            logger.info("[MessageRecorder] 数据库连接已关闭")

    async def _create_tables(self) -> None:
        """创建数据表和索引"""
        async with self._lock:
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    message_id TEXT,
                    session_id TEXT,
                    group_id TEXT,
                    sender_id TEXT NOT NULL,
                    sender_name TEXT,
                    message_type TEXT NOT NULL,
                    message_str TEXT,
                    message_chain TEXT,
                    raw_message TEXT,
                    timestamp INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)

            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_platform ON messages(platform)",
                "CREATE INDEX IF NOT EXISTS idx_sender_id ON messages(sender_id)",
                "CREATE INDEX IF NOT EXISTS idx_group_id ON messages(group_id)",
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_session_id ON messages(session_id)",
            ]
            for index_sql in indexes:
                await self._db.execute(index_sql)

            await self._migrate_schema()

            await self._db.commit()

    async def _migrate_schema(self) -> None:
        """数据库 schema 迁移：安全添加唯一约束和 FTS 索引"""
        cursor = await self._db.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_platform_message_id_unique'
        """)
        if not await cursor.fetchone():
            cursor = await self._db.execute("""
                SELECT platform, message_id, COUNT(*) as cnt
                FROM messages
                WHERE message_id IS NOT NULL AND message_id != ''
                GROUP BY platform, message_id
                HAVING cnt > 1
            """)
            duplicates = await cursor.fetchall()

            if duplicates:
                deduped = 0
                for platform, message_id, cnt in duplicates:
                    cursor = await self._db.execute("""
                        DELETE FROM messages
                        WHERE platform = ? AND message_id = ?
                        AND id NOT IN (
                            SELECT id FROM messages
                            WHERE platform = ? AND message_id = ?
                            ORDER BY timestamp DESC
                            LIMIT 1
                        )
                    """, (platform, message_id, platform, message_id))
                    deduped += cursor.rowcount
                if deduped > 0:
                    logger.info(f"[MessageRecorder] 去重清理了 {deduped} 条重复消息记录")

            try:
                await self._db.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_message_id_unique
                    ON messages(platform, message_id)
                    WHERE message_id IS NOT NULL AND message_id != ''
                """)
                logger.info("[MessageRecorder] 已添加 (platform, message_id) 唯一约束")
            except Exception as e:
                logger.warning(f"[MessageRecorder] 添加唯一约束失败（可能仍有重复数据）: {e}")

        cursor = await self._db.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='messages_fts'
        """)
        if not await cursor.fetchone():
            try:
                await self._db.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                    USING fts5(message_str, content='messages', content_rowid='id')
                """)

                await self._db.execute("""
                    INSERT INTO messages_fts(rowid, message_str)
                    SELECT id, message_str FROM messages
                    WHERE message_str IS NOT NULL
                """)

                await self._db.execute("""
                    CREATE TRIGGER IF NOT EXISTS messages_fts_insert
                    AFTER INSERT ON messages BEGIN
                        INSERT INTO messages_fts(rowid, message_str)
                        VALUES (new.id, new.message_str);
                    END
                """)

                await self._db.execute("""
                    CREATE TRIGGER IF NOT EXISTS messages_fts_delete
                    AFTER DELETE ON messages BEGIN
                        INSERT INTO messages_fts(messages_fts, rowid, message_str)
                        VALUES ('delete', old.id, old.message_str);
                    END
                """)

                await self._db.execute("""
                    CREATE TRIGGER IF NOT EXISTS messages_fts_update
                    AFTER UPDATE ON messages BEGIN
                        INSERT INTO messages_fts(messages_fts, rowid, message_str)
                        VALUES ('delete', old.id, old.message_str);
                        INSERT INTO messages_fts(rowid, message_str)
                        VALUES (new.id, new.message_str);
                    END
                """)

                logger.info("[MessageRecorder] 已创建 FTS5 全文搜索索引")
            except Exception as e:
                logger.warning(f"[MessageRecorder] 创建 FTS5 索引失败（SQLite 可能不支持 FTS5）: {e}")

    async def save_message(self, record: MessageRecord) -> int:
        """保存消息记录，返回记录 ID（重复消息返回 0）"""
        record.created_at = int(time.time() * 1000)

        logger.debug(
            f"[MessageRecorder] 正在保存消息: "
            f"platform={record.platform}, sender={record.sender_id}, "
            f"type={record.message_type}, group={record.group_id or '私聊'}"
        )

        has_message_id = record.message_id and record.message_id.strip()
        insert_sql = """
            INSERT OR IGNORE INTO messages (
                platform, message_id, session_id, group_id,
                sender_id, sender_name, message_type,
                message_str, message_chain, raw_message,
                timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """ if has_message_id else """
            INSERT INTO messages (
                platform, message_id, session_id, group_id,
                sender_id, sender_name, message_type,
                message_str, message_chain, raw_message,
                timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        async with self._lock:
            cursor = await self._db.execute(insert_sql, (
                record.platform,
                record.message_id,
                record.session_id,
                record.group_id,
                record.sender_id,
                record.sender_name,
                record.message_type,
                record.message_str,
                record.message_chain,
                record.raw_message,
                record.timestamp,
                record.created_at,
            ))
            await self._db.commit()
            record_id = cursor.lastrowid or 0

        if record_id == 0 and has_message_id:
            logger.debug(
                f"[MessageRecorder] 消息已存在，跳过: "
                f"platform={record.platform}, message_id={record.message_id}"
            )
        else:
            logger.debug(
                f"[MessageRecorder] 消息已写入数据库, record_id={record_id}"
            )

        return record_id

    def _build_where_clause(self, query_filter: QueryFilter) -> tuple:
        """构建 WHERE 子句和参数"""
        conditions: List[str] = []
        params: List[Any] = []

        def safe_str(val: Any) -> str:
            if val is None:
                return ""
            return str(val)

        def safe_int(val: Any) -> int:
            if val is None:
                return 0
            try:
                return int(val)
            except (TypeError, ValueError):
                return 0

        platforms = query_filter.get_platforms()
        if platforms:
            if len(platforms) == 1:
                conditions.append("platform = ?")
                params.append(safe_str(platforms[0]))
            else:
                conditions.append(f"platform IN ({','.join(['?'] * len(platforms))})")
                params.extend([safe_str(p) for p in platforms])

        sender_ids = query_filter.get_sender_ids()
        if sender_ids:
            if len(sender_ids) == 1:
                conditions.append("sender_id = ?")
                params.append(safe_str(sender_ids[0]))
            else:
                conditions.append(f"sender_id IN ({','.join(['?'] * len(sender_ids))})")
                params.extend([safe_str(s) for s in sender_ids])

        group_ids = query_filter.get_group_ids()
        if group_ids:
            if len(group_ids) == 1:
                conditions.append("group_id = ?")
                params.append(safe_str(group_ids[0]))
            else:
                conditions.append(f"group_id IN ({','.join(['?'] * len(group_ids))})")
                params.extend([safe_str(g) for g in group_ids])

        session_ids = query_filter.get_session_ids()
        if session_ids:
            if len(session_ids) == 1:
                conditions.append("session_id = ?")
                params.append(safe_str(session_ids[0]))
            else:
                conditions.append(f"session_id IN ({','.join(['?'] * len(session_ids))})")
                params.extend([safe_str(s) for s in session_ids])

        if query_filter.message_type:
            conditions.append("message_type = ?")
            params.append(safe_str(query_filter.message_type))

        if query_filter.time:
            start_time, end_time = parse_time_range(query_filter.time)
            from datetime import datetime
            start_dt = datetime.fromtimestamp(start_time / 1000)
            end_dt = datetime.fromtimestamp(end_time / 1000)
            logger.debug(
                f"[MessageRecorder] 时间范围参数: start={start_time} ({start_dt}), "
                f"end={end_time} ({end_dt})"
            )
            conditions.append("timestamp >= ?")
            params.append(safe_int(start_time))
            conditions.append("timestamp <= ?")
            params.append(safe_int(end_time))
        else:
            if query_filter.start_time is not None:
                conditions.append("timestamp >= ?")
                params.append(safe_int(query_filter.start_time))
            if query_filter.end_time is not None:
                conditions.append("timestamp <= ?")
                params.append(safe_int(query_filter.end_time))

        if query_filter.keyword:
            escaped_keyword = safe_str(query_filter.keyword).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("message_str LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped_keyword}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        return where_clause, params

    def _build_fts_keyword(self, keyword: str) -> str:
        """将关键词转换为 FTS5 查询语法"""
        cleaned = keyword.strip()
        if not cleaned:
            return ""
        tokens = cleaned.split()
        escaped = []
        for token in tokens:
            token = token.replace('"', '""')
            escaped.append(f'"{token}"')
        return " ".join(escaped)

    async def _fts_available(self) -> bool:
        """检查 FTS5 索引是否可用"""
        try:
            cursor = await self._db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='messages_fts'
            """)
            return await cursor.fetchone() is not None
        except Exception:
            return False

    async def query_messages(self, query_filter: QueryFilter) -> List[MessageRecord]:
        """根据过滤器查询消息"""
        where_clause, params = self._build_where_clause(query_filter)
        order_clause = "timestamp DESC" if query_filter.is_desc_order() else "timestamp ASC"

        limit_val = query_filter.limit
        offset_val = query_filter.offset

        no_limit = limit_val is None or limit_val == -1 or limit_val == 0
        effective_limit = None if no_limit else int(limit_val)
        effective_offset = max(0, int(offset_val) if offset_val is not None else 0)

        use_fts = False
        if query_filter.keyword and await self._fts_available():
            use_fts = True
            fts_keyword = self._build_fts_keyword(query_filter.keyword)
            like_clause = "message_str LIKE ? ESCAPE '\\'"
            fts_clause = "id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)"
            where_clause = where_clause.replace(like_clause, fts_clause)
            keyword_escaped = str(query_filter.keyword).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like_param = f"%{keyword_escaped}%"
            if like_param in params:
                params[params.index(like_param)] = fts_keyword

        logger.debug(
            f"[MessageRecorder] 执行查询: WHERE {where_clause}, "
            f"params={params}, limit={effective_limit}, offset={effective_offset}, order={order_clause}, fts={use_fts}"
        )

        select_columns = """
            id, platform, message_id, session_id, group_id,
            sender_id, sender_name, message_type,
            message_str, message_chain, raw_message,
            timestamp, created_at
        """

        if effective_limit is not None:
            sql = f"""
                SELECT {select_columns}
                FROM messages
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
            """
            params.extend([effective_limit, effective_offset])
        else:
            sql = f"""
                SELECT {select_columns}
                FROM messages
                WHERE {where_clause}
                ORDER BY {order_clause}
            """

        async with self._lock:
            cursor = await self._db.execute(sql, params)
            rows = await cursor.fetchall()

        records = []
        for row in rows:
            record = MessageRecord(
                id=row[0],
                platform=row[1],
                message_id=row[2],
                session_id=row[3],
                group_id=row[4],
                sender_id=row[5],
                sender_name=row[6],
                message_type=row[7],
                message_str=row[8],
                message_chain=row[9],
                raw_message=row[10],
                timestamp=row[11],
                created_at=row[12],
            )
            records.append(record)

        logger.debug(f"[MessageRecorder] 查询返回 {len(records)} 条记录")

        return records

    async def query_messages_batch(
        self,
        query_filter: QueryFilter,
        batch_size: int = 500
    ):
        """分批查询消息，返回异步生成器，避免内存溢出"""
        from typing import AsyncGenerator

        where_clause, params = self._build_where_clause(query_filter)
        order_clause = "timestamp DESC" if query_filter.is_desc_order() else "timestamp ASC"

        total_limit = query_filter.limit if query_filter.limit and query_filter.limit > 0 else None
        offset_val = max(0, int(query_filter.offset) if query_filter.offset else 0)

        use_fts = False
        if query_filter.keyword and await self._fts_available():
            use_fts = True
            fts_keyword = self._build_fts_keyword(query_filter.keyword)
            like_clause = "message_str LIKE ? ESCAPE '\\'"
            fts_clause = "id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)"
            where_clause = where_clause.replace(like_clause, fts_clause)
            keyword_escaped = str(query_filter.keyword).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like_param = f"%{keyword_escaped}%"
            if like_param in params:
                params[params.index(like_param)] = fts_keyword

        select_columns = """
            id, platform, message_id, session_id, group_id,
            sender_id, sender_name, message_type,
            message_str, message_chain, raw_message,
            timestamp, created_at
        """

        current_offset = offset_val
        total_fetched = 0

        while True:
            if total_limit is not None and total_fetched >= total_limit:
                break

            current_batch_size = batch_size
            if total_limit is not None:
                remaining = total_limit - total_fetched
                current_batch_size = min(batch_size, remaining)

            sql = f"""
                SELECT {select_columns}
                FROM messages
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
            """
            batch_params = params + [current_batch_size, current_offset]

            async with self._lock:
                cursor = await self._db.execute(sql, batch_params)
                rows = await cursor.fetchall()

            if not rows:
                break

            for row in rows:
                record = MessageRecord(
                    id=row[0],
                    platform=row[1],
                    message_id=row[2],
                    session_id=row[3],
                    group_id=row[4],
                    sender_id=row[5],
                    sender_name=row[6],
                    message_type=row[7],
                    message_str=row[8],
                    message_chain=row[9],
                    raw_message=row[10],
                    timestamp=row[11],
                    created_at=row[12],
                )
                yield record
                total_fetched += 1

            if len(rows) < current_batch_size:
                break

            current_offset += batch_size

    async def get_message_by_id(self, message_id: int) -> Optional[MessageRecord]:
        """根据数据库 ID 获取单条消息"""
        async with self._lock:
            cursor = await self._db.execute("""
                SELECT id, platform, message_id, session_id, group_id,
                       sender_id, sender_name, message_type,
                       message_str, message_chain, raw_message,
                       timestamp, created_at
                FROM messages
                WHERE id = ?
            """, (message_id,))
            row = await cursor.fetchone()

        if row:
            return MessageRecord(
                id=row[0],
                platform=row[1],
                message_id=row[2],
                session_id=row[3],
                group_id=row[4],
                sender_id=row[5],
                sender_name=row[6],
                message_type=row[7],
                message_str=row[8],
                message_chain=row[9],
                raw_message=row[10],
                timestamp=row[11],
                created_at=row[12],
            )
        return None

    async def get_message_by_platform_id(
        self,
        platform_message_id: str,
        platform: Optional[str] = None
    ) -> Optional[MessageRecord]:
        """根据平台原始消息 ID 获取消息"""
        if platform:
            sql = """
                SELECT id, platform, message_id, session_id, group_id,
                       sender_id, sender_name, message_type,
                       message_str, message_chain, raw_message,
                       timestamp, created_at
                FROM messages
                WHERE message_id = ? AND platform = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """
            params = (platform_message_id, platform)
        else:
            sql = """
                SELECT id, platform, message_id, session_id, group_id,
                       sender_id, sender_name, message_type,
                       message_str, message_chain, raw_message,
                       timestamp, created_at
                FROM messages
                WHERE message_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """
            params = (platform_message_id,)

        async with self._lock:
            cursor = await self._db.execute(sql, params)
            row = await cursor.fetchone()

        if row:
            return MessageRecord(
                id=row[0],
                platform=row[1],
                message_id=row[2],
                session_id=row[3],
                group_id=row[4],
                sender_id=row[5],
                sender_name=row[6],
                message_type=row[7],
                message_str=row[8],
                message_chain=row[9],
                raw_message=row[10],
                timestamp=row[11],
                created_at=row[12],
            )
        return None

    async def get_existing_message_ids(
        self,
        message_ids: List[str],
        platform: str
    ) -> set:
        """批量查询已存在的消息ID，返回已存在的ID集合"""
        if not message_ids:
            return set()

        placeholders = ",".join("?" * len(message_ids))
        sql = f"""
            SELECT message_id FROM messages
            WHERE message_id IN ({placeholders}) AND platform = ?
        """
        params = list(message_ids) + [platform]

        async with self._lock:
            cursor = await self._db.execute(sql, params)
            rows = await cursor.fetchall()

        return {row[0] for row in rows}

    async def get_context_messages(
        self,
        message_id: int,
        before: int = 5,
        after: int = 5
    ) -> Dict[str, List[MessageRecord]]:
        """获取某条消息的上下文消息"""
        target = await self.get_message_by_id(message_id)
        if not target:
            return {"before": [], "after": []}

        if target.message_type == "group" and target.group_id:
            scope_conditions = "platform = ? AND group_id = ? AND message_type = 'group'"
            scope_params = [target.platform, target.group_id]
        elif target.session_id and target.session_id.strip():
            scope_conditions = "session_id = ?"
            scope_params = [target.session_id]
        else:
            scope_conditions = "platform = ? AND sender_id = ? AND message_type = 'private'"
            scope_params = [target.platform, target.sender_id]

        select_columns = """
            id, platform, message_id, session_id, group_id,
            sender_id, sender_name, message_type,
            message_str, message_chain, raw_message,
            timestamp, created_at
        """

        before_sql = f"""
            SELECT {select_columns}
            FROM messages
            WHERE {scope_conditions} AND timestamp < ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        before_params = scope_params + [target.timestamp, before]

        after_sql = f"""
            SELECT {select_columns}
            FROM messages
            WHERE {scope_conditions} AND timestamp > ?
            ORDER BY timestamp ASC
            LIMIT ?
        """
        after_params = scope_params + [target.timestamp, after]

        async with self._lock:
            cursor = await self._db.execute(before_sql, before_params)
            before_rows = await cursor.fetchall()

            cursor = await self._db.execute(after_sql, after_params)
            after_rows = await cursor.fetchall()

        def _row_to_record(row) -> MessageRecord:
            return MessageRecord(
                id=row[0],
                platform=row[1],
                message_id=row[2],
                session_id=row[3],
                group_id=row[4],
                sender_id=row[5],
                sender_name=row[6],
                message_type=row[7],
                message_str=row[8],
                message_chain=row[9],
                raw_message=row[10],
                timestamp=row[11],
                created_at=row[12],
            )

        before_msgs = [_row_to_record(row) for row in reversed(before_rows)]
        after_msgs = [_row_to_record(row) for row in after_rows]

        return {"before": before_msgs, "after": after_msgs}

    async def count_messages(self, query_filter: QueryFilter) -> int:
        """统计符合条件的消息数量"""
        where_clause, params = self._build_where_clause(query_filter)

        logger.debug(f"[MessageRecorder] 执行统计: WHERE {where_clause}")

        sql = f"SELECT COUNT(*) FROM messages WHERE {where_clause}"
        async with self._lock:
            cursor = await self._db.execute(sql, params)
            result = await cursor.fetchone()
        count = result[0] if result else 0

        logger.debug(f"[MessageRecorder] 统计结果: {count} 条")

        return count

    async def get_stats(self) -> MessageStats:
        """获取消息统计信息"""
        stats = MessageStats()

        async with self._lock:
            cursor = await self._db.execute("SELECT COUNT(*) FROM messages")
            result = await cursor.fetchone()
            stats.total_count = result[0] if result else 0

            cursor = await self._db.execute(
                "SELECT COUNT(*) FROM messages WHERE message_type = 'group'"
            )
            result = await cursor.fetchone()
            stats.group_message_count = result[0] if result else 0

            cursor = await self._db.execute(
                "SELECT COUNT(*) FROM messages WHERE message_type = 'private'"
            )
            result = await cursor.fetchone()
            stats.private_message_count = result[0] if result else 0

            cursor = await self._db.execute(
                "SELECT platform, COUNT(*) FROM messages GROUP BY platform"
            )
            rows = await cursor.fetchall()
            stats.platform_stats = {row[0]: row[1] for row in rows}

            cursor = await self._db.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM messages"
            )
            result = await cursor.fetchone()
            if result and result[0]:
                stats.oldest_timestamp = result[0]
                stats.newest_timestamp = result[1]

            cursor = await self._db.execute(
                "SELECT MIN(created_at), MAX(created_at) FROM messages"
            )
            result = await cursor.fetchone()
            if result and result[0]:
                stats.first_record_time = result[0]
                stats.last_record_time = result[1]

        return stats

    async def cleanup_by_age(self, retention_days: int) -> int:
        """清理超过保留天数的消息，返回清理数量"""
        if retention_days <= 0:
            logger.debug("[MessageRecorder] 跳过按时间清理: retention_days=0")
            return 0

        cutoff_time = int((time.time() - retention_days * 86400) * 1000)
        logger.debug(
            f"[MessageRecorder] 按时间清理: retention_days={retention_days}, "
            f"cutoff_timestamp={cutoff_time}"
        )

        try:
            async with self._lock:
                cursor = await self._db.execute(
                    "DELETE FROM messages WHERE timestamp < ?",
                    (cutoff_time,)
                )
                await self._db.commit()
                deleted = cursor.rowcount

            if deleted > 0:
                logger.debug(f"[MessageRecorder] 按时间清理了 {deleted} 条记录")

            return deleted
        except aiosqlite.Error as e:
            logger.error(f"[MessageRecorder] 按时间清理失败: {e}")
            return 0

    async def cleanup_by_limit(self, max_records: int) -> int:
        """清理超出数量限制的旧消息，返回清理数量"""
        if max_records <= 0:
            logger.debug("[MessageRecorder] 跳过按数量清理: max_records=0")
            return 0

        async with self._lock:
            cursor = await self._db.execute("SELECT COUNT(*) FROM messages")
            result = await cursor.fetchone()
            current_count = result[0] if result else 0

            logger.debug(
                f"[MessageRecorder] 按数量清理检查: current={current_count}, max={max_records}"
            )

            if current_count <= max_records:
                logger.debug("[MessageRecorder] 当前记录数未超限，无需清理")
                return 0

            delete_count = current_count - max_records
            cursor = await self._db.execute("""
                DELETE FROM messages
                WHERE id IN (
                    SELECT id FROM messages
                    ORDER BY timestamp ASC
                    LIMIT ?
                )
            """, (delete_count,))
            await self._db.commit()
            deleted = cursor.rowcount

        logger.debug(f"[MessageRecorder] 按数量清理了 {deleted} 条记录")

        return deleted

    # ========== Web 扩展查询方法 ==========

    async def get_timeline_stats(
        self,
        interval: str = "day",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        platform: Optional[str] = None,
        group_id: Optional[str] = None
    ) -> List[Dict]:
        """
        按时间间隔统计消息数量

        Args:
            interval: 时间间隔 (day, week, month)
            start_time: 开始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）
            platform: 平台筛选
            group_id: 群组筛选

        Returns:
            时间点统计数据列表
        """
        # SQLite 时间格式化
        # day: strftime('%Y-%m-%d', timestamp/1000, 'unixepoch')
        # week: strftime('%Y-W%W', timestamp/1000, 'unixepoch')
        # month: strftime('%Y-%m', timestamp/1000, 'unixepoch')

        if interval == "day":
            time_format = "strftime('%Y-%m-%d', timestamp/1000, 'unixepoch')"
        elif interval == "week":
            time_format = "strftime('%Y-W%W', timestamp/1000, 'unixepoch')"
        elif interval == "month":
            time_format = "strftime('%Y-%m', timestamp/1000, 'unixepoch')"
        else:
            time_format = "strftime('%Y-%m-%d', timestamp/1000, 'unixepoch')"

        conditions = []
        params: List[Any] = []

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        if group_id:
            conditions.append("group_id = ?")
            params.append(group_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"""
            SELECT
                {time_format} as date,
                COUNT(*) as count,
                SUM(CASE WHEN message_type = 'group' THEN 1 ELSE 0 END) as group_count,
                SUM(CASE WHEN message_type = 'private' THEN 1 ELSE 0 END) as private_count
            FROM messages
            WHERE {where_clause}
            GROUP BY date
            ORDER BY date ASC
        """

        async with self._lock:
            cursor = await self._db.execute(sql, params)
            rows = await cursor.fetchall()

        return [
            {
                "date": row[0],
                "count": row[1],
                "group_count": row[2],
                "private_count": row[3]
            }
            for row in rows
        ]

    async def get_sender_ranking(
        self,
        limit: int = 20,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        platform: Optional[str] = None,
        group_id: Optional[str] = None
    ) -> List[Dict]:
        """获取发送者排行榜"""
        conditions = []
        params: List[Any] = []

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        if group_id:
            conditions.append("group_id = ?")
            params.append(group_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"""
            SELECT
                sender_id,
                sender_name,
                platform,
                COUNT(*) as count
            FROM messages
            WHERE {where_clause}
            GROUP BY sender_id, platform
            ORDER BY count DESC
            LIMIT ?
        """
        params.append(limit)

        async with self._lock:
            cursor = await self._db.execute(sql, params)
            rows = await cursor.fetchall()

        return [
            {
                "sender_id": row[0],
                "sender_name": row[1],
                "platform": row[2],
                "count": row[3]
            }
            for row in rows
        ]

    async def get_group_ranking(
        self,
        limit: int = 20,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        platform: Optional[str] = None
    ) -> List[Dict]:
        """获取群组活跃度排行"""
        conditions = ["message_type = 'group'"]
        params: List[Any] = []

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if platform:
            conditions.append("platform = ?")
            params.append(platform)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT
                group_id,
                platform,
                COUNT(*) as count,
                COUNT(DISTINCT sender_id) as sender_count
            FROM messages
            WHERE {where_clause}
            GROUP BY group_id, platform
            ORDER BY count DESC
            LIMIT ?
        """
        params.append(limit)

        async with self._lock:
            cursor = await self._db.execute(sql, params)
            rows = await cursor.fetchall()

        return [
            {
                "group_id": row[0],
                "platform": row[1],
                "count": row[2],
                "sender_count": row[3]
            }
            for row in rows
        ]

    async def get_distinct_platforms(self) -> List[str]:
        """获取所有平台列表"""
        sql = "SELECT DISTINCT platform FROM messages ORDER BY platform"
        async with self._lock:
            cursor = await self._db.execute(sql)
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_distinct_senders(
        self,
        platform: Optional[str] = None,
        group_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """获取发送者列表"""
        conditions = []
        params: List[Any] = []

        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        if group_id:
            conditions.append("group_id = ?")
            params.append(group_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"""
            SELECT DISTINCT sender_id, sender_name, platform
            FROM messages
            WHERE {where_clause}
            ORDER BY sender_name, sender_id
            LIMIT ?
        """
        params.append(limit)

        async with self._lock:
            cursor = await self._db.execute(sql, params)
            rows = await cursor.fetchall()

        return [
            {
                "id": row[0],
                "name": row[1] or row[0],
                "platform": row[2]
            }
            for row in rows
        ]

    async def get_distinct_groups(
        self,
        platform: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """获取群组列表"""
        conditions = ["message_type = 'group'", "group_id IS NOT NULL"]
        params: List[Any] = []

        if platform:
            conditions.append("platform = ?")
            params.append(platform)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT DISTINCT group_id, platform
            FROM messages
            WHERE {where_clause}
            ORDER BY group_id
            LIMIT ?
        """
        params.append(limit)

        async with self._lock:
            cursor = await self._db.execute(sql, params)
            rows = await cursor.fetchall()

        return [
            {
                "id": row[0],
                "platform": row[1]
            }
            for row in rows
        ]

    async def get_media_paths_before(self, cutoff_timestamp: int) -> List[str]:
        """获取指定时间戳之前的消息中包含的媒体文件路径"""
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT message_chain FROM messages WHERE timestamp < ? AND message_chain IS NOT NULL",
                (cutoff_timestamp,),
            )
            rows = await cursor.fetchall()
        paths = []
        for row in rows:
            paths.extend(MediaDownloader.extract_media_paths(row[0]))
        return paths

    async def get_media_paths_over_limit(self, max_records: int) -> List[str]:
        """获取超出数量限制的旧消息中包含的媒体文件路径"""
        async with self._lock:
            cursor = await self._db.execute("SELECT COUNT(*) FROM messages")
            result = await cursor.fetchone()
            current_count = result[0] if result else 0

            if current_count <= max_records:
                return []

            delete_count = current_count - max_records
            cursor = await self._db.execute(
                """
                SELECT message_chain FROM messages
                WHERE id IN (
                    SELECT id FROM messages ORDER BY timestamp ASC LIMIT ?
                )
                AND message_chain IS NOT NULL
                """,
                (delete_count,),
            )
            rows = await cursor.fetchall()

        paths = []
        for row in rows:
            paths.extend(MediaDownloader.extract_media_paths(row[0]))
        return paths