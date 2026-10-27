# 满穗 QQ 聊天伙伴 Implementation Plan

> **For agentic workers:** Use `executing-plans` to implement this plan task by task in the current conversation after the file scope is explicitly approved. Do not dispatch subagents, commit, publish, log in to QQ, or send real messages without the corresponding user authorization. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Windows 本机制作原作满穗风格的 QQ 伙伴：本人私聊和已启用群内的本人消息逐条回应，仅本人可私聊，其他成员 @ 必回、普通群话题自主参与，带持久记忆、好感度、用量统计和本地启停入口。

**Architecture:** NapCat 通过带令牌的本机 OneBot v11 反向 WebSocket 连接 AstrBot；入口权限保护早于 AstrBot 的消息转换与日志，满穗插件独占回复通路。插件直接调用 DeepSeek Chat Completions，统一控制上下文、重试、用量和结构化输出，SQLite 按私聊、群、群成员隔离状态。源码、依赖、下载、缓存和项目生成的数据全部限定在 `E:\QQAgent`，不在本机运行大模型。

**Tech Stack:** Python 3.12.16、uv 0.13.6、AstrBot v4.29.3、NapCat v4.18.41、httpx、SQLite、pytest / pytest-asyncio、PowerShell、Windows CMD；模型 `deepseek-flash`，非思考模式。

---

> 执行状态（2026-10-27）：A 范围制作及离线验证完成，最终 53 项测试、13 个子测试通过。下方原始任务清单保留作为实施依据，实际进度及修订见末尾执行记录和 docs/acceptance.md。B 真实接入未执行。

## 1. 状态、依据与实施边界

- 日期：2026-10-27；时区：Asia/Shanghai。
- 依据：`E:\QQAgent\docs\superpowers\specs\2026-10-27-mansui-qq-design.md`，用户已经批准设计。
- 设计快照 SHA-256：`82A460C51FFF953ECCB7D2B09AB568B4262DB92EBF698E811F19C5855E1AA968`。
- 本轮获准创建的唯一文件是本计划及其必要父目录。当前尚未安装组件、创建插件源码、运行测试、登录 QQ 或请求付费模型。
- 下文所有实施任务均未执行；测试命令和预期结果不代表已经测试通过。
- 这是一套相互依赖的本地应用，使用一份计划；权限与数据处理先形成可独立离线验收的核心，再接入 AstrBot 和 NapCat。
- 当前没有 Git 仓库，不自动初始化、提交、推送、创建工作树或发布插件。上游源码优先使用固定版本归档，保留许可证。

### 1.1 已核对的上游事实与实施结论

1. AstrBot 官方发布页当前指向 v4.29.3，源码要求 Python >= 3.12。以该标签和源代码归档固定本次适配；不能用启动脚本每次拉取最新分支。[发布页](https://github.com/AstrBotDevs/AstrBot/releases/tag/v4.29.3)、[依赖声明](https://raw.githubusercontent.com/AstrBotDevs/AstrBot/v4.29.3/pyproject.toml)。
2. AstrBot 的 `ASTRBOT_ROOT` 控制运行根目录，其数据位于根目录下的 `data`。本项目取 `E:\QQAgent\data\astrbot`，因此实际上游数据路径是 `E:\QQAgent\data\astrbot\data`，不要误认为环境变量直接指定 data 目录。[路径源码](https://raw.githubusercontent.com/AstrBotDevs/AstrBot/v4.29.3/astrbot/core/utils/astrbot_path.py)。
3. AstrBot 消息转换入口会先输出原始事件调试日志，事件构造还包含追踪信息。因此仅在普通插件处理器里丢弃他人私聊不够：需要启动前安装入口检查，并关闭原始日志和追踪。[适配器源码](https://raw.githubusercontent.com/AstrBotDevs/AstrBot/v4.29.3/astrbot/core/platform/sources/aiocqhttp/aiocqhttp_platform_adapter.py)、[事件源码](https://raw.githubusercontent.com/AstrBotDevs/AstrBot/v4.29.3/astrbot/core/platform/astr_message_event.py)。
4. NapCat v4.18.41 支持 `NAPCAT_WORKDIR`，控制配置、日志和缓存目录；本项目取 `E:\QQAgent\data\napcat`。它不能证明 QQ 自身的会话资料也已迁移，QQ 数据路径必须另外验证。[发布页](https://github.com/NapNeko/NapCatQQ/releases/tag/v4.18.41)、[路径源码](https://raw.githubusercontent.com/NapNeko/NapCatQQ/v4.18.41/packages/napcat-common/src/path.ts)。
5. NapCat 普通日志可包含收发内容，WebUI 的内存日志订阅也可能接收这些日志。正常运行同时关闭 `fileLog` 与 `consoleLog`，使用本项目只含状态码的运行状态记录；仅调整日志级别不视为完整隔离。[日志源码](https://raw.githubusercontent.com/NapNeko/NapCatQQ/v4.18.41/packages/napcat-core/helper/log.ts)、[配置源码](https://raw.githubusercontent.com/NapNeko/NapCatQQ/v4.18.41/packages/napcat-core/helper/config.ts)。
6. NapCat Windows 启动脚本会定位已安装 QQ；Windows 10 有专用启动入口。不要执行会强制结束所有 QQ 的批处理，不改写现有 QQ 的安装文件。[Windows 启动说明](https://napneko.github.io/guide/boot/Shell)、[启动源码](https://raw.githubusercontent.com/NapNeko/NapCatQQ/v4.18.41/packages/napcat-shell-loader/launcher-win10-user.bat)。
7. DeepSeek 使用 `https://api.deepseek.com/chat/completions`，模型 `deepseek-flash`。思考模式当前默认打开，因此请求必须显式加入 `thinking: {type: disabled}`；模型返回的推理字段不保存、不发送给 QQ。[首次调用](https://api-docs.deepseek.com/zh-cn/)、[思考参数](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)。
8. uv 0.13.6 的发布记录列出 CPython 3.12.16。私有运行时使用明确的目录变量，并关闭 Windows 注册与 PATH 安装；不会替换用户现有 Python。[uv 发布](https://github.com/astral-sh/uv/releases/tag/0.13.6)、[环境变量](https://docs.astral.sh/uv/reference/environment/)。

上面的版本是本计划核对到的候选组合，不代表 QQ 9.9.29.47354 已通过 NapCat 兼容性测试。实际归档哈希、Windows 依赖解析、QQ 会话路径以及启动参数必须由任务 1 的检查记录确认，不能猜测不存在的参数来强行迁移资料。

## 2. 待批准的写入清单

### 2.1 A 范围：制作程序、准备依赖、离线验证

批准 A 范围后，允许创建和迭代以下文件、以及列出的组件和生成数据目录。文件列表是实施边界，不表示本轮已经创建。新增表外文件或写入根目录之外必须重新列明范围。

| 具体文件 | 职责 |
| --- | --- |
| `E:\QQAgent\README.md` | 启动、配置、停止、排错与数据说明 |
| `E:\QQAgent\config\mansui.example.json` | 无密钥、无真实账号的配置示例 |
| `E:\QQAgent\config\versions.lock.json` | 上游标签、归档 URL、哈希、实际解释器与依赖版本 |
| `E:\QQAgent\scripts\environment.ps1` | 仅对子进程生效的所有路径变量 |
| `E:\QQAgent\scripts\prepare.ps1` | 下载、检查归档、准备私有环境与插件安装副本 |
| `E:\QQAgent\scripts\preflight.py` | 路径、版本、端口、配置和权限保护自检 |
| `E:\QQAgent\scripts\configure.py` | 本机交互配置，密钥输入不回显 |
| `E:\QQAgent\scripts\boot_astrbot.py` | 安装入口保护后启动 AstrBot |
| `E:\QQAgent\scripts\ingress_guard.py` | 原始消息权限门、框架保护与插件健康检查 |
| `E:\QQAgent\scripts\start.ps1` | 本项目后台启动、互斥和状态登记 |
| `E:\QQAgent\scripts\stop.ps1` | 请求有序停止，仅操作本项目进程 |
| `E:\QQAgent\scripts\status.py` | 本机连接、队列、用量、费用提醒与故障状态 |
| `E:\QQAgent\scripts\maintenance.py` | 数据保留、日志轮转、临时缓存和安全备份 |
| `E:\QQAgent\启动满穗.cmd` | 双击启动入口 |
| `E:\QQAgent\停止满穗.cmd` | 双击停止入口 |
| `E:\QQAgent\配置满穗.cmd` | 双击配置入口 |
| `E:\QQAgent\查看状态.cmd` | 双击查看状态入口 |
| `E:\QQAgent\plugins\mansui_companion\__init__.py` | 包入口 |
| `E:\QQAgent\plugins\mansui_companion\metadata.yaml` | AstrBot 插件元数据 |
| `E:\QQAgent\plugins\mansui_companion\domain.py` | 事件、路由与结果类型 |
| `E:\QQAgent\plugins\mansui_companion\settings.py` | 配置读取和严格校验 |
| `E:\QQAgent\plugins\mansui_companion\policy.py` | 账号权限、结构化 @、本人必回判断 |
| `E:\QQAgent\plugins\mansui_companion\store.py` | 数据库、状态机与事务 |
| `E:\QQAgent\plugins\mansui_companion\schema.sql` | 数据表、索引、版本 |
| `E:\QQAgent\plugins\mansui_companion\affinity.py` | 关系分数和限幅 |
| `E:\QQAgent\plugins\mansui_companion\memory.py` | 上下文、记忆、来源与遗忘 |
| `E:\QQAgent\plugins\mansui_companion\deepseek.py` | 模型请求、有限重试、用量解析 |
| `E:\QQAgent\plugins\mansui_companion\usage.py` | 日月统计、估价、提醒 |
| `E:\QQAgent\plugins\mansui_companion\scheduler.py` | 会话顺序、有限队列、并发和清理 |
| `E:\QQAgent\plugins\mansui_companion\service.py` | 处理消息、生成结果、发送后提交 |
| `E:\QQAgent\plugins\mansui_companion\commands.py` | 本人私聊中的管理命令 |
| `E:\QQAgent\plugins\mansui_companion\onebot.py` | 事件归一化和带发送回执的纯文本回复 |
| `E:\QQAgent\plugins\mansui_companion\main.py` | AstrBot 生命周期及消息处理器 |
| `E:\QQAgent\plugins\mansui_companion\persona.md` | 人物提示词 |
| `E:\QQAgent\plugins\mansui_companion\persona-sources.md` | 原作依据、适配设定和样例评审 |
| `E:\QQAgent\tests\conftest.py` | 合成消息、假模型、假时钟、假发送端 |
| `E:\QQAgent\tests\test_policy.py` | 权限和本人必回 |
| `E:\QQAgent\tests\test_storage.py` | 去重、隔离、恢复、发送事务 |
| `E:\QQAgent\tests\test_affinity.py` | 好感度边界和日期切换 |
| `E:\QQAgent\tests\test_memory.py` | 上下文、纠正、遗忘和来源失效 |
| `E:\QQAgent\tests\test_deepseek.py` | 请求参数、错误、重试和输出校验 |
| `E:\QQAgent\tests\test_usage.py` | 费用未知值与超过旧请求上限 |
| `E:\QQAgent\tests\test_scheduler.py` | 并发、排队、异常、重启 |
| `E:\QQAgent\tests\test_service.py` | 连续参与、沉默、本人回复完整性 |
| `E:\QQAgent\tests\test_astrbot.py` | 上游接入、入口私聊拦截、默认回复关闭 |
| `E:\QQAgent\tests\test_lifecycle.py` | 启停、重复启动、PID 复用和目录限制 |
| `E:\QQAgent\tests\test_acceptance.py` | A01–A19 的端到端模拟场景 |
| `E:\QQAgent\docs\compatibility.md` | 兼容检查证据与实际落盘路径 |
| `E:\QQAgent\docs\acceptance.md` | 验收编号、命令、实际结果和限制 |
| `E:\QQAgent\docs\operations.md` | 本机配置、密钥申请、扫码和日常维护 |
| `E:\QQAgent\docs\superpowers\plans\2026-10-27-mansui-qq-implementation.md` | 执行时登记进度与经批准的修订 |

批量生成目录也属于待批准范围，逐一说明其内容：

| 目录或生成文件 | A 范围允许内容 |
| --- | --- |
| `E:\QQAgent\app\AstrBot\` | v4.29.3 上游完整归档、锁文件、相匹配的 WebUI 资源；不直接修改框架业务源码 |
| `E:\QQAgent\app\NapCat\` | v4.18.41 Shell 归档解包；A 范围只检查，不运行 QQ 加载器 |
| `E:\QQAgent\runtime\tools\uv\` | uv 0.13.6 Windows x64 便携包 |
| `E:\QQAgent\runtime\python\` | uv 管理的 CPython 3.12.16 解释器与标准库 |
| `E:\QQAgent\runtime\python-bin\` | 私有解释器入口，禁止添加系统 PATH |
| `E:\QQAgent\runtime\venv\` | 本项目虚拟环境、上游锁定依赖、插件和测试依赖 |
| `E:\QQAgent\runtime\downloads\` | 官方归档、校验文件和安全解包暂存文件 |
| `E:\QQAgent\runtime\uv-cache\` | uv 下载、解析、构建缓存 |
| `E:\QQAgent\runtime\pip-cache\` | 组件确需 pip 时的缓存 |
| `E:\QQAgent\runtime\tmp\` | 项目安装和子进程临时文件 |
| `E:\QQAgent\runtime\test-state\` | 全部合成测试数据、SQLite 临时库、JUnit 报告、测试进程状态 |
| `E:\QQAgent\runtime\state\` | 不含消息正文和密钥的 PID、启动时间、健康状态；A 只写模拟状态 |
| `E:\QQAgent\data\astrbot\data\plugins\mansui_companion\` | 上表插件源码的安装副本，不用文件系统联接重定向用户目录 |
| `E:\QQAgent\logs\` | 脱敏构建、测试状态日志；无真实聊天和原始密钥 |

A 范围可联网获取官方代码、依赖和文档，可运行本机模拟 HTTP/WebSocket 服务及无 QQ 账号的框架测试。模拟程序默认只监听 127.0.0.1、使用临时端口并在测试结束退出。未获 A 范围批准之前，不执行上述写入或下载。

### 2.2 B 范围：接入真实账号后才生成的文件与外部操作

此范围将在离线验收完成、明确测试账号与群号后再确认，不与 A 的制作授权混同：

- `E:\QQAgent\config\mansui.local.json`：真实本人 QQ、群名单、小号 ID 与本机配置。
- `E:\QQAgent\config\secrets.local.json`：DeepSeek Key、OneBot 令牌及本机管理凭据；只由用户本机填写，不回传开发对话。
- `E:\QQAgent\data\mansui.sqlite3` 及 SQLite 的 `-wal`、`-shm` 文件：真实聊天与关系。
- `E:\QQAgent\data\astrbot\data\`：AstrBot 配置、上游数据库、静态资源及必要运行目录。
- `E:\QQAgent\data\napcat\`：NapCat 配置、缓存及必要运行目录，其中账户配置按实际小号 ID 命名，先在本机展示实际文件名。
- `E:\QQAgent\data\qq\`：期望的专用 QQ 会话资料目录，只有明确验证上游支持才启用；不把 `NAPCAT_WORKDIR` 当成 QQ 会话迁移开关。
- `E:\QQAgent\backups\`：仅白名单配置结构和人设备份；不含聊天、密钥、登录凭据。
- `E:\QQAgent\runtime\state\` 与 `E:\QQAgent\logs\`：真实运行的脱敏状态、进程记录及轮转日志。

B 包括用户扫码、小额实际 API 调用、向明确测试群和本人私聊发送测试消息。若 QQ 必须在既有安装目录或用户配置目录写入，先报告确切路径与影响再批准；不修改主号会话、不全局移动 QQ 数据、不自动关闭其他 QQ 进程。服务器、开机自启、系统防火墙、系统 PATH 和注册表修改均不在 A/B 中。

## 3. 全局实现约定与接口

### 3.1 路由优先级

按顺序执行：检查平台/小号身份 → 拒绝非本人私聊与非白名单群 → 拒绝自身消息 → 平台事件 ID 去重 → 本人私聊/群消息必回 → 他人结构化 @ 必回 → 其他群消息自主参与。

“必回”是正常运行时的处理规则；不使用兴趣、好感度、每日调用次数、固定发言冷却或文本重复来跳过本人。只对同一平台事件重投去重。队列溢出、断线或服务异常必须有本机状态，不声称已经送达。

### 3.2 模块契约

以下是任务内必须实现的明确接口，不把它们当成已存在的库函数。参数以任务 2 的类型定义为准；`scope` 始终由程序生成，不能取模型提供的作用域。

| 模块接口 | 输入与返回 / 事务要求 |
| --- | --- |
| `settings.load_settings(path, secrets_path=None)` | 校验账号为数字字符串、群为字符串集合、模型地址固定 HTTPS；返回不可变 Settings，Key 不进入 repr |
| `policy.admit(raw, owner, groups, expected_bot)` | 只读平台身份字段；返回 bool；拒绝时不读取正文、不持久化 |
| `policy.decide(message, owner, groups)` | 返回 DROP / REQUIRED / OPTIONAL |
| `store.claim(message, route)` | 唯一键 `(bot, scope, message_id)`；事务插入一次，重复返回 False |
| `store.transition(key, old, new, reason=None)` | 带旧状态条件的更新，不用无条件覆盖；并发冲突返回 False |
| `store.commit_sent(key, reply, sent_id, change, now)` | 一次事务写发送成功、助手消息、关系变化；重复回执不重复加分 |
| `store.context(scope, before_seq, limit=24)` | 只读当前作用域且序号不晚于触发消息的记录，时间顺序返回 |
| `memory.add/correct/forget/list` | 校验管理者、目标作用域和来源；纠正/遗忘同步使依赖摘要失效 |
| `affinity.apply_change(state, proposal, now)` | 纯函数；返回新状态和实际变化 |
| `deepseek.complete(messages, purpose, max_tokens)` | 返回正文、用量及请求状态；每次尝试分别计数 |
| `usage.record/summary/estimate` | 未返回用量用 NULL，不用 0；费用估计允许返回 unknown |
| `scheduler.submit(message, route)` | 已授权并完成 claim 后提交；返回 queued / overloaded；每会话至多 10 条等待消息 |
| `service.process(message, route)` | 在会话工作器中处理；生成、校验、发送、明确回执后提交 |
| `onebot.send_text(bot, message, text)` | 只发送一个 text 段；返回平台 message_id；不接受模型指定目标 |
| `commands.handle(message, store, settings)` | 只允许本人私聊的结构化管理命令；返回文本或 None；不执行任意命令 |
| `main.MansuiPlugin` | initialize 加载服务，事件处理器只提交消息，terminate 有序停止 |

### 3.3 数据与运行常量

- 关系初始 20，范围 0–100，单次 -1/0/+1，当地自然日增加与减少分别最多 3，变化间隔 600 秒。
- 全局模型并发 2；同会话一名工作器；每会话等待队列 10；记录队列满的状态，不设置每日模型调用上限。
- 上下文最多 24 条，每条最多 2,000 字符；本次输入最多 4,000 字符，超出显式说明截断。整体消息文本最多 24,000 字符，剔除最旧历史，保留当前输入与必要系统规则。字符限制不是精确 token 估算。
- 输出日常 512 tokens，明确详细问答 1024；非流式。普通候选过期时间按每批语境配置，第一版 120 秒，只用于尚未处理的 OPTIONAL；从不用于 REQUIRED。
- 网络错误最多 3 次尝试（首次 + 2 次重试），单次超时 45 秒；服务端 Retry-After 若超过本次处理可等待范围则报告限流，不提前重试。
- 原始记录 30 天；插件日志 5 个各 10MB，其他状态日志合计不超过 50MB，总量不超过 100MB；媒体临时缓存 7 天。
- 配置示例中的本人、小号、群号均留空。单元测试使用虚构数字账号，不读取真实配置。

## 4. Task 1：固定组件与验证落盘路径

**Files:** E:\QQAgent\scripts\environment.ps1、E:\QQAgent\scripts\prepare.ps1、E:\QQAgent\scripts\preflight.py、E:\QQAgent\config\versions.lock.json、E:\QQAgent\docs\compatibility.md；组件输出严格在第 2 节列出的 app/runtime 目录。

- [ ] 1. 在 A 范围获批后，核对 E:\QQAgent 当前清单；已有文件先比较，禁止覆盖已有真实配置、数据库或登录会话。检查 E 盘空间，记录实际数值；依赖准备预计空间只是估计，不据此声称内存充足。
- [ ] 2. 创建 environment.ps1，所有变量仅在本次 PowerShell/子进程生效，不调用 setx，不重定义 HOME 或 CODEX_HOME。内容如下：

~~~powershell
$ErrorActionPreference = 'Stop'
$env:UV_CACHE_DIR = 'E:\QQAgent\runtime\uv-cache'
$env:UV_PYTHON_INSTALL_DIR = 'E:\QQAgent\runtime\python'
$env:UV_PYTHON_BIN_DIR = 'E:\QQAgent\runtime\python-bin'
$env:UV_PYTHON_INSTALL_REGISTRY = 'false'
$env:UV_PYTHON_NO_REGISTRY = 'true'
$env:UV_NO_MODIFY_PATH = 'true'
$env:UV_PROJECT_ENVIRONMENT = 'E:\QQAgent\runtime\venv'
$env:UV_TOOL_DIR = 'E:\QQAgent\runtime\tools'
$env:UV_TOOL_BIN_DIR = 'E:\QQAgent\runtime\tools\bin'
$env:PIP_CACHE_DIR = 'E:\QQAgent\runtime\pip-cache'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP = 'E:\QQAgent\runtime\tmp'
$env:TMP = 'E:\QQAgent\runtime\tmp'
$env:ASTRBOT_ROOT = 'E:\QQAgent\data\astrbot'
$env:NAPCAT_WORKDIR = 'E:\QQAgent\data\napcat'
$env:QQAGENT_ROOT = 'E:\QQAgent'
~~~

- [ ] 3. 从下列固定 URL 下载到 runtime\downloads；使用 HTTPS，禁止镜像拼接与关闭证书验证。提取前验证 ZIP 全部条目不含绝对路径、盘符或跳出目标目录的 ..；已有目标目录不直接覆盖。

~~~text
https://github.com/AstrBotDevs/AstrBot/archive/refs/tags/v4.29.3.zip
https://github.com/NapNeko/NapCatQQ/releases/download/v4.18.41/NapCat.Shell.zip
https://github.com/astral-sh/uv/releases/download/0.13.6/uv-x86_64-pc-windows-msvc.zip
~~~

对 GitHub Release 提供的 SHA-256/digest 做比对；没有上游摘要时记录下载来源和本地哈希，不把自行计算哈希说成独立来源验证。versions.lock.json 保存 URL、标签、Git 提交、获取时间、哈希、Python 完整版本与 AstrBot uv.lock 的哈希。

- [ ] 4. 安装私有解释器并按 AstrBot 自带锁文件准备依赖及其测试工具，不全局 pip 安装，不自动升级锁文件。以下命令在源码已安全解包后运行：

~~~powershell
. 'E:\QQAgent\scripts\environment.ps1'
& 'E:\QQAgent\runtime\tools\uv\uv.exe' python install 3.12.16
if ($LASTEXITCODE -ne 0) { throw 'private_python_install_failed' }
& 'E:\QQAgent\runtime\tools\uv\uv.exe' sync --frozen --project 'E:\QQAgent\app\AstrBot' --python 3.12.16 --group dev
if ($LASTEXITCODE -ne 0) { throw 'locked_dependency_install_failed' }
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B --version
& 'E:\QQAgent\runtime\tools\uv\uv.exe' pip check --python 'E:\QQAgent\runtime\venv\Scripts\python.exe'
~~~

预期解释器为 3.12.16，依赖检查退出 0。若 Windows wheel 不兼容，记录具体包及版本，先在既有范围内解决；需要改版本、加入编译工具或修改系统时先更新实施范围，不能暗自安装 Build Tools。

- [ ] 5. 核对上游安装中的相关入口仍与本计划一致。读取 NapCat Windows 加载器的实际参数、QQ 所在目录与数据目录能力，检查 WebUI 资源版本、进程创建行为及是否涉及系统写入。此步不启动真实 QQ，不导出用户账号资料。把已确认项与尚未运行验证项分开写入 compatibility.md。
- [ ] 6. 配置离线测试进程使用 E:\QQAgent\runtime\test-state\astrbot 作为 ASTRBOT_ROOT，模拟 NapCat 也使用 test-state 子目录。不能为了导入框架而初始化生产 data 目录。
- [ ] 7. 在后续获准接入真实 QQ 前，必须验证专用会话数据实际落盘位置。QQ 未能按已批准路径运行时，暂停真实登录；可继续完成不依赖 QQ 的离线开发，不能宣称接入已完成。

**完成证据：** 固定版本和哈希记录、依赖检查、所有可控运行路径的实际解析值；QQ 兼容与数据路径未验证时如实标记“尚未实测”。

## 5. Task 2：事件类型、配置与唯一回复规则

**Files:** E:\QQAgent\plugins\mansui_companion\domain.py、settings.py、policy.py；E:\QQAgent\config\mansui.example.json；E:\QQAgent\tests\test_policy.py、conftest.py。本节短文件名均指上述同目录的明确文件。

- [ ] 1. 定义不可变 Message、Route 和 Settings，统一数字账号为字符串；保留 message_id，不以正文哈希代替平台 ID。Message 至少包含 bot、sender、group、message_id、text、mentions、received_at、unsupported；scope 是 (bot, private/group, 会话 ID) 的 JSON 序列化值。
- [ ] 2. 先写路由测试，再实现下列核心算法。admit 在读取正文之前执行，通知、请求和身份不全的事件不进入聊天通路：

~~~python
from dataclasses import dataclass
from enum import Enum

class Route(str, Enum):
    DROP = "drop"
    REQUIRED = "required"
    OPTIONAL = "optional"

@dataclass(frozen=True)
class Message:
    bot: str
    sender: str
    group: str | None
    message_id: str
    text: str
    mentions: frozenset[str]
    received_at: float
    unsupported: bool = False

def admit(raw: dict, owner: str, groups: frozenset[str],
          expected_bot: str) -> bool:
    if not owner.isdigit() or not expected_bot.isdigit():
        return False
    if raw.get("post_type") != "message":
        return False
    bot = str(raw.get("self_id", ""))
    sender = str(raw.get("user_id", ""))
    if bot != expected_bot or not sender.isdigit() or sender == bot:
        return False
    kind = raw.get("message_type")
    if kind == "private":
        return sender == owner
    if kind == "group":
        return str(raw.get("group_id", "")) in groups
    return False

def decide(message: Message, owner: str,
           groups: frozenset[str]) -> Route:
    if message.sender == message.bot:
        return Route.DROP
    if message.group is None:
        return Route.REQUIRED if message.sender == owner else Route.DROP
    if message.group not in groups:
        return Route.DROP
    if message.sender == owner or message.bot in message.mentions:
        return Route.REQUIRED
    if not message.text.strip() or message.unsupported:
        return Route.DROP
    return Route.OPTIONAL
~~~

- [ ] 3. 配置示例必须是合法 JSON，包含下列完整初始结构；真实 Key 不写进示例。模型地址不接受群消息修改；本机配置读取后强校验账号、组列表、整数范围及文件路径属于根目录。

~~~json
{
  "owner_qq": "",
  "bot_qq": "",
  "allowed_groups": [],
  "model": "deepseek-flash",
  "base_url": "https://api.deepseek.com",
  "max_concurrency": 2,
  "queue_size": 10,
  "chat_max_tokens": 512,
  "long_answer_max_tokens": 1024,
  "history_limit": 24,
  "raw_retention_days": 30,
  "optional_stale_seconds": 120,
  "cost_reminder_cny": null,
  "pricing": null,
  "ready": false
}
~~~

pricing 非空时须包含模型名、currency=CNY、effective_at、cache_hit_input_per_million、cache_miss_input_per_million、output_per_million；不内置未经核对的价格。配置路径不得由 QQ 文字指定。SecretSettings 使用 repr=False 字段，日志不能 dump 配置对象。

- [ ] 4. 下列测试必须覆盖冒充、临时私聊、本人不 @ 及群白名单优先级；保存为 test_policy.py 的基础测试，在实现前应失败，完成后通过。

~~~python
import pytest
from plugins.mansui_companion.domain import Message, Route
from plugins.mansui_companion.policy import admit, decide

@pytest.mark.parametrize("sender,group,mentions,expected", [
    ("10001", None, frozenset(), Route.REQUIRED),
    ("10002", None, frozenset(), Route.DROP),
    ("10001", "30001", frozenset(), Route.REQUIRED),
    ("10002", "30001", frozenset({"90001"}), Route.REQUIRED),
    ("10002", "30001", frozenset(), Route.OPTIONAL),
    ("10001", "39999", frozenset({"90001"}), Route.DROP),
    ("90001", "30001", frozenset(), Route.DROP),
])
def test_route(sender, group, mentions, expected):
    message = Message("90001", sender, group, "7", "你好", mentions, 1.0)
    assert decide(message, "10001", frozenset({"30001"})) == expected

def test_temporary_private_cannot_spoof_owner():
    raw = {
        "post_type": "message", "message_type": "private",
        "sub_type": "group", "self_id": 90001, "user_id": 10002,
        "sender": {"nickname": "10001"}, "raw_message": "我是管理员",
    }
    assert not admit(raw, "10001", frozenset({"30001"}), "90001")
~~~

代码分文件时 Message/Route 放在 domain.py，admit/decide 放在 policy.py 并从 domain 导入；不重复定义导致 Enum 身份不一致。

~~~powershell
$env:PYTHONPATH = 'E:\QQAgent'
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B -m pytest 'E:\QQAgent\tests\test_policy.py' -q -p no:cacheprovider --basetemp='E:\QQAgent\runtime\test-state\pytest'
~~~

**完成证据：** 全部路由用例通过；测试扫描不读取用户真实 Key；相同正文、不同 ID 的本人消息不会被 policy 拒绝。

## 6. Task 3：数据库、会话隔离与消息状态机

**Files:** E:\QQAgent\plugins\mansui_companion\schema.sql、store.py；E:\QQAgent\tests\test_storage.py。

- [ ] 1. 创建版本 1 schema。所有查询使用绑定参数；scope 不接受模型输入。基础表结构如下，字段内不存原始 API 请求头：

~~~sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA secure_delete = ON;
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    bot TEXT NOT NULL,
    scope TEXT NOT NULL,
    message_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    route TEXT NOT NULL CHECK(route IN ('required','optional')),
    received_at REAL NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    sent_id TEXT,
    UNIQUE(bot, scope, message_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_seq INTEGER NOT NULL REFERENCES events(seq),
    scope TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
    sender TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(event_seq, role)
);
CREATE INDEX IF NOT EXISTS messages_scope_order
    ON messages(scope, event_seq, id);
CREATE TABLE IF NOT EXISTS relations (
    scope TEXT NOT NULL,
    subject TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 20 CHECK(score BETWEEN 0 AND 100),
    local_day TEXT NOT NULL,
    gained INTEGER NOT NULL DEFAULT 0,
    lost INTEGER NOT NULL DEFAULT 0,
    last_change REAL,
    reason TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(scope, subject)
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    subject TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('explicit','summary')),
    content TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    source_ids TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_scope
    ON memories(scope, active, subject);
CREATE TABLE IF NOT EXISTS usage_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_seq INTEGER,
    requested_at REAL NOT NULL,
    purpose TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_hit_tokens INTEGER,
    cache_miss_tokens INTEGER,
    model TEXT NOT NULL,
    estimated_cny TEXT,
    pricing_version TEXT
);
CREATE INDEX IF NOT EXISTS usage_time ON usage_attempts(requested_at);
CREATE TABLE IF NOT EXISTS local_status (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
INSERT OR IGNORE INTO schema_version(version) VALUES (1);
~~~

- [ ] 2. store.claim 使用一个事务插入 events 和授权用户的 messages；同一事件 UNIQUE 冲突返回 False。不能先调用模型再做去重。拒绝私聊连 events/relations 都不创建，只允许无账号、无内容的总拒绝计数存在内存。
- [ ] 3. 实现状态转换矩阵，更新 SQL 必须带旧状态。合法状态：
  received → queued → processing → sending → sent；
  optional 可以从 queued/processing → silent 或 stale；
  required 在超载/断线时 → failed 或 awaiting_retry（本机可见）；
  sending 超时或进程中断 → unknown_delivery。
  不能从 unknown_delivery 直接重发；先借助平台回执核对，无法核对则等待用户决定。
- [ ] 4. 回复发送成功后，在同一 SQLite 事务内登记 sent_id、助手文本和实际好感度变化；发生提交失败不再次向 QQ 发送。重复平台回执不得再次加分。
- [ ] 5. 所有消息和记忆查询都带 scope；群成员关系额外带 subject。对 bot/群号/本人号分别变化的测试库证明隔离。context 的事件上界是当前 seq，防止队列后到消息进入前一条消息的回答。
- [ ] 6. 首次建库、已有版本校验、事务失败均有明确错误；不捕获所有错误后创建空库。迁移只在离线备份策略得到明确批准后执行，第一版不需要迁移旧业务数据。
- [ ] 7. 重启将 processing/queued 的 REQUIRED 记为待恢复状态，展示数量，不把它们当 OPTIONAL 自动过期；sending 统一 unknown_delivery。过期 OPTIONAL 不补发。当前进程中短暂断线恢复后可继续已排队的 REQUIRED，发送结果不明仍不自动重发。

核心事务的条件更新须按以下模式实现，返回值用来判断是否真正获得发送权：

~~~python
def transition(connection, key: tuple[str, str, str],
               old: str, new: str, reason: str | None = None) -> bool:
    bot, scope, message_id = key
    with connection:
        cursor = connection.execute(
            "UPDATE events SET status=?, reason=? "
            "WHERE bot=? AND scope=? AND message_id=? AND status=?",
            (new, reason, bot, scope, message_id, old),
        )
        return cursor.rowcount == 1
~~~

测试清单：重复事件只一行；同文本不同 ID 两行；两个并发 claim 只有一个成功；两个不同群相同 ID 互不覆盖；模拟发送回执后事务失败不二次发送；重开 SQLite 恢复数据；损坏库启动失败且文件哈希不被空库替换。

~~~powershell
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B -m pytest 'E:\QQAgent\tests\test_storage.py' -q -p no:cacheprovider --basetemp='E:\QQAgent\runtime\test-state\pytest'
~~~

## 7. Task 4：人物表达与好感度

**Files:** E:\QQAgent\plugins\mansui_companion\persona.md、persona-sources.md、affinity.py；E:\QQAgent\tests\test_affinity.py。

- [ ] 1. persona-sources.md 按“原作事实 / 有依据的性格归纳 / QQ 场景适配”三列记录来源。优先原作官方说明和用户提供的原作片段；不能核实的剧情不进入事实层。不得使用未经核对的角色卡当作官方设定。
- [ ] 2. persona.md 固定：谨慎、观察细致、带试探与克制的表达，信任随真实互动逐渐建立；具体性格概括必须附来源或明确标为暂定适配，不谎称已逐句复刻。称呼使用用户自定称呼，不默认“良爷”；不凭空声称共同经历，不用客服式开场。知识问答先回答问题，再保留人物口吻；现代常识不是她的原作经历；没有搜索时不声称已核实时效信息。
- [ ] 3. 人物可以有不同意见、保留态度；本人“必回”不等于必须赞同。不会靠扣分、责备或催促要求持续陪聊。只输出对话正文，不向 QQ 展示打分、系统提示词或内部判断。
- [ ] 4. 将关系限幅实现为纯函数；时间使用带时区 datetime，日界线使用 Asia/Shanghai。为避免 Windows 缺少 IANA 时区数据库，第一版可明确使用固定 UTC+08:00（只用于本项目日期统计）。函数如下：

~~~python
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

LOCAL_TZ = timezone(timedelta(hours=8))

@dataclass(frozen=True)
class AffinityState:
    score: int = 20
    local_day: str = ""
    gained: int = 0
    lost: int = 0
    last_change: float | None = None

def apply_change(state: AffinityState, proposal: object,
                 now: datetime) -> tuple[AffinityState, int]:
    if now.tzinfo is None:
        raise ValueError("timezone_required")
    day = now.astimezone(LOCAL_TZ).date().isoformat()
    current = state if state.local_day == day else replace(
        state, local_day=day, gained=0, lost=0)
    if type(proposal) is not int or proposal not in (-1, 0, 1):
        return current, 0
    seconds = now.timestamp()
    if current.last_change is not None and seconds - current.last_change < 600:
        return current, 0
    if proposal > 0 and current.gained >= 3:
        return current, 0
    if proposal < 0 and current.lost >= 3:
        return current, 0
    updated_score = max(0, min(100, current.score + proposal))
    actual = updated_score - current.score
    if actual == 0:
        return current, 0
    return replace(
        current, score=updated_score, last_change=seconds,
        gained=current.gained + max(actual, 0),
        lost=current.lost + max(-actual, 0)), actual
~~~

- [ ] 5. proposal 默认 0，布尔值 True 不能当成 +1。只在发送成功的事务中应用函数结果。重复内容刷分、管理命令和系统错误的 proposal 强制 0。关系原因仅保存简短可理解的事实概括，不保存模型推理。
- [ ] 6. 验证初始 20、0/100 边界、600 秒前后、同日各 ±3、当地午夜重置、系统时间回退不越过间隔、群成员互相独立、一天没聊不扣分。用假时钟推进，不真等十分钟。
- [ ] 7. 人设样例至少包含：初见、熟悉后寒暄、不同意见、简单计算、无法确认的新闻、用户短时间连发、要求直接满好感、群里追问私聊内容。评审结果写入 persona-sources.md，给出自然程度、性格依据、知识准确性；不得用测试通过代替人物表现评审。

~~~powershell
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B -m pytest 'E:\QQAgent\tests\test_affinity.py' -q -p no:cacheprovider --basetemp='E:\QQAgent\runtime\test-state\pytest'
~~~

## 8. Task 5：上下文、长期记忆与本人管理命令

**Files:** E:\QQAgent\plugins\mansui_companion\memory.py、commands.py；E:\QQAgent\tests\test_memory.py。

- [ ] 1. 实现 context(scope, before_seq, limit)，按事件序号取最多 24 条当前作用域记录，再按全局字符预算从旧到新裁剪。群消息把真实发送者 ID 与正文编码为资料字段，不把昵称拼入 system 指令。消息载荷使用 JSON 编码，不能靠用户能闭合的特殊分隔符实现权限。
- [ ] 2. 长期记忆分 explicit 和 summary。明确要求记住的事实带主体、scope、来源事件 ID、更新时间；模型的猜测、玩笑、引用他人的话不自动升级为事实。摘要在上下文需要压缩且确有新授权内容时生成，不建立无消息定时模型轮询。
- [ ] 3. 摘要只选择单一 scope 的来源；写入前验证所有 source_ids 指向该 scope。摘要生成的 API 用量归 purpose=summary。把摘要作为不可信对话资料加入用户内容块，不能提升为系统权限。
- [ ] 4. 实现下列管理命令，只有本人私聊能够执行；在群聊中出现相同文本按普通聊天处理，绝不执行管理动作。命令成功/失败都直接回应，不额外调用模型。

| 命令 | 行为 |
| --- | --- |
| /满穗 帮助 | 返回本人可用命令 |
| /满穗 关系 | 显示当前本人私聊的阶段与分数 |
| /满穗 重置关系 确认 | 仅重置当前本人私聊关系到 20；回复明确作用域 |
| /满穗 记住 文本 | 保存本人明确声明的记忆并返回编号 |
| /满穗 记忆 | 按编号列出当前私聊的有效记忆 |
| /满穗 纠正 编号 新文本 | 只纠正当前私聊的该记忆，并使依赖旧值的摘要失效 |
| /满穗 遗忘 编号 | 删除该事实、关联派生摘要，并清除可再次带回该事实的来源上下文 |
| /满穗 状态 | 返回简短连接状态；不包含 Key、token 或其他人的信息 |

群作用域管理通过本机配置工具明确选择群与目标成员完成，第一版不让私聊命令默认读取其他群。修改账号白名单和密钥只通过本机配置入口；模型不能修改配置。本人私聊中的普通文本请求改配置可解释操作方法，但不把聊天内容当配置脚本。

- [ ] 5. 纠正/遗忘在同一事务内处理 memory、依赖摘要、关联的旧 messages 内容及内存缓存。若同一原始消息承载多条记忆，给用户说明此次遗忘会清除该来源消息的上下文内容，保留其他已经明确存下的独立事实。不能仅把 active 改成 0 却仍把旧原文送给模型。
- [ ] 6. 禁止已知秘密字符串和常见 Key 形态进入记忆与对话日志；本机配置中实际秘密用于精确过滤，诊断中只输出 secret_present=true/false。用户若把 Key 发给机器人，只返回本机配置入口提示，不保存正文或发送模型。
- [ ] 7. 关系重置、记忆删除等管理回复不纳入关系成长；这些直接数据操作留不含内容的操作类别与时间，不能保留被遗忘的正文副本。
- [ ] 8. 30 天清理只删除到期原始正文；不会顺带删除明确保留的长期记忆。来源消息正文被清理后保留来源 ID 和时间作为出处标记。默认不创建聊天数据库备份；删除是应用层遗忘，不声称已对硬盘历史扇区做取证级擦除。

跨作用域来源检查必须执行，而不是只写提示词：

~~~python
def validate_sources(connection, scope: str, source_ids: list[int]) -> None:
    if not source_ids or any(type(value) is not int for value in source_ids):
        raise ValueError("invalid_sources")
    for source_id in set(source_ids):
        row = connection.execute(
            "SELECT scope FROM events WHERE seq=?", (source_id,)
        ).fetchone()
        if row is None or row[0] != scope:
            raise ValueError("cross_scope_source")
~~~

测试：群 A 请求不能出现私聊/群 B 标记字符串；来源混合摘要拒绝保存；纠正后模型输入只见新值；遗忘后重启也不再检索旧值；清理原文仍保留明确记忆；非本人私聊不新增任何记录；群里的管理命令不能修改数据库。

~~~powershell
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B -m pytest 'E:\QQAgent\tests\test_memory.py' -q -p no:cacheprovider --basetemp='E:\QQAgent\runtime\test-state\pytest'
~~~

## 9. Task 6：DeepSeek 请求、结构化输出、用量与提醒

**Files:** E:\QQAgent\plugins\mansui_companion\deepseek.py、usage.py；E:\QQAgent\tests\test_deepseek.py、test_usage.py。

- [ ] 1. 使用 httpx.AsyncClient 直接调用官方 Chat Completions；不再委托 AstrBot 默认 Agent 发第二次请求，不启用工具、联网搜索或 MCP。正式请求证书验证开启，跟随重定向关闭，默认不继承进程代理以免把密钥误送到不明代理；若用户确需代理再本机明确配置。
- [ ] 2. 模型请求的 schema 与正文用以下函数生成，明确非思考模式。messages 已由 memory 构建，调用前再检查包含系统规则和当前消息，不接受模型指定目标或文件路径。

~~~python
def make_payload(model: str, messages: list[dict], max_tokens: int) -> dict:
    if max_tokens not in (512, 1024):
        raise ValueError("unsupported_output_limit")
    return {
        "model": model,
        "messages": messages,
        "stream": False,
        "thinking": {"type": "disabled"},
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
~~~

聊天系统规则要求返回 JSON 对象：
~~~json
{"participate":true,"text":"实际回复文字","affinity_delta":0,"affinity_reason":""}
~~~

对于 REQUIRED，系统提示明确 participate=true，必须回应本次消息；模型返回 false 不能跳过本人或 @。对于 OPTIONAL，可返回 participate=false，此时 text 必须为空；不向群发送“我不感兴趣”。关系建议和正文来自同一次请求，不为每条回复另加关系打分请求。summary 请求使用独立 schema，不混入聊天的发送通路。

- [ ] 3. 每次请求前写 usage_attempts 的 attempt 行；请求结束补 outcome 和服务端 usage。记录首次与重试各自次数，但失败请求没有 usage 时保留 NULL，不把尝试数直接折算费用。服务端能返回的 input/output/cache hit/cache miss 逐项解析。
- [ ] 4. 只对连接错误、超时、429、500、502、503、504 有限重试；401/402/403/400 等直接报告密钥/余额/权限/参数问题，不循环调用。503 等重试最多共 3 次，基础等待 1、2 秒并加入小抖动；有合法 Retry-After 时优先遵守其秒数或 HTTP 日期。等待过长则报告限流并结束本轮，不缩短后强行请求。失败统计记录错误类别，不记录服务端可能回显正文的完整 body。
- [ ] 5. 并发信号量在每次真正 HTTP 请求期间持有；退避等待不占用全局槽位。取消任务、超时及异常都要通过 finally 释放槽位。HTTP 客户端随插件终止关闭。
- [ ] 6. 解析并校验生成 JSON；空 choices、空 content、字符串截断、错误类型、额外工具调用、超长正文均显式处理。reasoning_content 永远忽略。正文里的 CQ 控制串不能被当作指令执行；发送层只发送 text 段。
- [ ] 7. 生成结果异常时：REQUIRED 返回一次简短说明“这次没整理好回复，再和我说一遍好吗？”并在本机标记 model_output_invalid；不输出异常堆栈，不伪装正常回答。OPTIONAL 保持安静并记录本机异常。只有模型格式问题可有一次受全局 3 次上限约束的修复尝试，不能形成嵌套无限重试；余额/鉴权失败不尝试修复。
- [ ] 8. 解析器的最小完整实现如下；是否对必回结果使用一次修复由 service 的已用尝试次数决定：

~~~python
import json
from dataclasses import dataclass

@dataclass(frozen=True)
class Reply:
    participate: bool
    text: str
    affinity_delta: int
    affinity_reason: str
    valid: bool

def parse_reply(content: str, required: bool) -> Reply:
    try:
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("object_required")
        participate = value.get("participate")
        text = value.get("text")
        if type(participate) is not bool or not isinstance(text, str):
            raise ValueError("bad_reply_types")
        text = text.strip()
        if required and (not participate or not text):
            raise ValueError("required_reply_missing")
        if participate and not text:
            raise ValueError("empty_reply")
        if len(text) > 4000:
            raise ValueError("reply_too_long")
        delta = value.get("affinity_delta", 0)
        if type(delta) is not int or delta not in (-1, 0, 1):
            delta = 0
        reason = value.get("affinity_reason", "")
        if not isinstance(reason, str):
            reason = ""
        return Reply(participate, text if participate else "", delta,
                     reason[:100], True)
    except (json.JSONDecodeError, ValueError, TypeError):
        return Reply(required, "这次没整理好回复，再和我说一遍好吗？" if required else "",
                     0, "", False)
~~~

- [ ] 9. 用 Decimal 计算费用。只对可核实用量和匹配模型、币种、日期的价格快照估算；input_total 与 hit/miss 不吻合时标记不完整。汇总同时显示“可估算部分”和“未知用量请求数”，不能把不完整估计当总账单。先由配置层校验 pricing 的所有必需键与 Decimal 字符串；估价遇到缺键、非数值或非有限值时返回 unknown，不能使聊天任务抛异常终止。阈值到达只改变本机状态，服务处理函数不得据此拒绝消息。

~~~python
from decimal import Decimal

def estimate_cny(hit: int | None, miss: int | None, output: int | None,
                 prices: dict | None) -> Decimal | None:
    if prices is None or any(value is None for value in (hit, miss, output)):
        return None
    values = (hit, miss, output)
    if any(type(value) is not int or value < 0 for value in values):
        return None
    try:
        rates = [
            Decimal(str(prices["cache_hit_input_per_million"])),
            Decimal(str(prices["cache_miss_input_per_million"])),
            Decimal(str(prices["output_per_million"])),
        ]
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None
    if any(not rate.is_finite() or rate < 0 for rate in rates):
        return None
    return sum((Decimal(value) * rate for value, rate in zip(values, rates)),
               Decimal(0)) / Decimal(1_000_000)
~~~

- [ ] 10. 费用提醒在本机状态页/终端显示，不向 QQ 群主动推送。同一阈值状态不刷屏；用户修改阈值或新的自然日重新计算。没有价格或阈值时仍显示调用次数和已知 token。
- [ ] 11. 使用 httpx.MockTransport 测试请求，不访问真实 DeepSeek。覆盖非思考参数、Retry-After 秒数/日期、401 一次终止、429 后成功、连续 503 最多 3 次、空 JSON、required=false 矫正、未知 usage、缓存计价与超过 200 次仍继续服务。

~~~python
import json
import httpx

async def fake_response(request):
    payload = json.loads(request.content)
    assert request.url.host == "api.deepseek.com"
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["stream"] is False
    assert "tools" not in payload
    return httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"participate":true,"text":"我在听。","affinity_delta":0}',
            "reasoning_content": "不应进入 QQ 或数据库的测试标记"
        }}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20,
                  "prompt_cache_hit_tokens": 60, "prompt_cache_miss_tokens": 40},
    })
~~~

~~~powershell
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B -m pytest 'E:\QQAgent\tests\test_deepseek.py' 'E:\QQAgent\tests\test_usage.py' -q -p no:cacheprovider --basetemp='E:\QQAgent\runtime\test-state\pytest'
~~~

## 10. Task 7：会话队列与自然参与

**Files:** E:\QQAgent\plugins\mansui_companion\scheduler.py、service.py；E:\QQAgent\tests\test_scheduler.py、test_service.py。

- [ ] 1. 每个 scope 一个队列和至多一个工作器；等待容量 10，不包括正在处理的 1 条。全局模型并发 2。工作器处理完队列后移除空闲对象，避免小群长期运行产生无界 task/lock 字典。
- [ ] 2. 同一会话按到达顺序执行。必回消息到来时，可移除尚未执行的 OPTIONAL 候选以腾出队列位置；不得跨过先到的 REQUIRED。全局有多个会话竞争时优先有必回需求的会话。若 10 条全是 REQUIRED，保持有限队列，把新事件状态记为 overloaded 并在本机显示未应答数量，不静默假装已回复。
- [ ] 3. 本人每条新事件保留独立应答，不批量合并。本人发同一句两次，产生两次处理；重复投递同一 ID，只处理一次。普通候选允许合并同一群短时间连续消息；事件标记 merged_into，不能生成无限批次链。
- [ ] 4. 合并窗口依据该群近几次消息到达间隔动态取较短值，并有 2 秒最大等待保证用户不会一直等；这只是普通候选的收集等待，不是每次发言后的冷却。不对 REQUIRED 使用此等待。
- [ ] 5. OPTIONAL 本地轻量检查只排除空消息、自身、平台重复、单纯协议占位和正在重复的无内容片段，不使用有限关键词白名单排除新话题。已有对话引用/回复、当前群共同话题、上下文中的后续问题都要送入当轮参与判断。语境判断与生成正文同一次模型调用，以 participate 控制是否发送。
- [ ] 6. 把角色兴趣、已有交流、群内关系、话题进展、是否有新观点、是否打断别人写入当前上下文。允许连续多轮参与、提出看法和不同意见；不使用每小时配额、固定随机概率、每日 API 上限。没有新消息时不调用模型“自我思考”。
- [ ] 7. 处理流程严格执行下列状态顺序。service 的分支必须在测试里可观察，不把“模型建议不说话”与“服务错误”混为一个 silent 状态：

~~~text
已授权并 claim
  -> REQUIRED 或 OPTIONAL 入队
  -> 读取当前 scope 的上下文/记忆/该发送者关系
  -> 本人私聊管理命令：直接生成管理回复
  -> REQUIRED 且无可读文字：生成不支持内容的简短说明
  -> 否则生成 JSON 结果
  -> OPTIONAL 且 participate=false：记 silent，零次 QQ 发送
  -> REQUIRED 且格式错误：一次解释性回复，实际关系变化 0
  -> 从 processing 原子转换到 sending
  -> 纯文本发送至原消息所在会话
  -> 明确 message_id 回执：一次事务 commit_sent
  -> 超时且送达不明：unknown_delivery；禁止自动重发
~~~

- [ ] 8. 请求错误、取消、数据库失败都释放队列 task_done 与全局槽位；一个会话异常不终止其他会话。模型连接错误不触发群内连续错误公告，REQUIRED 可发送一次简短故障说明，OPTIONAL 仅本机显示。
- [ ] 9. REQUIRED 收到纯图片、语音或空 @ 时直接说明第一版无法识别/请补文字；不中断“每条有回应”。未知消息类型不下载附件，不自动 OCR、语音识别或调用额外模型。
- [ ] 10. 写合成测试：连续 5 条本人消息分别收到回复；相同文本不同 ID 仍分别回复；单事件重复 3 次只一条；低兴趣/低关系本人依然回应；其他人连续多轮相关话题能连续参与；无兴趣普通消息零发送；201 次完成后第 202 次仍回复；队列饱和事件本机可见；抛异常后下个会话正常；工作器空闲后不增长。

可用的并发探针为：

~~~python
import asyncio

class ProbeModel:
    def __init__(self):
        self.active = 0
        self.maximum = 0
        self.calls = 0

    async def complete(self, messages, purpose, max_tokens):
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        self.calls += 1
        try:
            await asyncio.sleep(0)
            return {
                "content": '{"participate":true,"text":"我听见了。","affinity_delta":0}',
                "usage": None,
            }
        finally:
            self.active -= 1
~~~

通过实际 scheduler + service 调用探针，在多个会话同时提交时断言 maximum <= 2、每个 REQUIRED 有独立回执、队列清空后 active=0。禁止只直接测试 Semaphore 对象而绕过真正消息通路。

~~~powershell
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B -m pytest 'E:\QQAgent\tests\test_scheduler.py' 'E:\QQAgent\tests\test_service.py' -q -p no:cacheprovider --basetemp='E:\QQAgent\runtime\test-state\pytest'
~~~

## 11. Task 8：AstrBot / OneBot 接入与入口隐私保护

**Files:** E:\QQAgent\scripts\ingress_guard.py、boot_astrbot.py；E:\QQAgent\plugins\mansui_companion\onebot.py、main.py、metadata.yaml、__init__.py；E:\QQAgent\tests\test_astrbot.py。

- [ ] 1. boot_astrbot 在任何 AstrBot core 导入前设置专用根目录和临时目录，并读取严格校验过的本机配置。A 阶段所有导入实验只用 test-state 的假配置。安装私有插件时把源文件复制到 data\astrbot\data\plugins\mansui_companion，校验源与副本 SHA-256 一致；复制不包括测试、Key 或数据库。
- [ ] 2. 在框架启动处理平台事件前，包装固定版本 AiocqhttpAdapter.convert_message。先用 policy.admit 检查真实平台身份，再调用转换；插件尚未就绪、配置缺失或小号 ID 不匹配时拒绝处理。插件初始化失败/停止时撤销 ready 状态，不能让默认 Agent 接替回复。
- [ ] 3. 下列入口包装为权限保护的核心实现，放在 ingress_guard.py；is_ready 是由本项目维护的内存布尔健康函数，settings 已经校验且不可由模型写入。安装时必须确认当前适配器版本和方法签名，断言失败就停止启动。

~~~python
import inspect
from plugins.mansui_companion.policy import admit

def install_guard(adapter_type, settings, is_ready):
    original = adapter_type.convert_message
    if getattr(original, "_qqagent_guard", False):
        raise RuntimeError("guard_already_installed")
    signature = inspect.signature(original)
    if list(signature.parameters) != ["self", "event"]:
        raise RuntimeError("unsupported_adapter_signature")

    async def guarded(self, event):
        if not is_ready():
            return None
        if not admit(event, settings.owner_qq,
                     frozenset(settings.allowed_groups), settings.bot_qq):
            return None
        return await original(self, event)

    guarded._qqagent_guard = True
    adapter_type.convert_message = guarded
    return original
~~~

此包装解决“他人私聊在插件之前被转换/记录”的入口问题；还须完成下一步的日志、内置回复和解析限制，不把包装存在当成全部验证完成。

- [ ] 4. 使用上游配置关闭默认 LLM 回复、内置聊天命令、消息追踪、框架文件日志和匿名统计；provider 留空。AstrBot 配置值至少为 provider_settings.enable=false、trace_enable=false、log_file_enable=false、log_level=WARNING、disable_builtin_commands=true、disable_metrics=true。实际键按固定版本核对，配置生成失败则停止启动。[配置源码](https://raw.githubusercontent.com/AstrBotDevs/AstrBot/v4.29.3/astrbot/core/config/default.py)。
- [ ] 5. onebot 归一化只读取当前事件的 text 与明确指向小号的 at 段。不要把昵称、正文中的“@满穗”、转发中别人的 at 或 at=all 当作点名；群临时私聊按 message_type=private 判断。quote/forward/image/file 不自动展开、不下载、不调用 get_msg 跨会话取引用；在受控转换包装中关闭 get_reply 并剔除不需要解析的内容段，保留 unsupported 标记给自己的处理器。
- [ ] 6. 只为专用平台实例注册最高优先级 ALL 消息监听；命中专用实例后同步 stop_event()，再提交异步队列；不使用 yield 把结果交回框架默认回复链。非专用实例不接管。后台工作器直接通过已核对的 OneBot API 发送纯文本并读取 message_id 回执。[事件处理文档](https://docs.astrbot.app/dev/star/guides/listen-message-event.html)。
- [ ] 7. main.py 的 initialize 创建唯一 Service 和 Scheduler，terminate 取消可丢弃的普通候选、等待正在写入的事务，并关闭 HTTP 客户端与数据库。服务健康状态应覆盖事件接收通路；插件被禁用或热重载后健康状态立即变为未就绪。
- [ ] 8. 发送函数只接受来自已授权原消息的 target；不允许模型选择群号、QQ 或调用任意 action。按下列格式发送并验证返回值；发送超时应交给 service 标记 unknown_delivery，函数内不自动重试：

~~~python
async def send_text(bot, message, text: str) -> str:
    if not text.strip():
        raise ValueError("empty_send")
    segments = [{"type": "text", "data": {"text": text}}]
    if message.group is None:
        result = await bot.call_action(
            "send_private_msg", user_id=int(message.sender),
            message=segments, auto_escape=True)
    else:
        result = await bot.call_action(
            "send_group_msg", group_id=int(message.group),
            message=segments, auto_escape=True)
    if not isinstance(result, dict) or result.get("message_id") is None:
        raise RuntimeError("missing_send_receipt")
    return str(result["message_id"])
~~~

使用被锁定的 aiocqhttp 实际对象确认 call_action 返回 data 层而非完整 envelope；若该版本返回 envelope，由 onebot 适配层验证 status/retcode 后取 data，不把未成功响应视为成功。

- [ ] 9. metadata.yaml 的 name 为 mansui_companion、display_name 为满穗、version 为 0.1.0，desc 明确本人私聊与白名单群；作者标为本地项目。不要伪造公开仓库 URL，不自动发布插件。
- [ ] 10. NapCat OneBot 客户端指向 ws://127.0.0.1:6199/ws，messagePostFormat=array，reportSelfMessage=false，debug=false，token 与 AstrBot 一致。仅启用必要客户端；HTTP 服务、额外 WebSocket 服务默认关闭。WebUI 显式 host=127.0.0.1，而非其默认全地址监听。[OneBot 文档](https://docs.astrbot.app/platform/aiocqhttp.html)、[NapCat 网络配置源码](https://raw.githubusercontent.com/NapNeko/NapCatQQ/v4.18.41/packages/napcat-onebot/config/config.ts)、[WebUI 配置](https://raw.githubusercontent.com/NapNeko/NapCatQQ/v4.18.41/packages/napcat-webui-backend/src/helper/config.ts)。
- [ ] 11. NapCat 核心 fileLog=false、consoleLog=false，关闭消息原文的文件、控制台和 WebUI 日志订阅输出。二维码通过本机 WebUI 显示；不把包含令牌的 WebUI URL 打到开发对话。故障状态依赖受控的连接/健康检查，不靠收集原始 QQ 日志。
- [ ] 12. 假适配器测试以唯一标记作为“他人私聊正文”，断言原 convert_message 调用次数=0，logger/trace/mock model/DB/send 均未见标记；本人消息正常通过。随后用固定 AstrBot 的真实事件流水线 + 假 OneBot 端进行同样测试，验证未 @ 的本人消息确实可到达插件、默认回复没有被激活。
- [ ] 13. 模拟插件初始化失败、禁用、热重载和配置缺失，断言不再有模型调用或 QQ 发送。未经认证的 WS 连接被拒绝；测试端绑定本机临时端口，并在测试结束关闭。

~~~powershell
$env:ASTRBOT_ROOT = 'E:\QQAgent\runtime\test-state\astrbot'
$env:TEMP = 'E:\QQAgent\runtime\test-state\tmp'
$env:TMP = $env:TEMP
$env:PYTHONPATH = 'E:\QQAgent;E:\QQAgent\app\AstrBot'
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B -m pytest 'E:\QQAgent\tests\test_astrbot.py' -q -p no:cacheprovider --basetemp='E:\QQAgent\runtime\test-state\pytest'
~~~

## 12. Task 9：本机配置、启停、状态与数据维护

**Files:** E:\QQAgent\scripts\configure.py、preflight.py、start.ps1、stop.ps1、status.py、maintenance.py；E:\QQAgent\启动满穗.cmd、停止满穗.cmd、配置满穗.cmd、查看状态.cmd；E:\QQAgent\tests\test_lifecycle.py；E:\QQAgent\docs\operations.md。

- [ ] 1. configure.py 使用本机交互输入：本人 QQ、允许群号、小号 ID、DeepSeek Key；SecretSettings 的字段名与 settings.load_settings 保持一致。Key 用 getpass 输入且不回显。保存前展示账号和目录，不展示 Key；本机验证后原子写入本地 JSON，已有配置只修改用户选择的字段。A 阶段测试只使用虚构账号和假密钥；真实配置文件属于 B 范围。
- [ ] 2. 令牌由 secrets.token_urlsafe(32) 在本机生成，不硬编码。Key 与令牌只落 secrets.local.json，限制当前 Windows 用户可读写并记录 ACL 检查结果；不将凭据放进进程参数、README、截图、备份或版本控制。
- [ ] 3. preflight 检查必填配置、目录可写、插件校验和、入口保护已安装、已登录小号 ID 与配置一致；检查 6185（管理）、6199（反向 WS）、6099（NapCat WebUI）端口占用。冲突时给出具体本机状态，不自动结束占用进程、不悄悄改端口、不开放防火墙。
- [ ] 4. start.ps1 使用以绝对根目录派生的 Windows 命名互斥体，检测已有实例；重复启动只显示当前状态。先启动 AstrBot 并等本机健康检查成功，再在 B 范围允许后启动 NapCat。管理页面关闭不结束服务。
- [ ] 5. 后台辅助进程使用 Start-Process -WindowStyle Hidden，或 Python CREATE_NO_WINDOW。所有进程记录 PID、创建时间、实际可执行路径、启动参数中的非秘密标识与项目根目录；支持 Windows Job Object 时用来跟踪自己启动的进程树。
- [ ] 6. 不直接调用可能终止全部 QQ 的上游脚本。启动真实 QQ 前核实最终加载命令与会话目录；已有主号窗口不作为本项目子进程，不接管或注入用户现用主号进程。需要提升权限时明确目的，不设置全局执行策略。
- [ ] 7. stop.ps1 先发送仅本机可用的有令牌停止请求，停止接收、等待有限时间完成正在进行的事务，再停止本项目进程。兜底终止前同时核对 PID、创建时间、路径与本项目标识，防止 PID 被其他应用复用。禁止 taskkill /IM QQ.exe、按进程名称批量结束或删除用户会话。
- [ ] 8. 每个 CMD 都使用自身目录定位脚本，不依赖用户当前终端目录。启动入口的完整内容为：

~~~bat
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
if errorlevel 1 pause
endlocal
~~~

停止入口将脚本名精确改为 stop.ps1；配置和状态入口调用 runtime\venv\Scripts\python.exe 及 scripts\configure.py / status.py，均带完整双引号与 -B。ExecutionPolicy Bypass 只对此进程生效，不写系统策略。

- [ ] 9. status.py 在本机显示：QQ 登录、OneBot 连接、模型配置是否齐全、最近成功请求时间、每会话队列数、未应答/送达不明数、日月请求与已知 token、费用估计是否完整及提醒。故障使用 configuration_missing / qq_offline / onebot_disconnected / auth_failed / balance_insufficient / rate_limited / queue_full / unknown_delivery 等固定类别，不展示私聊正文。
- [ ] 10. 日志只记录必要的组件、时间、状态码和计数；已知秘密替换为 [REDACTED]。日志轮转总额 <=100MB；7 天媒体缓存清理只遍历本项目明确列出的缓存目录；30 天正文清理使用参数化 SQL。所有递归删除之前解析绝对路径并拒绝越界或 reparse point，不能沿目录联接删到其他位置。
- [ ] 11. 备份使用文件白名单而非“备份整个 config/data”。只包含 mansui.example.json、persona.md、persona-sources.md、versions.lock.json；不包含 local/secrets、SQLite、QQ 会话或上游整目录。恢复配置不覆盖真实 Key，不创建聊天数据库历史副本。
- [ ] 12. 本机可选查看资源占用，采样本项目进程的 CPU、内存和队列；记录空闲/正常/活跃群三个阶段。只做状态统计，不在空闲时请求模型。A 用假进程和模拟高负载验证，B 再实测真实 QQ 与框架。
- [ ] 13. 用临时子进程验证重复启动不生成第二实例、关状态窗口不停止服务、旧 PID 指向其他程序时拒绝终止、正在写库时有序停止、端口冲突不伤及其他服务、清理路径含联接时拒绝、备份内没有模拟密钥标记。

路径检查的核心函数如下，执行删除时还须检查每个实际子条目而非仅检查最外层字符串：

~~~python
from pathlib import Path

def confined_path(root: Path, candidate: Path) -> Path:
    root_resolved = root.resolve(strict=True)
    candidate_resolved = candidate.resolve(strict=False)
    if candidate_resolved == root_resolved:
        raise ValueError("cannot_operate_on_project_root")
    if not candidate_resolved.is_relative_to(root_resolved):
        raise ValueError("outside_project_root")
    return candidate_resolved
~~~

~~~powershell
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B -m pytest 'E:\QQAgent\tests\test_lifecycle.py' -q -p no:cacheprovider --basetemp='E:\QQAgent\runtime\test-state\pytest'
~~~

## 13. Task 10：离线总验收与交付资料

**Files:** E:\QQAgent\tests\test_acceptance.py、conftest.py；E:\QQAgent\docs\acceptance.md、operations.md；E:\QQAgent\README.md。

- [ ] 1. conftest 在测试开始强制把所有数据目录设为 runtime\test-state；创建假时钟、假模型、假 OneBot 服务和内存/临时 SQLite。真实外网默认禁止，只有任务 1 下载和后续明确授权的 B 阶段才允许访问真实服务。fixture 不读取 secrets.local.json。
- [ ] 2. 让验收测试调用完整业务入口，而非只验证输出文案。对必回消息核对调用次数、发送目的地、回执、保存状态；对拒绝消息核对零发送、零模型请求、零新增数据和无日志正文。
- [ ] 3. 按第 15 节映射逐项执行。所有 201/202 次调用和失败重试均为模拟，无实际付费请求。各单项通过后只运行一次完整回归；后续仅因修改、失败或仍有疑点而重跑有关项。
- [ ] 4. 在 acceptance.md 记录实际命令、环境版本、结果、尚未验证的真实平台限制和时间，不将“计划预计通过”写成通过。遇到断言失败修复对应原因，不能删除断言或用固定回复规避人物与权限逻辑。
- [ ] 5. README 面向日常使用者，正文只介绍四个入口、电脑保持唤醒联网、私聊与群规则、费用提醒、数据目录。operations.md 记录 DeepSeek 官方 Key 申请入口 https://platform.deepseek.com/、本机输入步骤、扫码核对小号、测试群设置、故障状态和数据遗忘；不把开发接口细节塞进普通聊天。
- [ ] 6. 在文件清单中核对本轮实际产物；没有未批准的目录、真实凭据、依赖全局安装或系统配置变更。保留全部上游许可证；不创建 Git 提交或上传任何文件。
- [ ] 7. 离线完成后给用户展示可运行入口及验收结果，再提出 B 范围的具体账号与测试消息范围确认。此时需要 Key，但应让用户通过本机配置入口填写，不要求发到聊天里。

完整离线回归命令：

~~~powershell
. 'E:\QQAgent\scripts\environment.ps1'
$env:QQAGENT_CONFIG = 'E:\QQAgent\runtime\test-state\config.json'
$env:QQAGENT_DATA = 'E:\QQAgent\runtime\test-state\data'
$env:ASTRBOT_ROOT = 'E:\QQAgent\runtime\test-state\astrbot'
$env:NAPCAT_WORKDIR = 'E:\QQAgent\runtime\test-state\napcat'
$env:TEMP = 'E:\QQAgent\runtime\test-state\tmp'
$env:TMP = $env:TEMP
$env:PYTHONPATH = 'E:\QQAgent;E:\QQAgent\app\AstrBot'
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B -m pytest 'E:\QQAgent\tests' -q -p no:cacheprovider --basetemp='E:\QQAgent\runtime\test-state\pytest' --junitxml='E:\QQAgent\runtime\test-state\acceptance.xml'
if ($LASTEXITCODE -ne 0) { throw 'offline_acceptance_failed' }
~~~

预期所有已实现离线场景通过、退出 0。真实 QQ 接入、真实模型角色质量和实际内存占用不能由这条命令证明。

## 14. Task 11：B 范围批准后的本机联调

**Files:** 第 2.2 节的真实配置与运行数据；E:\QQAgent\docs\compatibility.md、acceptance.md、operations.md。本任务在 A 范围完成后才能进入，并需 B 范围和实际测试目标授权。

- [ ] 1. 在本机配置入口填写唯一主人 QQ、测试群、小号与 Key。先检查格式，不联网验证。没有群号时保持群功能关闭，不把“空名单”解释为所有群。
- [ ] 2. 仅对官方 DeepSeek 发起 1 次简短鉴权/格式测试；确认模型名、非思考参数、usage 与 JSON 返回。如果失败，根据错误类别修复，不自动进行大量重复付费测试。
- [ ] 3. 按已核实的专用 QQ 启动方法启动，用户扫码小号；本机显示实际登录 QQ 号供核对，主号或不匹配立即关闭本项目回复通路。验证数据写入目标目录，未确认外部路径不得继续。
- [ ] 4. 完成单一测试群与本人私聊的少量双向消息：本人私聊、本人群内不 @、他人 @、其他话题可参与/可沉默、他人私聊不回应。需要测试者发消息时由用户安排，助手不擅自联系其他人。
- [ ] 5. 观察一次断线重连、一次停止/重启、一次重复启动；不主动破坏用户网络或结束无关进程。核对关系与记忆保留，没有集中补发过时普通群话题。
- [ ] 6. 用户评审人设样例；根据具体反馈在既定 persona 文件和测试范围内微调，保持原作依据。未找到依据时写成场景适配，不能编造原作台词。
- [ ] 7. 记录真实运行时的资源样本、峰值、样本时长与队列深度；没有样本则明确未测。不因当前可用内存数值就保证永不增长。
- [ ] 8. 本人确认小群试运行符合预期后，才开启其余明确指定群。交付四个入口和运行说明；不启用服务器或开机自启。

## 15. 设计验收映射

| 设计编号 | 主要任务 | 必须取得的证据 |
| --- | --- | --- |
| A01 本人私聊 | 2、5、7、8、11 | 每条新消息独立回应；含低关系、不支持内容说明；本会话上下文延续 |
| A02 他人私聊 | 2、8、10、11 | 入口转换前拒绝；无发送、无模型请求、无消息/关系/记忆记录、无日志正文；包含群临时私聊与昵称冒充 |
| A03 非白名单群 | 2、8、10 | 即使本人或 @ 也不启用 |
| A04 白名单群 @ | 2、7、8、11 | 他人结构化 @ 正常回复一次；文本假 @ 不算 |
| A05 普通群参与 | 6、7、11 | 新话题可参与、连续交流不中断、无兴趣可沉默，无固定小时配额 |
| A06 自身/重复/转发 | 2、3、7、8 | 不自问自答，事件重投只处理一次，转发/引用不冒充当前说话人或触发隐藏 @ |
| A07 私聊隔离 | 3、5、10 | 群请求和回复里没有私聊独有标记字符串 |
| A08 跨群隔离 | 3、5、10 | 群 A 无法读取群 B 上下文、摘要和成员关系 |
| A09 好感度 | 3、4、10 | 0–100、单次 ±1、当地日 ±3、600 秒间隔、作用域独立；发送成功才提交 |
| A10 刷分/注入 | 2、4、5、6、8 | 要求满分、伪造身份、索要秘密不能改变程序权限/数据或泄露凭据 |
| A11 纠正/遗忘 | 5、10 | 原始来源和派生摘要失效，重启后也不再被模型取回 |
| A12 重启 | 3、7、9、11 | 关系、记忆、去重保存；unknown_delivery 不自动重发；旧 OPTIONAL 不补发 |
| A13 异常/断线 | 6、7、8、9、11 | 有限退避、无异常刷群、本机故障类别明确、会话之间不互相拖死 |
| A14 人物/问答 | 4、6、11 | 人设来源和样例审阅；回答有用，不伪造原作经历或联网查询 |
| A15 路径/日志 | 1、8、9、10、11 | 可控文件位于 E:\QQAgent；日志/备份不含密钥；QQ 原生落盘路径实测 |
| A16 启停 | 9、11 | 启动互斥、后台独立于页面、只停止本项目且验证 PID 创建时间 |
| A17 负载 | 7、9、10、11 | 有界队列与工作器，日志总量受控；模拟加真实采样，无持续未解释增长 |
| A18 用量/提醒 | 6、7、10 | 201 次后仍服务，重试/失败正确计数，未知不当零，提醒仅本机且不停止 |
| A19 本人群消息 | 2、3、7、8、10、11 | 未 @、低兴趣、低关系、连续重复文字均逐条回应；本人 @ 不双回，群内只用群上下文 |

## 16. 本计划自审与执行交接

计划审查不等于应用测试。本轮可以验证的内容只有：设计与计划覆盖、文件范围、引用的上游接口、代码块语法、配置示例语法和验收映射完整性。

执行优先顺序：A 授权 → 任务 1 环境和兼容检查 → 任务 2–7 核心及离线测试 → 任务 8 框架集成 → 任务 9 启停维护 → 任务 10 离线总验收 → B 授权 → 任务 11 真实联调。

默认在当前对话逐项执行，不开启子代理；如果用户另行指定并行或子代理再调整组织方式。执行前加载个人 cold storage 中的 executing-plans 工作流；文件写入门禁仍以用户 AGENTS.md 为准。不为采用工作流而额外创建 Git 仓库、提交或安装 Skill。

需要用户的下一步决定只有：是否批准第 2.1 节 A 范围的源码、依赖和离线测试写入。该批准不包含 B 范围的真实 QQ 登录或消息发送。完成 A 后再提供实际可运行结果、账号配置入口和清楚的 B 测试清单。


### 本轮文档检查记录

- 已对照已批准设计检查 11 个实施任务与 A01–A19，验收映射无缺号。
- 已解析 13 个 Python 代码块、11 个 PowerShell 代码块和 2 个 JSON 示例，语法检查通过。
- 已在内存 SQLite 中验证 schema，并对文档内路由、好感度限幅、输出解析和费用估算函数做基础断言检查。
- 上述检查只验证计划片段，不代表插件、上游组件或真实 QQ 已运行通过。
- 已核对原设计文件 SHA-256 未变化；项目当前只有设计与实施计划两份文档。
- A 范围实施写入尚待用户批准；B 范围真实联调尚未授权或执行。
## 17. 执行记录

- 用户已明确批准 A 范围执行；B 范围尚未开始。
- Ruling: 使用同名插件版 executing-plans，个人旧路径不存在；保持用户要求的当前对话执行，不新建 Git、工作树、Skill 或子代理。
- Ruling: 进度写入本计划，测试日志与临时数据仅放 runtime/test-state，遵守已批准文件范围，不创建工作流默认的 .superpowers 工作目录。
- 接口检查：任务 2 的 Message/Route 被任务 3/7/8 共用；私聊授权检查必须早于正文/日志；任务 6 返回 content/usage 由任务 7 消费；任务 3 发送成功事务使用任务 4 的限幅状态；任务 5 删除必须清除任务 3 上下文及摘要来源。
- Task 1: 三个固定版本的 GitHub Release 已核实；归档下载进行中。E 盘可用约 458 GiB。
- Task 2/4 RED: 基础权限、配置和好感度测试已先写入，模块缺失引发预期失败；下一步实现这些能力。
### 执行进度：离线核心与接入已形成

- [x] 固定归档下载完成；Python 3.12.16 和 168 个依赖安装在 E:\QQAgent，uv pip check 通过。
- 修订：官方 AstrBot v4.29.3 源码归档没有 uv.lock，实际按 pyproject.toml 在组件目录解析生成锁，再以 --frozen 安装；来源不冒称为上游锁文件。
- [x] 权限、数据库、去重、好感度、记忆、模型有限重试、用量、排队、纯文本发送实现并经过分项测试。
- [x] 首轮全量回归 47 passed、13 subtests passed；其后继续进行审查与新增边界测试，最终结果以 docs/acceptance.md 为准。
- [x] 真实 AstrBot 核心 + 插件 + OneBot 模拟 WebSocket 完成收发回执验证；非本人私聊在转换前拒绝，错误 WS 令牌拒绝。
- 审查修正：关闭上游默认接受事件的 HTTP 入口；只用带令牌的反向 WS。增加上下文来源依赖，遗忘可清除后续派生内容。
- [x] 本机配置、认证状态端口、重复启动互斥、后台停止、PID 核验与 Windows Job 子进程停止通过模拟验证。
- 代码审查采用当前会话自审与回归，不启动子代理；延续本计划已批准的执行方式。尚无提交、发布、真实 QQ 登录或付费 API 调用。
### A 范围交付结论

- [x] Tasks 1–10 的本地制作部分完成；实际版本、路径、修订和兼容边界已写入 docs/compatibility.md。
- [x] 最终回归：53 passed，13 subtests passed，4 个上游告警；ruff 检查与 preflight --offline 均通过。
- [x] 四个双击入口、使用说明、人设依据、验收报告已交付；安装副本哈希核对通过。
- [x] config 生产目录只有示例和版本清单，未生成真实账号配置；data 仅安装了插件副本。
- [ ] Task 11 / B：真实 Key、QQ 扫码、小号版本和原生资料路径、指定群/私聊收发、模型人物表现、真实资源占用待用户确认后执行。
- 自动审批曾拒绝直接打印控制令牌的新增便利选项，已删除该方案；未以其他方式实现凭据显示。