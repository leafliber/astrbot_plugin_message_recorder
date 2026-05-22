"""database.py 集成测试 - 使用真实 SQLite 内存数据库"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import aiosqlite

from astrbot_plugin_message_recorder.database import Database, _row_to_record
from astrbot_plugin_message_recorder.models import MessageRecord, QueryFilter
from astrbot_plugin_message_recorder.serializer import compute_content_hash


@pytest.fixture
def tmp_db_path(tmp_path):
    return tmp_path / "test_messages.db"


@pytest.fixture
async def db(tmp_db_path):
    with patch(
        "astrbot_plugin_message_recorder.database.get_astrbot_plugin_data_path",
        return_value=str(tmp_db_path.parent),
    ):
        database = Database("test_plugin")
        database.db_path = tmp_db_path
        database._db = await aiosqlite.connect(tmp_db_path)
        await database._db.execute("PRAGMA journal_mode=WAL")
        await database._create_tables()
        yield database
        await database.close()


def _make_record(**overrides) -> MessageRecord:
    _uid = uuid.uuid4().hex[:8]
    defaults = dict(
        platform="telegram",
        message_id=f"msg_{_uid}",
        session_id="sess_001",
        group_id="grp_001",
        channel_id=None,
        sender_id="user_001",
        sender_name="Alice",
        message_type="group",
        message_str=f"Hello world {_uid}",
        message_chain=None,
        raw_message=None,
        reply_to_id=None,
        timestamp=time.time_ns() // 1_000_000,
    )
    defaults.update(overrides)
    return MessageRecord(**defaults)


class TestDatabaseInit:
    @pytest.mark.asyncio
    async def test_creates_tables(self, db):
        cursor = await db._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
        )
        assert await cursor.fetchone() is not None

    @pytest.mark.asyncio
    async def test_fts_table_exists(self, db):
        cursor = await db._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'"
        )
        assert await cursor.fetchone() is not None


class TestSaveMessage:
    @pytest.mark.asyncio
    async def test_save_and_retrieve(self, db):
        record = _make_record()
        record_id = await db.save_message(record)
        assert record_id > 0

        retrieved = await db.get_message_by_id(record_id)
        assert retrieved is not None
        assert retrieved.platform == "telegram"
        assert retrieved.sender_id == "user_001"
        assert retrieved.message_str.startswith("Hello world")

    @pytest.mark.asyncio
    async def test_duplicate_returns_minus_one(self, db):
        ts = 1700001000000
        record = _make_record(message_id="msg_dedup", message_str="dedup test", timestamp=ts)
        rid1 = await db.save_message(record)
        assert rid1 > 0

        record2 = _make_record(message_id="msg_dedup", message_str="dedup test", timestamp=ts)
        rid2 = await db.save_message(record2)
        assert rid2 == -1

    @pytest.mark.asyncio
    async def test_content_hash_dedup(self, db):
        ts = 1700002000000
        record = _make_record(message_id="", message_str="dedup test", timestamp=ts)
        rid1 = await db.save_message(record)
        assert rid1 > 0

        record2 = _make_record(message_id="", message_str="dedup test", timestamp=ts)
        rid2 = await db.save_message(record2)
        assert rid2 == -1

    @pytest.mark.asyncio
    async def test_auto_content_hash(self, db):
        record = _make_record(content_hash=None)
        rid = await db.save_message(record)
        assert rid > 0

        retrieved = await db.get_message_by_id(rid)
        assert retrieved.content_hash is not None
        assert len(retrieved.content_hash) == 16

    @pytest.mark.asyncio
    async def test_auto_created_at(self, db):
        before = int(time.time() * 1000)
        record = _make_record()
        rid = await db.save_message(record)
        after = int(time.time() * 1000)

        retrieved = await db.get_message_by_id(rid)
        assert before <= retrieved.created_at <= after

    @pytest.mark.asyncio
    async def test_different_platforms_same_message_id(self, db):
        r1 = _make_record(platform="telegram", message_id="100")
        r2 = _make_record(platform="discord", message_id="100")
        rid1 = await db.save_message(r1)
        rid2 = await db.save_message(r2)
        assert rid1 > 0
        assert rid2 > 0
        assert rid1 != rid2


class TestQueryMessages:
    @pytest.mark.asyncio
    async def test_query_by_platform(self, db):
        await db.save_message(_make_record(platform="telegram"))
        await db.save_message(_make_record(platform="discord"))

        results = await db.query_messages(QueryFilter(platform="telegram"))
        assert len(results) == 1
        assert results[0].platform == "telegram"

    @pytest.mark.asyncio
    async def test_query_by_sender_id(self, db):
        await db.save_message(_make_record(sender_id="user1"))
        await db.save_message(_make_record(sender_id="user2"))

        results = await db.query_messages(QueryFilter(sender_id="user1"))
        assert len(results) == 1
        assert results[0].sender_id == "user1"

    @pytest.mark.asyncio
    async def test_query_by_group_id(self, db):
        await db.save_message(_make_record(group_id="grp1"))
        await db.save_message(_make_record(group_id="grp2"))

        results = await db.query_messages(QueryFilter(group_id="grp1"))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_by_message_type(self, db):
        await db.save_message(_make_record(message_type="group"))
        await db.save_message(_make_record(message_type="private", group_id=None))

        results = await db.query_messages(QueryFilter(message_type="private"))
        assert all(r.message_type == "private" for r in results)

    @pytest.mark.asyncio
    async def test_query_with_limit(self, db):
        for i in range(10):
            await db.save_message(_make_record(message_id=f"msg_{i}"))

        results = await db.query_messages(QueryFilter(limit=5))
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_query_with_offset(self, db):
        for i in range(10):
            await db.save_message(_make_record(message_id=f"msg_{i}"))

        results = await db.query_messages(QueryFilter(limit=5, offset=5))
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_query_order_asc(self, db):
        for i in range(3):
            await db.save_message(
                _make_record(message_id=f"msg_{i}", timestamp=1700000000000 + i * 1000)
            )

        results = await db.query_messages(QueryFilter(order="asc"))
        assert results[0].timestamp < results[1].timestamp < results[2].timestamp

    @pytest.mark.asyncio
    async def test_query_order_desc(self, db):
        for i in range(3):
            await db.save_message(
                _make_record(message_id=f"msg_{i}", timestamp=1700000000000 + i * 1000)
            )

        results = await db.query_messages(QueryFilter(order="desc"))
        assert results[0].timestamp > results[1].timestamp > results[2].timestamp

    @pytest.mark.asyncio
    async def test_query_by_channel_id(self, db):
        await db.save_message(_make_record(channel_id="ch1"))
        await db.save_message(_make_record(channel_id="ch2"))

        results = await db.query_messages(QueryFilter(channel_id="ch1"))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_by_reply_to_id(self, db):
        await db.save_message(_make_record(reply_to_id="orig_001"))
        await db.save_message(_make_record(reply_to_id=None))

        results = await db.query_messages(QueryFilter(reply_to_id="orig_001"))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_keyword_like(self, db):
        await db.save_message(_make_record(message_str="Hello world"))
        await db.save_message(_make_record(message_str="Goodbye world", message_id="m2"))

        results = await db.query_messages(QueryFilter(keyword="Hello"))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_keyword_like_special_chars(self, db):
        await db.save_message(_make_record(message_str="50% off sale!"))
        results = await db.query_messages(QueryFilter(keyword="50%"))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_multiple_platforms(self, db):
        await db.save_message(_make_record(platform="telegram"))
        await db.save_message(_make_record(platform="discord"))
        await db.save_message(_make_record(platform="wechat"))

        results = await db.query_messages(QueryFilter(platforms=["telegram", "discord"]))
        assert len(results) == 2


class TestGetMessageById:
    @pytest.mark.asyncio
    async def test_existing(self, db):
        record = _make_record()
        rid = await db.save_message(record)
        result = await db.get_message_by_id(rid)
        assert result is not None
        assert result.id == rid

    @pytest.mark.asyncio
    async def test_nonexistent(self, db):
        result = await db.get_message_by_id(99999)
        assert result is None


class TestGetMessageByPlatformId:
    @pytest.mark.asyncio
    async def test_with_platform(self, db):
        await db.save_message(_make_record(platform="telegram", message_id="100"))
        result = await db.get_message_by_platform_id("100", "telegram")
        assert result is not None
        assert result.message_id == "100"

    @pytest.mark.asyncio
    async def test_without_platform(self, db):
        await db.save_message(_make_record(message_id="200"))
        result = await db.get_message_by_platform_id("200")
        assert result is not None

    @pytest.mark.asyncio
    async def test_not_found(self, db):
        result = await db.get_message_by_platform_id("nonexistent")
        assert result is None


class TestGetContextMessages:
    @pytest.mark.asyncio
    async def test_group_context(self, db):
        ts_base = 1700000000000
        for i in range(10):
            await db.save_message(
                _make_record(
                    message_id=f"ctx_{i}",
                    group_id="grp_ctx",
                    message_type="group",
                    timestamp=ts_base + i * 1000,
                )
            )

        target = await db.get_message_by_platform_id("ctx_5")
        context = await db.get_context_messages(target.id, before=2, after=2)
        assert len(context["before"]) <= 2
        assert len(context["after"]) <= 2

    @pytest.mark.asyncio
    async def test_nonexistent_target(self, db):
        context = await db.get_context_messages(99999)
        assert context["before"] == []
        assert context["after"] == []


class TestCountMessages:
    @pytest.mark.asyncio
    async def test_count_all(self, db):
        for i in range(5):
            await db.save_message(_make_record(message_id=f"cnt_{i}"))
        count = await db.count_messages(QueryFilter())
        assert count == 5

    @pytest.mark.asyncio
    async def test_count_with_filter(self, db):
        await db.save_message(_make_record(platform="telegram"))
        await db.save_message(_make_record(platform="discord"))
        count = await db.count_messages(QueryFilter(platform="telegram"))
        assert count == 1


class TestGetStats:
    @pytest.mark.asyncio
    async def test_stats(self, db):
        await db.save_message(_make_record(message_id="s1", message_type="group"))
        await db.save_message(_make_record(message_id="s2", message_type="private", group_id=None))
        await db.save_message(_make_record(message_id="s3", message_type="channel", channel_id="ch1"))

        stats = await db.get_stats()
        assert stats.total_count == 3
        assert stats.group_message_count == 1
        assert stats.private_message_count == 1
        assert stats.channel_message_count == 1


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_by_age(self, db):
        old_ts = int((time.time() - 100 * 86400) * 1000)
        await db.save_message(_make_record(message_id="old", timestamp=old_ts))
        await db.save_message(_make_record(message_id="new"))

        deleted = await db.cleanup_by_age(30)
        assert deleted == 1

        count = await db.count_messages(QueryFilter())
        assert count == 1

    @pytest.mark.asyncio
    async def test_cleanup_by_limit(self, db):
        for i in range(10):
            await db.save_message(_make_record(message_id=f"lim_{i}"))

        deleted = await db.cleanup_by_limit(5)
        assert deleted == 5

        count = await db.count_messages(QueryFilter())
        assert count == 5

    @pytest.mark.asyncio
    async def test_cleanup_by_age_zero(self, db):
        deleted = await db.cleanup_by_age(0)
        assert deleted == 0


class TestTimelineStats:
    @pytest.mark.asyncio
    async def test_timeline(self, db):
        ts = int(time.time() * 1000)
        await db.save_message(_make_record(message_id="tl1", message_str="msg A", timestamp=ts))
        await db.save_message(_make_record(message_id="tl2", message_str="msg B", timestamp=ts))

        stats = await db.get_timeline_stats(interval="day")
        assert len(stats) >= 1
        found = False
        for s in stats:
            if s["count"] == 2:
                found = True
                break
        assert found, f"Expected a day with count=2, got {stats}"


class TestSenderRanking:
    @pytest.mark.asyncio
    async def test_ranking(self, db):
        await db.save_message(_make_record(sender_id="u1", sender_name="Alice", message_id="r1"))
        await db.save_message(_make_record(sender_id="u1", sender_name="Alice", message_id="r2"))
        await db.save_message(_make_record(sender_id="u2", sender_name="Bob", message_id="r3"))

        ranking = await db.get_sender_ranking(limit=10)
        assert len(ranking) == 2
        assert ranking[0]["sender_id"] == "u1"
        assert ranking[0]["count"] == 2


class TestDistinctValues:
    @pytest.mark.asyncio
    async def test_distinct_platforms(self, db):
        await db.save_message(_make_record(platform="telegram"))
        await db.save_message(_make_record(platform="discord"))

        platforms = await db.get_distinct_platforms()
        assert "telegram" in platforms
        assert "discord" in platforms

    @pytest.mark.asyncio
    async def test_distinct_senders(self, db):
        await db.save_message(_make_record(sender_id="u1", sender_name="Alice"))
        senders = await db.get_distinct_senders()
        assert len(senders) >= 1

    @pytest.mark.asyncio
    async def test_distinct_groups(self, db):
        await db.save_message(_make_record(group_id="g1", message_type="group"))
        groups = await db.get_distinct_groups()
        assert len(groups) >= 1


class TestMediaPaths:
    @pytest.mark.asyncio
    async def test_get_media_paths_before(self, db):
        chain = json.dumps([{"type": "Image", "local_path": "images/2026/abc.jpg"}])
        old_ts = int((time.time() - 10 * 86400) * 1000)
        await db.save_message(_make_record(message_id="mp1", message_chain=chain, timestamp=old_ts))

        paths = await db.get_media_paths_before(int(time.time() * 1000))
        assert "images/2026/abc.jpg" in paths

    @pytest.mark.asyncio
    async def test_get_media_paths_over_limit(self, db):
        for i in range(5):
            chain = json.dumps([{"type": "Image", "local_path": f"images/{i}.jpg"}])
            await db.save_message(_make_record(message_id=f"mpl_{i}", message_chain=chain))

        paths = await db.get_media_paths_over_limit(3)
        assert len(paths) >= 1


