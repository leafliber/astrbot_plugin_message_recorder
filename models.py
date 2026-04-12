"""数据模型定义"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List
import json

PLUGIN_DIR_NAME = "astrbot_plugin_message_recorder"


@dataclass
class MessageRecord:
    """消息记录数据模型"""

    id: Optional[int] = None
    platform: str = ""
    message_id: str = ""
    session_id: str = ""
    group_id: Optional[str] = None
    sender_id: str = ""
    sender_name: Optional[str] = None
    message_type: str = ""  # "group" 或 "private"
    message_str: Optional[str] = None
    message_chain: Optional[str] = None  # JSON 字符串
    raw_message: Optional[str] = None  # JSON 字符串
    timestamp: int = 0  # 消息时间戳（毫秒）
    created_at: int = 0  # 记录创建时间（毫秒）

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)

    def get_message_chain_list(self) -> List[dict]:
        """解析消息链 JSON 为列表"""
        if self.message_chain:
            try:
                return json.loads(self.message_chain)
            except json.JSONDecodeError:
                return []
        return []

    def get_raw_message_dict(self) -> Optional[dict]:
        """解析原始消息 JSON 为字典"""
        if self.raw_message:
            try:
                return json.loads(self.raw_message)
            except json.JSONDecodeError:
                return None
        return None


@dataclass
class QueryFilter:
    """消息查询过滤器 - 支持任意条件组合"""

    # 平台筛选
    platform: Optional[str] = None
    platforms: Optional[List[str]] = None  # 支持多个平台

    # 发送者筛选（单个或多个）
    sender_id: Optional[str] = None
    sender_ids: Optional[List[str]] = None

    # 群组筛选（单个或多个）
    group_id: Optional[str] = None
    group_ids: Optional[List[str]] = None

    # 会话筛选（单个或多个）
    session_id: Optional[str] = None
    session_ids: Optional[List[str]] = None

    # 消息类型
    message_type: Optional[str] = None  # "group" 或 "private"

    # 时间筛选
    time: Optional[str] = None  # 时间字符串: today, yesterday, last7d, 2024-01-01~2024-01-15 等
    start_time: Optional[int] = None  # 开始时间戳（毫秒）
    end_time: Optional[int] = None  # 结束时间戳（毫秒）

    # 内容搜索
    keyword: Optional[str] = None  # 消息内容关键词搜索

    # 分页和排序
    limit: int = 100
    offset: int = 0
    order: str = "desc"  # "desc" 按时间倒序, "asc" 按时间正序

    def get_sender_ids(self) -> List[str]:
        """获取所有发送者 ID"""
        ids = []
        if self.sender_id:
            ids.append(self.sender_id)
        if self.sender_ids:
            ids.extend(self.sender_ids)
        return ids

    def get_group_ids(self) -> List[str]:
        """获取所有群组 ID"""
        ids = []
        if self.group_id:
            ids.append(self.group_id)
        if self.group_ids:
            ids.extend(self.group_ids)
        return ids

    def get_session_ids(self) -> List[str]:
        """获取所有会话 ID"""
        ids = []
        if self.session_id:
            ids.append(self.session_id)
        if self.session_ids:
            ids.extend(self.session_ids)
        return ids

    def get_platforms(self) -> List[str]:
        """获取所有平台"""
        platforms = []
        if self.platform:
            platforms.append(self.platform)
        if self.platforms:
            platforms.extend(self.platforms)
        return platforms

    def is_desc_order(self) -> bool:
        """是否按时间倒序排列"""
        return self.order.lower() != "asc"


@dataclass
class MessageStats:
    """消息统计信息"""

    total_count: int = 0
    group_message_count: int = 0
    private_message_count: int = 0
    platform_stats: dict = field(default_factory=dict)  # 各平台消息数量
    oldest_timestamp: Optional[int] = None
    newest_timestamp: Optional[int] = None
    first_record_time: Optional[int] = None
    last_record_time: Optional[int] = None