# 本机使用与接入步骤

当前完成制作和离线测试，尚未登录真实 QQ 或使用真实 API Key。下一阶段接入操作在本文最后单独列明。

## DeepSeek API Key

打开 [DeepSeek 开放平台](https://platform.deepseek.com/)，使用自己的账号登录，在 API Keys 管理中创建密钥。按控制台提示检查余额与 API 使用权限。普通聊天网页的登录状态不等于这个本地程序已经取得 API Key。

接入获准后双击 E:\QQAgent\配置满穗.cmd，填写本人 QQ、机器人小号 QQ、逗号分隔的群号和 API Key。密钥输入不回显，回车可保留已有值；保存前会显示账号和目录供本机核对。不要把 Key 粘贴到开发对话或 QQ 群。

本项目只调用 [官方 Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)，默认 deepseek-flash，显式关闭思考模式，输出结构化 JSON；不启用联网工具或额外代理。

## 首次启动

先完成小号版本和会话目录核验，随后使用「启动满穗」。状态显示服务已就绪并不代表 QQ 已登录，应同时核对 onebot_connected 与 qq_login。使用专门小号扫码，并且仅加入填写的测试群。

NapCat 的本机 WebUI 位于 http://127.0.0.1:6099，开启令牌认证。凭据只保存在本地受限文件中；本项目状态输出不显示令牌。首次扫码界面与认证流程将在接入阶段现场验证。

「查看状态」是独立窗口，关掉不会停止后台。停止时用「停止满穗」。不要手动运行上游 KillQQ.bat 或任意关闭所有 QQ 的命令。

## 费用与运行情况

一次 API 调用不一定等于一条 QQ 回复：普通群候选可能选择沉默，偶尔要压缩当前会话摘要，网络重试也会增加尝试次数。没有固定每日调用上限。并发最多 2、每会话等待最多 10，这些控制同时处理的工作量。

状态分别统计日/月尝试数、已知输入输出 tokens、未知用量和未知费用。pricing 默认空，表示没有已核实的价格快照，不能把未知金额当零。需要估价时在本机依据 [官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)填写模型、币种、日期与缓存命中/未命中及输出单价；cost_reminder_cny 只提醒，不停止回复。

常见状态：

| 状态 | 含义与处理 |
| --- | --- |
| configuration_missing_or_invalid | 尚未完成本机账号配置 |
| qq_session_path_not_verified | QQ 原生资料目录尚未核实 |
| port_in_use | 指定端口被占用；程序不会终止别的软件 |
| plugin_copy_mismatch | 人设或插件源码与安装副本不一致，需同步安装副本 |
| http_401 / http_403 | API 凭据或权限问题，在本机重新配置 |
| http_402 | 检查账户余额 |
| http_429 / rate_limit_wait_too_long | 服务端限流，本次请求停止有限重试 |
| queue_full / overloaded | 有消息未能进入有限队列，本机列出事件序号 |
| awaiting_retry / failed | 可明确选择重新处理 |
| unknown_delivery | 发送结果不明，不能自动重发 |
| model_output_invalid | 模型输出结构异常，必回消息收到简短说明 |
| reminder_reached | 当日可估算金额触及提醒值；聊天仍继续 |

明确未发送的事件可在本机用：
`E:\QQAgent\runtime\venv\Scripts\python.exe -B E:\QQAgent\scripts\status.py --retry 事件序号`
手动重试。送达不明状态不能用这个入口重试，避免重复发送。

## 记忆与维护

管理命令仅本人私聊生效，群中同样的文字不会执行管理动作。长期记忆编号与作用域绑定。遗忘和纠正会清除旧来源以及依赖它的后续上下文；这是应用层遗忘，不承诺磁盘取证级擦除或模型供应商的数据删除。

需要管理群成员记忆时，先停止满穗，再运行：
`E:\QQAgent\runtime\venv\Scripts\python.exe -B E:\QQAgent\scripts\configure.py --manage-memory`
本机明确选择允许群与成员，不能借私聊命令读取其他群。

聊天原文保留 30 天。媒体临时缓存清理限定项目缓存目录；不遍历 QQ 登录目录，不沿联接或符号链接删除。项目正常关闭原文日志；维护限制项目状态日志总量。备份只包含示例配置、版本记录与人设，不包含消息库、真实配置、密钥或 QQ 会话。

## 下一阶段真实接入范围（尚未执行）

需要确认本人 QQ、小号 QQ 与测试群。API Key 由本人在本机填写。计划写入：

- E:\QQAgent\config\mansui.local.json、secrets.local.json
- E:\QQAgent\data\mansui.sqlite3 及 SQLite 辅助文件
- E:\QQAgent\data\astrbot\data 下的真实框架配置和数据库
- E:\QQAgent\data\napcat 下的小号配置与必要缓存，包含 config\onebot11_小号QQ.json
- E:\QQAgent\runtime\state 与 logs 下的脱敏运行记录
- E:\QQAgent\config\versions.lock.json 中经验证的 QQ 启动路径与兼容记录

在不触碰主号会话的前提下核实小号扫码、最多 10 次初始 API 调用和最多 10 条本人私聊/测试群回复；后续持续运行由用户自行启动。若 QQ 原生目录必须在项目之外，先列出确切路径再确认，不自动迁移现有 QQ 数据。
