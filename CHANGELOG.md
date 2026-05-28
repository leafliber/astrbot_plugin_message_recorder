# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.2] - 2025-05-28

### Changed

- **项目结构重组**：将核心模块移入 `message_recorder/` 子目录，`main.py` 通过 `sys.path` 引入插件根目录，使用 `from message_recorder.xxx` 形式导入，避免与其他插件冲突
- **许可证变更**：从 MIT License 更改为 GNU Affero General Public License v3.0
- **配置默认值调整**：`max_records` 默认值从 `100000` 改为 `0`（不限制），`retention_days` 默认值从 `30` 改为 `0`（永久保留）

### Added

- 新增 `message_recorder/` 目录，包含以下模块：
  - `api.py` — 对外 API 接口
  - `database.py` — SQLite 数据库操作
  - `media_downloader.py` — 多媒体文件下载与保存
  - `models.py` — 数据模型定义（MessageRecord、QueryFilter、MessageStats）
  - `platform_adapter.py` — 平台适配器（Telegram、Discord、QQ 官方/私有、微信）
  - `serializer.py` — 消息链序列化与反序列化
  - `time_utils.py` — 时间解析与格式化工具
  - `web_api.py` — Web API 注册模块
- 新增 `CHANGELOG.md` 变更日志文件
- 完整的单元测试套件（220 个测试用例）

### Removed

- 移除根目录下的散落模块文件（已移入 `message_recorder/` 目录）

## [0.0.1] - 2024-12-01

### Added

- 初始发布版本
- 多平台消息记录（Telegram、Discord、QQ 官方/私有、微信）
- SQLite 数据库存储（WAL 模式）
- 完整消息链、回复关系、内容哈希去重
- 多媒体文件保存（图片、语音、视频、文件）
- Web 管理面板（仪表盘、消息搜索、数据导入导出）
- 指令系统（stats、query、search、today、yesterday、history）
- 对外 API 接口供其他插件调用
- 自动清理过期数据和孤立媒体文件
- FTS5 全文搜索索引
- JSON/CSV/MRPKG 格式导入导出
