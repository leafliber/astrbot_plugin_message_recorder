"""SQLite 数据库操作模块"""

import aiosqlite
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.api import logger

from .models import MessageRecord, QueryFilter, MessageStats
from .time_utils import parse_time_range


class Database:
    """SQLite 数据库管理类"""

    def __init__(self, plugin_name: str):
        self.plugin_name = plugin_name
        self.db_path: Optional[Path] = None
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        """初始化数据库"""
        # 设置数据库路径
        data_path = Path(get_astrbot_data_path())
        plugin_data_dir = data_path / "plugin_data" / self.plugin_name
        plugin_data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = plugin_data_dir / "messages.db"

        # 打开数据库连接
        self._db = await aiosqlite.connect(self.db_path)
        await self._create_tables()
        logger.info(f"[MessageRecorder] 数据库初始化完成: {self.db_path}")

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("[MessageRecorder] 数据库连接已关闭")

    async def _create_tables(self) -> None:
        """创建数据表和索引"""
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

        # 创建索引
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_platform ON messages(platform)",
            "CREATE INDEX IF NOT EXISTS idx_sender_id ON messages(sender_id)",
            "CREATE INDEX IF NOT EXISTS idx_group_id ON messages(group_id)",
            "CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_session_id ON messages(session_id)",
        ]
        for index_sql in indexes:
            await self._db.execute(index_sql)

        await self._db.commit()

    async def save_message(self, record: MessageRecord) -> int:
        """保存消息记录，返回记录 ID"""
        record.created_at = int(time.time() * 1000)

        logger.debug(
            f"[MessageRecorder] 正在保存消息: "
            f"platform={record.platform}, sender={record.sender_id}, "
            f"type={record.message_type}, group={record.group_id or '私聊'}"
        )

        cursor = await self._db.execute("""
            INSERT INTO messages (
                platform, message_id, session_id, group_id,
                sender_id, sender_name, message_type,
                message_str, message_chain, raw_message,
                timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
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

        logger.debug(
            f"[MessageRecorder] 消息已写入数据库, record_id={record_id}"
        )

        return record_id

    def _build_where_clause(self, query_filter: QueryFilter) -> tuple:
        """构建 WHERE 子句和参数"""
        conditions: List[str] = []
        params: List[Any] = []

        # 平台筛选
        platforms = query_filter.get_platforms()
        if platforms:
            if len(platforms) == 1:
                conditions.append("platform = ?")
                params.append(platforms[0])
            else:
                conditions.append(f"platform IN ({','.join(['?'] * len(platforms))})")
                params.extend(platforms)

        # 发送者筛选
        sender_ids = query_filter.get_sender_ids()
        if sender_ids:
            if len(sender_ids) == 1:
                conditions.append("sender_id = ?")
                params.append(sender_ids[0])
            else:
                conditions.append(f"sender_id IN ({','.join(['?'] * len(sender_ids))})")
                params.extend(sender_ids)

        # 群组筛选
        group_ids = query_filter.get_group_ids()
        if group_ids:
            if len(group_ids) == 1:
                conditions.append("group_id = ?")
                params.append(group_ids[0])
            else:
                conditions.append(f"group_id IN ({','.join(['?'] * len(group_ids))})")
                params.extend(group_ids)

        # 会话筛选
        session_ids = query_filter.get_session_ids()
        if session_ids:
            if len(session_ids) == 1:
                conditions.append("session_id = ?")
                params.append(session_ids[0])
            else:
                conditions.append(f"session_id IN ({','.join(['?'] * len(session_ids))})")
                params.extend(session_ids)

        # 消息类型
        if query_filter.message_type:
            conditions.append("message_type = ?")
            params.append(query_filter.message_type)

        # 时间筛选 - 支持 time 字段
        if query_filter.time:
            start_time, end_time = parse_time_range(query_filter.time)
            # 调试日志：显示实际的时间范围参数
            from datetime import datetime
            start_dt = datetime.fromtimestamp(start_time / 1000)
            end_dt = datetime.fromtimestamp(end_time / 1000)
            logger.debug(
                f"[MessageRecorder] 时间范围参数: start={start_time} ({start_dt}), "
                f"end={end_time} ({end_dt})"
            )
            conditions.append("timestamp >= ?")
            params.append(start_time)
            conditions.append("timestamp <= ?")
            params.append(end_time)
        else:
            if query_filter.start_time:
                conditions.append("timestamp >= ?")
                params.append(query_filter.start_time)
            if query_filter.end_time:
                conditions.append("timestamp <= ?")
                params.append(query_filter.end_time)

        # 关键词搜索
        if query_filter.keyword:
            conditions.append("message_str LIKE ?")
            params.append(f"%{query_filter.keyword}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        return where_clause, params

    async def query_messages(self, query_filter: QueryFilter) -> List[MessageRecord]:
        """根据过滤器查询消息"""
        where_clause, params = self._build_where_clause(query_filter)
        order_clause = "timestamp DESC" if query_filter.is_desc_order() else "timestamp ASC"

        logger.debug(
            f"[MessageRecorder] 执行查询: WHERE {where_clause}, "
            f"params={params}, limit={query_filter.limit}, offset={query_filter.offset}, order={order_clause}"
        )

        sql = f"""
            SELECT id, platform, message_id, session_id, group_id,
                   sender_id, sender_name, message_type,
                   message_str, message_chain, raw_message,
                   timestamp, created_at
            FROM messages
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
        """
        params.extend([query_filter.limit, query_filter.offset])

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

    async def get_message_by_id(self, message_id: int) -> Optional[MessageRecord]:
        """根据数据库 ID 获取单条消息"""
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

        # 获取之前的消息
        before_filter = QueryFilter(
            session_id=target.session_id,
            end_time=target.timestamp,
            limit=before,
            order="desc",
        )
        before_msgs = await self.query_messages(before_filter)
        # 排除目标消息本身，并按时间顺序排列
        before_msgs = [m for m in before_msgs if m.id != message_id]
        before_msgs.reverse()

        # 获取之后的消息
        after_filter = QueryFilter(
            session_id=target.session_id,
            start_time=target.timestamp,
            limit=after + 1,
            order="asc",
        )
        after_msgs = await self.query_messages(after_filter)
        after_msgs = [m for m in after_msgs if m.id != message_id]

        return {"before": before_msgs, "after": after_msgs}

    async def count_messages(self, query_filter: QueryFilter) -> int:
        """统计符合条件的消息数量"""
        where_clause, params = self._build_where_clause(query_filter)

        logger.debug(f"[MessageRecorder] 执行统计: WHERE {where_clause}")

        sql = f"SELECT COUNT(*) FROM messages WHERE {where_clause}"
        cursor = await self._db.execute(sql, params)
        result = await cursor.fetchone()
        count = result[0] if result else 0

        logger.debug(f"[MessageRecorder] 统计结果: {count} 条")

        return count

    async def get_stats(self) -> MessageStats:
        """获取消息统计信息"""
        stats = MessageStats()

        # 总消息数
        cursor = await self._db.execute("SELECT COUNT(*) FROM messages")
        result = await cursor.fetchone()
        stats.total_count = result[0] if result else 0

        # 群聊消息数
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM messages WHERE message_type = 'group'"
        )
        result = await cursor.fetchone()
        stats.group_message_count = result[0] if result else 0

        # 私聊消息数
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM messages WHERE message_type = 'private'"
        )
        result = await cursor.fetchone()
        stats.private_message_count = result[0] if result else 0

        # 各平台消息数
        cursor = await self._db.execute(
            "SELECT platform, COUNT(*) FROM messages GROUP BY platform"
        )
        rows = await cursor.fetchall()
        stats.platform_stats = {row[0]: row[1] for row in rows}

        # 时间范围
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

        cursor = await self._db.execute(
            "DELETE FROM messages WHERE timestamp < ?",
            (cutoff_time,)
        )
        await self._db.commit()
        deleted = cursor.rowcount

        if deleted > 0:
            logger.debug(f"[MessageRecorder] 按时间清理了 {deleted} 条记录")

        return deleted

    async def cleanup_by_limit(self, max_records: int) -> int:
        """清理超出数量限制的旧消息，返回清理数量"""
        if max_records <= 0:
            logger.debug("[MessageRecorder] 跳过按数量清理: max_records=0")
            return 0

        # 获取当前记录数
        cursor = await self._db.execute("SELECT COUNT(*) FROM messages")
        result = await cursor.fetchone()
        current_count = result[0] if result else 0

        logger.debug(
            f"[MessageRecorder] 按数量清理检查: current={current_count}, max={max_records}"
        )

        if current_count <= max_records:
            logger.debug("[MessageRecorder] 当前记录数未超限，无需清理")
            return 0

        # 删除最旧的记录
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
        """
        获取发送者排行榜

        Returns:
            发送者统计数据列表
        """
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
        """
        获取群组活跃度排行

        Returns:
            群组统计数据列表
        """
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

        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()

        return [
            {
                "id": row[0],
                "platform": row[1]
            }
            for row in rows
        ]