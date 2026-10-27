# 组件与目录检查

记录日期：2026-10-27。此文区分已验证的本地组件与尚未验证的真实 QQ。

| 组件 | 实际固定版本 | 证据 |
| --- | --- | --- |
| AstrBot | v4.29.3 | 官方标签源码归档；真实核心和插件加载测试 |
| NapCat Shell | v4.18.41 | 官方归档与发布摘要比对；仅静态检查，未启动 QQ |
| uv | 0.13.6 | 官方 Windows x64 归档与发布摘要比对 |
| Python | 3.12.16 | E:\QQAgent\runtime\python 私有安装 |
| aiocqhttp | 1.4.4 | 模拟反向 WS 收发与回执、错误令牌测试 |
| httpx | 0.28.1 | MockTransport 模拟响应 |
| 依赖 | 168 个包 | uv pip check 通过，版本保存于 versions.lock.json |

来源：[AstrBot](https://github.com/AstrBotDevs/AstrBot/releases/tag/v4.29.3)、[NapCat](https://github.com/NapNeko/NapCatQQ/releases/tag/v4.18.41)、[uv](https://github.com/astral-sh/uv/releases/tag/0.13.6)。

AstrBot 发布归档没有 uv.lock。本项目依据该标签的 pyproject.toml 解析生成了依赖锁，之后使用 --frozen 安装；不是上游提供的锁。源码归档的 SHA-256 是本地记录值；NapCat、uv 和 dashboard 归档另外比对了发布方给出的摘要。未修改上游业务源码、未替换系统 Python、未修改系统 PATH 或注册表。

路径：

- 源码：E:\QQAgent\plugins\mansui_companion
- 已校验的安装副本：E:\QQAgent\data\astrbot\data\plugins\mansui_companion
- 组件：E:\QQAgent\app\AstrBot、E:\QQAgent\app\NapCat
- 依赖、下载、临时文件：E:\QQAgent\runtime
- 模拟数据与 JUnit：E:\QQAgent\runtime\test-state
- 正式消息库预定：E:\QQAgent\data\mansui.sqlite3；本次未生成真实消息库
- ASTRBOT_ROOT=E:\QQAgent\data\astrbot，因此框架 data 位于其下的 data
- NAPCAT_WORKDIR=E:\QQAgent\data\napcat，控制 NapCat 配置、缓存与日志，不能代替 QQ 原生资料目录设置

接入保护在 AstrBot 消息转换前执行。非本人私聊不会读取正文；通过的事件仅保留文本、真正的小号 @ 和程序生成的身份信息。引用、转发、媒体不自动展开。默认 LLM、内置回复、追踪、原文日志与统计关闭。只使用本机带令牌的反向 WS，禁用不用的 HTTP 事件入口，并校验连接的小号 ID。

端口均为 127.0.0.1：6199 OneBot、6185 本项目状态/停止接口、6099 NapCat WebUI。AstrBot 通用管理后台关闭，避免它额外改动专用回复配置。

资源快照：本机可用物理内存总量约 31.85 GiB，检查时剩余约 8.87 GiB；E 盘剩余约 456.91 GiB，项目含依赖和下载约 1.28 GiB。剩余内存会随其他软件变化，不能当作安装内存。模型在 DeepSeek 服务器运行，不在本机加载大模型。本次数据不是 QQ 已登录后的资源实测。

待真实接入核对：

1. 已有 QQ 9.9.29.47354 与固定 NapCat 组合是否可用。
2. QQ 自身的会话、缓存实际目录；如必须写到 E:\QQAgent 之外，要先列明路径与影响获得批准。
3. 扫码、好友私聊、群 @、无 @ 的本人群消息、断线恢复与真实资源占用。
4. DeepSeek 账户的权限、余额、延迟与人物表现。

在上述 QQ 会话目录核实前，preflight 返回 qq_session_path_not_verified；versions.lock.json 不会自行标记为已验证。

GitHub 同类方案：[AstrBot](https://github.com/AstrBotDevs/AstrBot)提供多平台与插件框架，[NapCat](https://github.com/NapNeko/NapCatQQ)提供 NTQQ 接入，[MaiBot](https://github.com/Mai-with-u/MaiBot)也专注自然聊天伙伴。本项目沿用已批准的 AstrBot + NapCat，并把本人必回、私聊权限、记忆隔离和关系边界放在独立插件中；这些专属规则需要定制与测试，不能仅靠换一张角色卡保证。
