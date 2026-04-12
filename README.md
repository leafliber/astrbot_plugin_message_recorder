<div align="center">

# 📝 AstrBot 消息记录器

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E4.16%2C%3C5-blue?style=for-the-badge)](https://github.com/Soulter/astrbot)
[![Python](https://img.shields.io/badge/Python-3.10+-green?style=for-the-badge)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

**多平台消息记录插件 | SQLite 存储 | Web 管理面板 | 丰富查询 API**

![](https://count.getloli.com/get/@astrbot-plugin-message-recorder?theme=moebooru-h)

</div>

---

## ✨ 功能特色

- 🔥 **全平台支持** - 支持 Telegram、Discord、QQ 官方/私有、微信等所有 AstrBot 接入的平台
- 💾 **SQLite 存储** - 轻量级本地数据库，无需额外配置，开箱即用
- 📊 **完整记录** - 保存消息文本、发送者、群组、时间戳、消息链等完整信息
- 🖼️ **多媒体保存** - 可选保存图片、语音、视频、文件到本地，支持原图/缩略图模式
- 🌐 **Web 管理面板** - 可视化仪表盘、消息搜索、数据导出/导入功能
- 🔍 **丰富查询** - 支持按发送者、群组、时间范围、关键词等多维度查询
- 🔌 **API 接口** - 提供完整 API 供其他插件调用，轻松获取历史消息
- 🧹 **自动清理** - 可配置保留天数和最大记录数，自动清理过期数据
- ⚡ **异步高效** - 使用 aiosqlite 异步操作，不影响消息处理性能

---

## 📦 安装

### 方式一：直接下载

1. 将本仓库克隆或下载到 AstrBot 的插件目录：
   ```
   AstrBot/data/plugins/astrbot_plugin_message_recorder/
   ```
2. 在 AstrBot WebUI 的「插件管理」页面点击「重载插件」

### 方式二：通过插件市场

在 AstrBot WebUI 的插件市场中搜索「消息记录器」并安装

### 依赖说明

如需使用 Web 管理面板，需安装 [astrbot_plugin_multi_web_manager](https://github.com/leafliber/astrbot_plugin_multi_web_manager) 插件。

---

## 🎛️ 配置项

在 AstrBot WebUI 的插件配置页面可调整以下选项：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enable_web_ui` | true | 是否启用 Web 管理面板 |
| `enable_commands` | true | 是否启用消息记录指令 |
| `max_records` | 0 | 最大消息记录数，超过时自动清理最旧记录（0 表示不限制） |
| `retention_days` | 0 | 消息保留天数，超过此天数自动清理（0 表示永久保留） |
| `save_message_chain` | true | 是否保存完整消息链（包含图片、表情等） |
| `save_raw_message` | false | 是否保存平台原始消息对象 |
| `cleanup_interval_hours` | 24 | 自动清理间隔（小时） |
| `save_media_files` | false | 是否保存多媒体文件（图片、语音、视频、文件）到本地 |
| `image_save_mode` | original | 图片保存模式：`original` 保存原图，`thumbnail` 保存缩略图 |

---

## 🌐 Web 管理面板

启用 Web 面板后，可通过 `/message_recorder/` 路径访问管理界面。

### 仪表盘

- **统计卡片** - 总消息数、群聊消息、私聊消息、平台数
- **时间趋势图** - 消息数量随时间变化的趋势
- **平台分布图** - 各平台消息占比
- **发送者排行** - 消息发送量排名
- **群组排行** - 群组活跃度排名

### 消息搜索

- 多条件组合搜索（平台、群组、发送者、时间范围、关键词）
- 分页浏览历史消息
- 查看消息详情和上下文
- 支持查看保存的媒体文件

### 数据导出

支持多种导出格式：

| 格式 | 说明 |
|------|------|
| JSON | 标准 JSON 格式，适合数据交换 |
| CSV | 表格格式，可用 Excel 打开 |
| MRPKG | 专用打包格式，包含媒体文件，支持导入 |

导出功能支持：
- 按条件筛选导出
- 异步后台处理，不阻塞操作
- 打包媒体文件（MRPKG 格式）

### 数据导入

- 支持 JSON、CSV、MRPKG 格式导入
- 大文件分片上传
- 导入进度实时显示
- 数据去重处理

---

## 📱 指令使用

> 指令功能可通过配置项 `enable_commands` 启用或禁用，默认启用。

### 基础指令

| 指令 | 说明 | 示例 |
|------|------|------|
| `/msg_record stats` | 查看消息统计信息 | `/msg_record stats` |
| `/msg_record cleanup` | 手动触发清理 | `/msg_record cleanup` |
| `/msg_record query [sender_id] [limit]` | 查询消息记录 | `/msg_record query 123456 20` |
| `/msg_record search <关键词> [limit]` | 搜索消息内容 | `/msg_record search hello 10` |
| `/msg_record help` | 查看帮助信息 | `/msg_record help` |

### 时间查询指令

| 指令 | 说明 | 示例 |
|------|------|------|
| `/msg_record today` | 查看今天的消息 | `/msg_record today` |
| `/msg_record yesterday` | 查看昨天的消息 | `/msg_record yesterday` |
| `/msg_record history <时间范围>` | 按时间范围查询 | `/msg_record history last7d` |

**时间范围格式支持：**

| 格式 | 说明 | 示例 |
|------|------|------|
| 自然语言 | `today`、`yesterday`、`week`、`month`、`hour` | `week` |
| 天数范围 | `last7d`、`last30d`、`last3d` 等 | `last7d` |
| 小时范围 | `last1h`、`last3h`、`last12h` 等 | `last3h` |
| 具体日期 | YYYY-MM-DD 格式 | `2024-01-15` |
| 日期范围 | 日期范围，用 `~` 分隔 | `2024-01-01~2024-01-15` |
| 相对时间 | `-1d`（昨天）、`-7d`（7天前）等 | `-3d` |

---

## 🔌 其他插件调用

本插件提供了完整的 API 接口，其他插件可以通过以下方式调用：

### 获取 API 实例

```python
from astrbot.api.star import Context

async def get_message_recorder_api(context: Context):
    """获取消息记录器 API"""
    recorder = context.get_registered_star("astrbot_plugin_message_recorder")
    if recorder and hasattr(recorder, "get_api"):
        return recorder.get_api()
    return None
```

### 核心 API：query() 和 count()

支持任意条件组合的统一查询方法：

```python
mr_api = await get_message_recorder_api(context)

# 基础查询 - 获取最近10条消息
messages = await mr_api.query(limit=10)

# 多条件组合查询
messages = await mr_api.query(
    platform="telegram",      # 平台
    group_id="123456",        # 群组 ID
    sender_id="user1",        # 发送者 ID
    time="today",             # 时间范围
    keyword="关键词",          # 内容搜索
    limit=20,
    order="desc"              # 排序方式
)

# 多 ID 查询（同时查询多个发送者）
messages = await mr_api.query(
    sender_ids=["user1", "user2", "user3"],
    time="last7d"
)

# 多群组查询
messages = await mr_api.query(
    group_ids=["group1", "group2"],
    message_type="group"
)

# 分页查询
messages = await mr_api.query(
    group_id="123456",
    limit=20,
    offset=40  # 第三页（跳过前40条）
)

# 统计符合条件的消息数量
count = await mr_api.count(
    platform="telegram",
    time="month"
)
```

### 快捷方法

```python
# 获取今天的消息
messages = await mr_api.get_today(limit=20)

# 获取昨天的消息
messages = await mr_api.get_yesterday(limit=20)

# 获取最近 N 小时的消息
messages = await mr_api.get_recent(hours=6, limit=50)

# 获取最近 N 天的消息
messages = await mr_api.get_recent_days(days=30, limit=100)

# 搜索消息内容
messages = await mr_api.search("关键词", limit=20)
messages = await mr_api.search("关键词", group_id="123456", time="week")

# 根据ID获取单条消息
message = await mr_api.get_by_id(123)

# 根据平台原始消息ID获取消息
message = await mr_api.get_by_platform_message_id("12345678")
message = await mr_api.get_by_platform_message_id("12345678", platform="telegram")

# 获取消息上下文
context_messages = await mr_api.get_context(message_id=123, before=5, after=5)
# 返回 {"before": [...], "after": [...]}

# 获取统计信息
stats = await mr_api.get_stats()
```

### query() 参数详解

| 参数 | 类型 | 说明 |
|------|------|------|
| `platform` | str | 单个平台名称 |
| `platforms` | List[str] | 多个平台列表 |
| `sender_id` | str | 单个发送者 ID |
| `sender_ids` | List[str] | 多个发送者 ID 列表 |
| `group_id` | str | 单个群组 ID |
| `group_ids` | List[str] | 多个群组 ID 列表 |
| `session_id` | str | 单个会话 ID |
| `session_ids` | List[str] | 多个会话 ID 列表 |
| `message_type` | str | 消息类型：`"group"` 或 `"private"` |
| `time` | str | 时间字符串（见下表） |
| `start_time` | int | 开始时间戳（毫秒） |
| `end_time` | int | 结束时间戳（毫秒） |
| `keyword` | str | 消息内容关键词 |
| `limit` | int | 返回数量限制 |
| `offset` | int | 偏移量（分页） |
| `order` | str | `"desc"` 倒序，`"asc"` 正序 |

### time 参数格式

| 格式 | 示例 | 说明 |
|------|------|------|
| 自然语言 | `today`、`yesterday`、`week`、`month` | 预设时间范围 |
| 天数范围 | `last7d`、`last30d`、`last3d` | 最近 N 天 |
| 小时范围 | `last1h`、`last3h`、`last12h` | 最近 N 小时 |
| 具体日期 | `2024-01-15` | 指定日期 |
| 日期范围 | `2024-01-01~2024-01-15` | 日期范围 |
| 相对时间 | `-1d`、`-7d`、`-3h` | N 天/小时前 |

### MessageRecord 数据结构

```python
@dataclass
class MessageRecord:
    id: int                    # 数据库自增ID
    platform: str              # 平台名称
    message_id: str            # 消息ID
    session_id: str            # 会话ID
    group_id: str              # 群组ID (私聊为 None)
    sender_id: str             # 发送者ID
    sender_name: str           # 发送者昵称
    message_type: str          # 消息类型 ("group" 或 "private")
    message_str: str           # 纯文本消息内容
    message_chain: str         # 消息链 JSON (包含图片、表情等)
    raw_message: str           # 原始消息 JSON
    timestamp: int             # 消息时间戳 (毫秒)
    created_at: int            # 记录创建时间 (毫秒)

# 辅助方法
message.to_dict()                        # 转为字典
message.get_message_chain_list()         # 解析消息链为列表
message.get_raw_message_dict()           # 解析原始消息为字典
```

---

## 📊 数据存储

### 数据库

消息存储在 SQLite 数据库中，路径为：

```
data/plugin_data/astrbot_plugin_message_recorder/messages.db
```

表结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 自增主键 |
| `platform` | TEXT | 平台标识 |
| `message_id` | TEXT | 消息 ID |
| `session_id` | TEXT | 会话 ID |
| `group_id` | TEXT | 群组 ID |
| `sender_id` | TEXT | 发送者 ID |
| `sender_name` | TEXT | 发送者昵称 |
| `message_type` | TEXT | 消息类型 |
| `message_str` | TEXT | 纯文本内容 |
| `message_chain` | TEXT | 消息链 JSON |
| `raw_message` | TEXT | 原始消息 JSON |
| `timestamp` | INTEGER | 消息时间戳 |
| `created_at` | INTEGER | 记录创建时间 |

### 多媒体文件

启用多媒体保存后，文件存储路径为：

```
data/plugin_data/astrbot_plugin_message_recorder/media/
├── images/     # 图片
│   └── 2026-04/   # 按年月分目录
├── records/    # 语音
├── videos/     # 视频
└── files/      # 其他文件
```

**文件命名规则：**

媒体文件使用**内容 SHA256 hash** 命名（取前16位），自动去重：
- 相同内容的文件只保存一份
- 避免重复下载和存储
- 文件名示例：`a1b2c3d4e5f6g7h8.jpg`

---

## 🖼️ 媒体文件 API

### 其他插件获取媒体文件

```python
mr_api = await get_message_recorder_api(context)

# 查询消息
messages = await mr_api.query(limit=10)

for msg in messages:
    # 从消息中提取媒体文件路径
    media_paths = mr_api.extract_media_paths(msg)
    
    for rel_path in media_paths:
        # 获取绝对路径（文件不存在返回 None）
        abs_path = mr_api.get_media_absolute_path(rel_path)
        if abs_path:
            with open(abs_path, "rb") as f:
                image_data = f.read()
        
        # 获取 Web 访问 URL
        web_url = mr_api.get_media_url(rel_path)
        # 返回: /message_recorder/api/media/images/2026-04/abc123.jpg
```

### 媒体相关 API 方法

| 方法 | 说明 |
|------|------|
| `get_media_base_path()` | 获取媒体文件存储根目录的绝对路径 |
| `get_media_absolute_path(rel_path)` | 获取媒体文件的绝对路径（文件不存在返回 None） |
| `get_media_url(rel_path)` | 获取媒体文件的 Web 访问 URL |
| `extract_media_paths(message)` | 从消息记录中提取所有媒体文件的相对路径 |

### Web API 访问媒体

媒体文件可通过 HTTP API 直接访问：

```
GET /message_recorder/api/media/{relative_path}
```

示例：
```
GET /message_recorder/api/media/images/2026-04/a1b2c3d4e5f6g7h8.jpg
```

消息详情 API 返回的 `message_chain` 中会自动包含 `media_url` 字段：

```json
{
  "message_chain": [
    {
      "type": "Image",
      "url": "https://example.com/image.jpg",
      "local_path": "images/2026-04/a1b2c3d4e5f6g7h8.jpg",
      "media_url": "/message_recorder/api/media/images/2026-04/a1b2c3d4e5f6g7h8.jpg"
    }
  ]
}
```

---

## 🛠️ 开发

### 本地调试

1. 克隆 AstrBot 本体和本插件仓库
2. 将插件目录放入 `AstrBot/data/plugins/`
3. 启动 AstrBot，在 WebUI 重载插件
4. 修改代码后点击「重载」即可热更新

### 代码格式化

提交前请使用 `ruff` 格式化代码：

```bash
ruff format .
```

---

## 📄 许可证

[MIT License](LICENSE)

---

## 🙏 致谢

- [AstrBot](https://github.com/Soulter/astrbot) - 强大的多平台聊天机器人框架

---

<div align="center">

**⭐ 如果这个插件对你有帮助，请给个 Star 支持！**

![](https://count.getloli.com/get/@astrbot-plugin-message-recorder?theme=moebooru-h&mute=1)

</div>
