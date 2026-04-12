"""AstrBot 消息记录器插件主入口"""

import asyncio
import json
import time
from typing import Optional

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

from .database import Database
from .api import MessageRecorderAPI
from .models import MessageRecord
from .time_utils import parse_time_range, format_time_range, normalize_timestamp
from .media_downloader import MediaDownloader, MEDIA_TYPE_MAP


@register(
    name="astrbot_plugin_message_recorder",
    desc="多平台消息记录器，将消息保存到 SQLite 数据库",
    author="Leafiber",
    version="1.0.0",
)
class MessageRecorder(Star):
    """消息记录器插件主类"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._db: Optional[Database] = None
        self._api: Optional[MessageRecorderAPI] = None
        self._media_downloader: Optional[MediaDownloader] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._web_panel_registered: bool = False

    async def initialize(self):
        """插件初始化"""
        try:
            self._db = Database("astrbot_plugin_message_recorder")
            await self._db.init()

            if self.config.get("save_media_files", False):
                image_save_mode = self.config.get("image_save_mode", "original")
                self._media_downloader = MediaDownloader(
                    "astrbot_plugin_message_recorder",
                    image_save_mode=image_save_mode,
                )
                logger.info(
                    f"[MessageRecorder] 多媒体文件保存已启用，"
                    f"图片模式: {image_save_mode}"
                )

            self._api = MessageRecorderAPI(self._db, self._media_downloader)

            self._start_cleanup_task()
            await self._register_web_panel()
            logger.info("[MessageRecorder] 插件初始化完成")
        except Exception as e:
            logger.error(f"[MessageRecorder] 初始化失败: {e}")

    async def terminate(self):
        """插件终止"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._media_downloader:
            await self._media_downloader.close()

        if self._web_panel_registered:
            try:
                from data.plugins.astrbot_plugin_multi_web_manager import get_registry
                registry = get_registry()
                if registry:
                    removed = registry.unregister_plugin("astrbot_plugin_message_recorder")
                    if removed:
                        logger.info(f"[MessageRecorder] 已移除 {removed} 个 Web 路由")
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"[MessageRecorder] 卸载 Web 面板时出错: {e}")

        if self._db:
            await self._db.close()
        logger.info("[MessageRecorder] 插件已终止")

    def _start_cleanup_task(self):
        """启动定时清理任务"""
        interval_hours = self.config.get("cleanup_interval_hours", 24)
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(interval_hours)
        )

    async def _cleanup_loop(self, interval_hours: int):
        """定时清理循环"""
        interval_seconds = interval_hours * 3600
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self._do_cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MessageRecorder] 清理任务出错: {e}")

    async def _do_cleanup(self) -> dict:
        """执行清理操作"""
        result = {"by_age": 0, "by_limit": 0, "media_files": 0}
        if not self._db:
            return result

        retention_days = self.config.get("retention_days", 30)
        if retention_days > 0:
            media_paths = await self._db.get_media_paths_before(
                int((time.time() - retention_days * 86400) * 1000)
            )
            result["by_age"] = await self._db.cleanup_by_age(retention_days)
            if self._media_downloader and media_paths:
                result["media_files"] += self._media_downloader.delete_media_files(
                    media_paths
                )

        max_records = self.config.get("max_records", 100000)
        if max_records > 0:
            media_paths = await self._db.get_media_paths_over_limit(max_records)
            result["by_limit"] = await self._db.cleanup_by_limit(max_records)
            if self._media_downloader and media_paths:
                result["media_files"] += self._media_downloader.delete_media_files(
                    media_paths
                )

        total = result["by_age"] + result["by_limit"]
        if total > 0:
            logger.info(
                f"[MessageRecorder] 已清理 {total} 条消息记录，"
                f"{result['media_files']} 个媒体文件"
            )

        return result

    def get_api(self) -> Optional[MessageRecorderAPI]:
        """获取 API 接口，供其他插件调用"""
        return self._api

    async def _register_web_panel(self):
        """注册 Web 面板到 MultiWebManager"""
        # 检查 WebUI 开关
        enable_web_ui = self.config.get("enable_web_ui", True)
        if not enable_web_ui:
            logger.info("[MessageRecorder] Web 面板已禁用（配置 enable_web_ui=False）")
            return

        # 尝试导入依赖插件（使用 AstrBot 插件路径）
        try:
            from data.plugins.astrbot_plugin_multi_web_manager import get_registry
        except ImportError:
            logger.warning(
                "[MessageRecorder] 未找到 astrbot_plugin_multi_web_manager，"
                "Web 面板功能不可用。请确保该插件已安装并启用。"
            )
            return

        # 尝试注册 Web 面板
        try:
            from .web.blueprint import create_blueprint

            registry = get_registry()
            if registry is None:
                logger.warning("[MessageRecorder] MultiWebManager 注册中心未初始化，Web 面板注册失败")
                return

            blueprint = create_blueprint(self)

            registry.register_blueprint(
                plugin_name="astrbot_plugin_message_recorder",
                blueprint=blueprint,
                url_prefix="/message_recorder",
                description="消息记录器 Web 面板 - 支持消息查询、导出、导入和仪表盘统计"
            )

            # 设置插件元数据
            registry.set_plugin_metadata("astrbot_plugin_message_recorder", {
                "name": "消息记录器",
                "version": "1.0.0",
                "desc": "多平台消息记录器，提供 Web 面板进行查询、导出和统计",
                "author": "cassia",
            })

            logger.info("[MessageRecorder] Web 面板已注册到 MultiWebManager，访问 /message_recorder/")
            self._web_panel_registered = True
        except Exception as e:
            logger.error(f"[MessageRecorder] 注册 Web 面板失败: {e}")

    # ========== 消息监听 ==========

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """
        监听所有消息事件并保存到数据库
        注意：此监听器不应拦截消息，让事件继续传递
        """
        if not self._db:
            logger.debug("[MessageRecorder] 跳过消息: 数据库未初始化")
            return  # 不拦截，让事件继续

        # 使用 create_task 异步执行保存，避免阻塞事件处理
        asyncio.create_task(self._save_message_async(event))

    async def _save_message_async(self, event: AstrMessageEvent):
        """异步保存消息，不阻塞事件处理"""
        logger.debug("[MessageRecorder] 收到消息事件，开始处理")

        try:
            message_obj = event.message_obj
            platform = self._get_platform_name(event)

            normalized_timestamp = normalize_timestamp(message_obj.timestamp)

            record = MessageRecord(
                platform=platform,
                message_id=message_obj.message_id or "",
                session_id=message_obj.session_id or "",
                group_id=message_obj.group_id,
                sender_id=message_obj.sender.user_id if message_obj.sender else "",
                sender_name=message_obj.sender.nickname if message_obj.sender else None,
                message_type="group" if message_obj.group_id else "private",
                message_str=event.message_str,
                timestamp=normalized_timestamp,
            )

            if self.config.get("save_message_chain", True):
                message_chain = message_obj.message
                if message_chain:
                    chain_data = []
                    for comp in message_chain:
                        comp_data = self._serialize_component(comp)
                        if self._media_downloader and self.config.get("save_media_files", False):
                            await self._download_media_for_component(comp, comp_data)
                        chain_data.append(comp_data)
                    record.message_chain = json.dumps(chain_data)

            if self.config.get("save_raw_message", False):
                raw_msg = message_obj.raw_message
                if raw_msg:
                    try:
                        record.raw_message = json.dumps(raw_msg, ensure_ascii=False)
                    except (TypeError, ValueError):
                        record.raw_message = str(raw_msg)

            record_id = await self._db.save_message(record)

            content_preview = (event.message_str[:30] + "...") if event.message_str and len(event.message_str) > 30 else (event.message_str or "[非文本]")

            logger.debug(
                f"[MessageRecorder] 消息保存成功 #{record_id} | "
                f"平台: {platform} | 类型: {record.message_type} | "
                f"发送者: {record.sender_name or record.sender_id} | "
                f"内容: {content_preview}"
            )

        except Exception as e:
            logger.error(f"[MessageRecorder] 保存消息失败: {e}")

    def _get_platform_name(self, event: AstrMessageEvent) -> str:
        """获取平台名称"""
        try:
            return event.get_platform_name() or "unknown"
        except Exception:
            return "unknown"

    def _serialize_component(self, component) -> dict:
        """序列化消息组件"""
        result = {"type": component.__class__.__name__}

        attrs = [
            "text", "url", "file", "file_id", "file_unique_id",
            "width", "height", "name", "path",
        ]
        for attr in attrs:
            if hasattr(component, attr):
                value = getattr(component, attr)
                if value is not None:
                    result[attr] = value

        return result

    async def _download_media_for_component(self, component, comp_data: dict):
        """为消息组件下载多媒体文件"""
        comp_type = comp_data.get("type", "")
        if comp_type not in MEDIA_TYPE_MAP:
            return

        url = self._extract_media_url(component, comp_data)
        if not url:
            return

        try:
            filename = None
            if comp_type == "File" and hasattr(component, "name") and component.name:
                filename = component.name

            local_path = await self._media_downloader.download_media(
                url=url,
                component_type=comp_type,
                filename=filename,
            )
            if local_path:
                comp_data["local_path"] = local_path
        except Exception as e:
            logger.warning(
                f"[MessageRecorder] 下载多媒体文件失败 "
                f"(type={comp_type}): {e}"
            )

    def _extract_media_url(self, component, comp_data: dict) -> Optional[str]:
        """从消息组件中提取多媒体文件 URL"""
        if hasattr(component, "url") and component.url:
            return component.url

        file_val = comp_data.get("file")
        if isinstance(file_val, str) and file_val.startswith("http"):
            return file_val

        path_val = comp_data.get("path")
        if isinstance(path_val, str) and path_val.startswith("http"):
            return path_val

        return None

    def _check_commands_enabled(self, event: AstrMessageEvent) -> bool:
        """检查指令功能是否启用"""
        return self.config.get("enable_commands", True)

    # ========== 管理指令 ==========

    @filter.command_group("msg_record")
    def msg_record():
        """消息记录指令组"""
        pass

    @msg_record.command("stats")
    async def cmd_stats(self, event: AstrMessageEvent):
        """查看消息统计信息"""
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        stats = await self._api.get_stats()

        lines = [
            "📊 消息记录统计",
            f"总记录数: {stats.total_count}",
            f"群聊消息: {stats.group_message_count}",
            f"私聊消息: {stats.private_message_count}",
        ]

        if stats.platform_stats:
            lines.append("平台分布:")
            for platform, count in stats.platform_stats.items():
                lines.append(f"  - {platform}: {count}")

        if stats.oldest_timestamp:
            oldest_time = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(stats.oldest_timestamp / 1000)
            )
            lines.append(f"最早消息: {oldest_time}")

        if stats.newest_timestamp:
            newest_time = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(stats.newest_timestamp / 1000)
            )
            lines.append(f"最新消息: {newest_time}")

        yield event.plain_result("\n".join(lines))

    @msg_record.command("cleanup")
    async def cmd_cleanup(self, event: AstrMessageEvent):
        """手动触发清理"""
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        result = await self._do_cleanup()
        total = result["by_age"] + result["by_limit"]

        yield event.plain_result(f"✅ 已清理 {total} 条消息记录")

    @msg_record.command("query")
    async def cmd_query(self, event: AstrMessageEvent, sender: str = "", limit: int = 10):
        """查询消息记录 (sender: 发送者ID, limit: 数量)"""
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        if limit > 50:
            limit = 50

        messages = await self._api.query(sender_id=sender, limit=limit)

        if not messages:
            yield event.plain_result("未找到消息记录")
            return

        lines = [f"📝 查询到 {len(messages)} 条消息:"]
        for msg in messages:
            time_str = time.strftime(
                "%m-%d %H:%M",
                time.localtime(msg.timestamp / 1000)
            )
            content = msg.message_str or "[非文本消息]"
            # 截断长消息
            if len(content) > 50:
                content = content[:50] + "..."
            lines.append(f"[{time_str}] {msg.sender_name or msg.sender_id}: {content}")

        yield event.plain_result("\n".join(lines))

    @msg_record.command("search")
    async def cmd_search(self, event: AstrMessageEvent, keyword: str, limit: int = 10):
        """搜索消息内容 (keyword: 关键词, limit: 数量)"""
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        if limit > 50:
            limit = 50

        messages = await self._api.search(keyword, limit=limit)

        if not messages:
            yield event.plain_result(f"未找到包含 '{keyword}' 的消息")
            return

        lines = [f"🔍 找到 {len(messages)} 条包含 '{keyword}' 的消息:"]
        for msg in messages:
            time_str = time.strftime(
                "%m-%d %H:%M",
                time.localtime(msg.timestamp / 1000)
            )
            content = msg.message_str or "[非文本消息]"
            lines.append(f"[{time_str}] {msg.sender_name or msg.sender_id}: {content}")

        yield event.plain_result("\n".join(lines))

    @msg_record.command("help")
    async def cmd_help(self, event: AstrMessageEvent):
        """查看帮助信息"""
        if not self._check_commands_enabled(event):
            return
        help_text = """📖 消息记录器帮助

📊 统计与管理:
/msg_record stats - 查看统计信息
/msg_record cleanup - 手动清理

📝 时间查询:
/msg_record today - 查看今天的消息
/msg_record yesterday - 查看昨天的消息
/msg_record history <时间范围> - 按时间查询
  时间范围支持: last7d、last30d、week、month
  或日期: 2024-01-01、2024-01-01~2024-01-15

🔍 其他查询:
/msg_record query [sender_id] [limit] - 查询消息
/msg_record search <关键词> [limit] - 搜索消息

其他插件可通过 get_api() 方法调用查询接口。"""
        yield event.plain_result(help_text)

    @msg_record.command("today")
    async def cmd_today(self, event: AstrMessageEvent, limit: int = 20):
        """查看今天的消息"""
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        if limit > 50:
            limit = 50

        messages = await self._api.get_today(limit=limit)

        if not messages:
            yield event.plain_result("今天暂无消息记录")
            return

        lines = [f"📅 今天共 {len(messages)} 条消息:"]
        for msg in messages:
            time_str = time.strftime(
                "%H:%M",
                time.localtime(msg.timestamp / 1000)
            )
            content = msg.message_str or "[非文本消息]"
            if len(content) > 50:
                content = content[:50] + "..."
            lines.append(f"[{time_str}] {msg.sender_name or msg.sender_id}: {content}")

        yield event.plain_result("\n".join(lines))

    @msg_record.command("yesterday")
    async def cmd_yesterday(self, event: AstrMessageEvent, limit: int = 20):
        """查看昨天的消息"""
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        if limit > 50:
            limit = 50

        messages = await self._api.get_yesterday(limit=limit)

        if not messages:
            yield event.plain_result("昨天暂无消息记录")
            return

        lines = [f"📅 昨天共 {len(messages)} 条消息:"]
        for msg in messages:
            time_str = time.strftime(
                "%H:%M",
                time.localtime(msg.timestamp / 1000)
            )
            content = msg.message_str or "[非文本消息]"
            if len(content) > 50:
                content = content[:50] + "..."
            lines.append(f"[{time_str}] {msg.sender_name or msg.sender_id}: {content}")

        yield event.plain_result("\n".join(lines))

    @msg_record.command("history")
    async def cmd_history(self, event: AstrMessageEvent, time_range: str = "week", limit: int = 30):
        """按时间范围查询消息"""
        if not self._check_commands_enabled(event):
            return
        if not self._api:
            yield event.plain_result("数据库未初始化")
            return

        if limit > 50:
            limit = 50

        start_time, end_time = parse_time_range(time_range)
        time_desc = format_time_range(start_time, end_time)

        messages = await self._api.query(time=time_range, limit=limit)

        if not messages:
            yield event.plain_result(f"在 {time_desc} 期间暂无消息记录")
            return

        lines = [f"📅 {time_desc} 共 {len(messages)} 条消息:"]
        for msg in messages:
            time_str = time.strftime(
                "%m-%d %H:%M",
                time.localtime(msg.timestamp / 1000)
            )
            content = msg.message_str or "[非文本消息]"
            if len(content) > 50:
                content = content[:50] + "..."
            lines.append(f"[{time_str}] {msg.sender_name or msg.sender_id}: {content}")

        yield event.plain_result("\n".join(lines))