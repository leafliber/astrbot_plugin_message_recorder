<div align="center">

# 📝 AstrBot 消息记录器

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E4.16%2C%3C5-blue?style=for-the-badge)](https://github.com/Soulter/astrbot)
[![Python](https://img.shields.io/badge/Python-3.10+-green?style=for-the-badge)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue?style=for-the-badge)](LICENSE)

**多平台消息记录插件 | SQLite 存储 | Web 管理面板 | 丰富查询 API**

![](https://count.getloli.com/get/@astrbot-plugin-message-recorder?theme=moebooru-h)

</div>

---

## ✨ 功能特色

- 🔥 **全平台支持** - 支持 Telegram、Discord、QQ 官方/私有、微信等所有 AstrBot 接入的平台
- 💾 **SQLite 存储** - 轻量级本地数据库，WAL 模式，开箱即用
- 📊 **完整记录** - 保存消息文本、发送者、群组/频道、时间戳、消息链、回复关系等完整信息
- 🖼️ **多媒体保存** - 可选保存图片、语音、视频、文件到本地，支持原图/缩略图模式，内容哈希自动去重
- 🌐 **Web 管理面板** - 基于 AstrBot Plugin Pages 的可视化面板，骨架屏渐进式加载，内嵌于 Dashboard
- 🔍 **多维查询** - 支持按平台、发送者、群组、频道、时间范围、关键词、回复关系等多维度组合查询
- 📤 **数据导入导出** - 支持 JSON/CSV/MRPKG 格式导出，大文件分片上传导入，含媒体文件打包
- 🔌 **API 接口** - 提供完整 API 供其他插件调用，支持分页、统计、上下文查询
- 🧹 **自动清理** - 可配置保留天数和最大记录数，自动清理过期数据和孤立媒体文件
- ⚡ **异步高效** - 使用 aiosqlite 异步操作，并发下载控制，不影响消息处理性能

---

## 📦 安装

### 方式一：插件市场

在 AstrBot WebUI 的插件市场中搜索「消息记录器」并安装

### 方式二：手动安装

将本仓库克隆或下载到 AstrBot 的插件目录：

```
AstrBot/data/plugins/astrbot_plugin_message_recorder/
```

然后在 AstrBot WebUI 的「插件管理」页面点击「重载插件」

---

## 🎛️ 配置项

在 AstrBot WebUI 的插件配置页面可调整以下选项：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enable_commands` | `true` | 是否启用消息记录指令 |
| `max_records` | `0` | 最大消息记录数，超过时自动清理最旧记录（0 表示不限制） |
| `retention_days` | `0` | 消息保留天数，超过此天数自动清理（0 表示永久保留） |
| `save_message_chain` | `true` | 是否保存完整消息链（包含图片、表情等） |
| `save_raw_message` | `false` | 是否保存平台原始消息对象 |
| `cleanup_interval_hours` | `24` | 自动清理间隔（小时） |
| `save_media_files` | `false` | 是否保存多媒体文件（图片、语音、视频、文件）到本地 |
| `image_save_mode` | `original` | 图片保存模式：`original` 保存原图，`thumbnail` 保存缩略图 |

---

## 🌐 Web 管理面板

启用 Web 面板后，可在 AstrBot Dashboard 的插件页面中直接访问管理界面，无需额外安装依赖。

### 仪表盘

- **统计卡片** - 总消息数、群聊消息、私聊消息、平台数，交错动画展示
- **时间趋势图** - 消息数量随时间变化的趋势（ECharts 按需懒加载）
- **平台分布图** - 各平台消息占比饼图
- **发送者排行** - 消息发送量排名
- **群组排行** - 群组活跃度排名
- **时间范围切换** - 支持今日/近7天/近30天/近90天/全部

> 仪表盘采用渐进式渲染策略：各区域独立骨架屏加载，数据到达后即时填充，无需等待全部数据。

### 消息搜索

- 多条件组合搜索（平台、群组、发送者、时间范围、关键词）
- 高级筛选（频道、消息类型、回复消息）
- 分页浏览历史消息
- 查看消息详情（模态内联加载）
- 查看消息上下文
- 搜索结果可一键跳转导出

### 数据导出

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| JSON | `.json` | 标准 JSON 格式，适合数据交换和程序处理 |
| CSV | `.csv` | 表格格式，可用 Excel 等工具打开 |
| MRPKG | `.mrpkg` | 专用打包格式（ZIP），包含数据 + 媒体文件，支持导入还原 |

导出功能特性：
- 按条件筛选导出，复用搜索条件
- 异步后台处理，不阻塞操作
- 实时进度反馈（消息处理进度 + 媒体文件收集进度）
- 小文件 base64 直接下载，大文件通过 Dashboard 桥接下载
- MRPKG 格式包含完整媒体文件，支持跨实例迁移

### 数据导入

- 支持 JSON、CSV、MRPKG 格式导入
- 小文件（≤50MB）直接上传，大文件自动分片上传（5MB/片）
- 分片上传实时进度显示
- 两种导入模式：合并（添加新记录）/ 跳过重复（检测并跳过已存在记录）
- 导入进度实时轮询显示
- MRPKG 格式自动还原媒体文件

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
    if recorder:
        plugin_instance = getattr(recorder, "star_cls", None)
        if plugin_instance and hasattr(plugin_instance, "get_api"):
            return plugin_instance.get_api()
    return None
```

### 核心查询：query() 和 count()

```python
mr_api = await get_message_recorder_api(context)

# 基础查询
messages = await mr_api.query(limit=10)

# 多条件组合查询
messages = await mr_api.query(
    platform="telegram",
    group_id="123456",
    sender_id="user1",
    time="today",
    keyword="关键词",
    limit=20,
    order="desc"
)

# 多 ID 查询
messages = await mr_api.query(
    sender_ids=["user1", "user2", "user3"],
    time="last7d"
)

# 频道查询
messages = await mr_api.query(
    channel_id="987654",
    time="week"
)

# 回复查询
replies = await mr_api.query(
    reply_to_id="12345678",
    platform="discord"
)

# 分页查询
messages = await mr_api.query(
    group_id="123456",
    limit=20,
    offset=40
)

# 统计数量
count = await mr_api.count(platform="telegram", time="month")
```

### 快捷方法

```python
# 时间相关
messages = await mr_api.get_today(limit=20)
messages = await mr_api.get_yesterday(limit=20)
messages = await mr_api.get_recent(hours=6, limit=50)
messages = await mr_api.get_recent_days(days=30, limit=100)

# 搜索
messages = await mr_api.search("关键词", limit=20)
messages = await mr_api.search("关键词", group_id="123456", time="week")

# 单条查询
message = await mr_api.get_by_id(123)
message = await mr_api.get_by_platform_message_id("12345678", platform="telegram")

# 上下文
context_messages = await mr_api.get_context(message_id=123, before=5, after=5)
# 返回 {"before": [...], "after": [...]}

# 回复
replies = await mr_api.get_replies("12345678", platform="telegram")

# 频道
messages = await mr_api.get_by_channel("987654", time="week")

# 统计
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
| `channel_id` | str | 频道 ID（Discord 等） |
| `message_type` | str | 消息类型：`group`、`private`、`channel` |
| `time` | str | 时间字符串（见时间格式表） |
| `start_time` | int | 开始时间戳（毫秒），与 time 互斥 |
| `end_time` | int | 结束时间戳（毫秒），与 time 互斥 |
| `keyword` | str | 消息内容关键词 |
| `reply_to_id` | str | 回复的目标消息 ID |
| `limit` | int | 返回数量限制 |
| `offset` | int | 偏移量（分页） |
| `order` | str | `desc` 倒序，`asc` 正序 |

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
    id: Optional[int]           # 数据库自增ID
    platform: str               # 平台名称
    message_id: str             # 平台消息ID
    session_id: str             # 会话ID
    group_id: Optional[str]     # 群组ID (私聊为 None)
    channel_id: Optional[str]   # 频道ID (Discord等)
    sender_id: str              # 发送者ID
    sender_name: Optional[str]  # 发送者昵称
    message_type: str           # 消息类型 (group/private/channel)
    message_str: Optional[str]  # 纯文本消息内容
    message_chain: Optional[str] # 消息链JSON (包含图片、表情等)
    raw_message: Optional[str]  # 原始消息JSON
    reply_to_id: Optional[str]  # 回复的目标消息ID
    content_hash: Optional[str] # 内容哈希 (用于去重)
    timestamp: int              # 消息时间戳 (毫秒)
    created_at: int             # 记录创建时间 (毫秒)

# 辅助方法
message.to_dict()                        # 转为字典
message.get_message_chain_list()         # 解析消息链为列表
message.get_raw_message_dict()           # 解析原始消息为字典
```

---

## 📊 数据存储

### 数据库

消息存储在 SQLite 数据库中（WAL 模式），路径为：

```
data/plugin_data/astrbot_plugin_message_recorder/messages.db
```

表结构（Schema Version 2）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 自增主键 |
| `platform` | TEXT NOT NULL | 平台标识 |
| `message_id` | TEXT | 平台消息 ID |
| `session_id` | TEXT | 会话 ID |
| `group_id` | TEXT | 群组 ID |
| `channel_id` | TEXT | 频道 ID |
| `sender_id` | TEXT NOT NULL | 发送者 ID |
| `sender_name` | TEXT | 发送者昵称 |
| `message_type` | TEXT NOT NULL | 消息类型 |
| `message_str` | TEXT | 纯文本内容 |
| `message_chain` | TEXT | 消息链 JSON |
| `raw_message` | TEXT | 原始消息 JSON |
| `reply_to_id` | TEXT | 回复目标消息 ID |
| `content_hash` | TEXT | 内容哈希（去重） |
| `timestamp` | INTEGER NOT NULL | 消息时间戳 |
| `created_at` | INTEGER NOT NULL | 记录创建时间 |

索引：
- `(platform, message_id)` 唯一索引 — 防止同平台同消息重复入库
- `(platform, content_hash)` 唯一索引 — 内容级别去重
- `timestamp`、`sender_id`、`group_id`、`channel_id`、`session_id`、`reply_to_id` 常规索引
- FTS5 全文搜索索引 — 支持消息内容关键词搜索

### 多媒体文件

启用多媒体保存后，文件存储路径为：

```
data/plugin_data/astrbot_plugin_message_recorder/media/
├── images/       # 图片
│   ├── a1/       # 按内容哈希前2位分目录
│   ├── b2/
│   └── ...
├── records/      # 语音
├── videos/       # 视频
└── files/        # 其他文件
```

**存储策略：**

- 文件名使用**内容 SHA256 哈希**（取前16位），相同内容只保存一份
- 目录按哈希前2位分组，避免单目录文件过多，同时确保跨时间段的相同文件不会重复存储
- 文件名示例：`a1b2c3d4e5f6g7h8.jpg`

---

## 🖼️ 媒体文件 API

### 其他插件获取媒体文件

```python
mr_api = await get_message_recorder_api(context)

messages = await mr_api.query(limit=10)

for msg in messages:
    media_paths = mr_api.extract_media_paths(msg)

    for rel_path in media_paths:
        # 获取绝对路径（文件不存在返回 None）
        abs_path = mr_api.get_media_absolute_path(rel_path)
        if abs_path:
            with open(abs_path, "rb") as f:
                image_data = f.read()

        # 获取 Web 访问 URL
        web_url = mr_api.get_media_url(rel_path)
```

### 媒体相关 API 方法

| 方法 | 说明 |
|------|------|
| `get_media_base_path()` | 获取媒体文件存储根目录的绝对路径 |
| `get_media_absolute_path(rel_path)` | 获取媒体文件的绝对路径（文件不存在返回 None） |
| `get_media_url(rel_path)` | 获取媒体文件的 Web 访问 URL |
| `extract_media_paths(message)` | 从消息记录中提取所有媒体文件的相对路径 |

### Web API 访问媒体

```
GET /message_recorder/api/media/{relative_path}
```

消息详情 API 返回的 `message_chain` 中会自动包含 `media_url` 字段：

```json
{
  "message_chain": [
    {
      "type": "Image",
      "url": "https://example.com/image.jpg",
      "local_path": "images/a1/a1b2c3d4e5f6g7h8.jpg",
      "media_url": "/message_recorder/api/media/images/a1/a1b2c3d4e5f6g7h8.jpg"
    }
  ]
}
```

---

## 🔗 Web API 列表

插件注册了以下 Web API 端点（前缀 `/message_recorder/api/`）：

| 端点 | 方法 | 说明 |
|------|------|------|
| `stats` | GET | 获取统计概览 |
| `stats/timeline` | GET | 获取时间趋势数据 |
| `stats/senders` | GET | 获取发送者排行 |
| `stats/groups` | GET | 获取群组排行 |
| `messages` | GET | 查询消息列表 |
| `message/detail` | GET | 获取消息详情 |
| `message/context` | GET | 获取消息上下文 |
| `search` | GET | 搜索消息 |
| `export` | POST | 创建导出任务 |
| `export/status` | GET | 查询导出状态 |
| `export/download` | GET | 下载导出文件（大文件） |
| `export/download_data` | GET | 获取导出文件数据（base64，小文件） |
| `import/upload` | POST | 简单文件导入 |
| `import/init` | POST | 初始化分片导入 |
| `import/chunk/<session_id>/<index>` | POST | 上传分片 |
| `import/complete` | POST | 完成分片导入 |
| `import/status` | GET | 查询导入状态 |
| `platforms` | GET | 获取平台列表 |
| `senders` | GET | 获取发送者列表 |
| `groups` | GET | 获取群组列表 |
| `media` | GET | 获取媒体文件 |
| `schema_version` | GET | 获取数据库 Schema 版本 |

---

## 🏗️ 项目结构

```
astrbot_plugin_message_recorder/
├── main.py                  # 插件主入口
├── message_recorder/        # 核心源码
│   ├── __init__.py
│   ├── api.py               # 对外 API 接口
│   ├── database.py          # SQLite 数据库操作
│   ├── media_downloader.py  # 多媒体文件下载
│   ├── models.py            # 数据模型定义
│   ├── platform_adapter.py  # 平台适配器
│   ├── serializer.py        # 消息链序列化
│   ├── time_utils.py        # 时间工具
│   └── web_api.py           # Web API 注册
├── pages/                   # Web 前端页面
│   └── recorder/
├── tests/                   # 测试用例
├── _conf_schema.json        # 配置项定义
├── metadata.yaml            # 插件元数据
└── requirements.txt         # 依赖列表
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

### 运行测试

```bash
python3 -m pytest tests/ -v
```

---

## 📄 许可证

[GNU Affero General Public License v3.0](LICENSE)

---

## 🙏 致谢

- [AstrBot](https://github.com/Soulter/astrbot) - 强大的多平台聊天机器人框架

---

<div align="center">

**⭐ 如果这个插件对你有帮助，请给个 Star 支持！**

![](https://count.getloli.com/get/@astrbot-plugin-message-recorder?theme=moebooru-h&mute=1)

</div>
