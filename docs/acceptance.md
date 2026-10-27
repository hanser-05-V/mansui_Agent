# 满穗离线验收记录

2026-10-27，在本机执行。结论：**A 范围的制作、依赖安装和离线验证完成。53 项测试通过，13 个子测试通过；4 个上游兼容性告警。真实接入 B 尚未执行。**

最终命令：

~~~powershell
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B -m pytest 'E:\QQAgent\tests' -q -p no:cacheprovider --asyncio-mode=auto --tb=short --show-capture=no --basetemp='E:\QQAgent\runtime\test-state\pytest-final' --junitxml='E:\QQAgent\runtime\test-state\acceptance.xml'
& 'E:\QQAgent\runtime\venv\Scripts\ruff.exe' check --no-cache --select F 'E:\QQAgent\plugins\mansui_companion' 'E:\QQAgent\scripts' 'E:\QQAgent\tests'
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B 'E:\QQAgent\scripts\preflight.py' --offline
~~~

实际结果：

~~~text
53 passed, 4 warnings, 13 subtests passed in 70.40s
All checks passed!
preflight_ok
~~~

另通过：168 个依赖的 uv pip check；4 个 PowerShell 脚本语法解析；安装插件与源码逐文件 SHA-256 比对。依赖锁 SHA-256：
bf6b50e74ed6384a49a5f6f28beb34ccbfcfb708888493a11c26d06c76d44acf

测试使用合成账号、假模型、httpx MockTransport、Quart 内存 WebSocket 与本机临时后台进程。外部网络连接在 pytest 中被拦截。未使用真实 DeepSeek Key，未启动 QQ，未产生真实 API 费用或 QQ 消息。

## 验收映射

| 编号 | 离线证据与边界 |
| --- | --- |
| A01 本人私聊 | 每个新 ID 分别回应；媒体说明、管理命令、低兴趣返回修正 |
| A02 他人私聊 | 仅检查身份即拒绝；正文读取哨兵断言、真实转换器零处理；包含临时私聊 |
| A03 非白名单群 | 本人或 @ 也不会启用 |
| A04 群 @ | 结构化 @ 小号必回；纯文本发送不能执行 CQ 控制码 |
| A05 自主参与 | 连续多轮普通话题能连续回复，participate=false 无发送；引用附带的当前文字仍参与判断 |
| A06 自身/重复 | 自身拒绝、平台 ID 去重，转发/引用不展开 |
| A07 私聊隔离 | 群模型输入不含私聊哨兵 |
| A08 跨群隔离 | 群 A/B 上下文、来源校验与私聊分离 |
| A09 关系 | 初始 20、0–100、±1、600 秒、每日正负各 3、时区午夜；发送成功仅提交一次 |
| A10 刷分/权限 | 重复文字与要求改好感不给分；密钥入站/出站拦截；模型不能指定目标或操作配置 |
| A11 遗忘/纠正 | 来源、派生后续上下文、摘要失效；重启后不再检索旧值；独立事实保留 |
| A12 重启 | 重投去重；发送中断变 unknown_delivery，不自动重发；未发送必回可本机重试 |
| A13 异常 | 最多 3 次模型尝试、401 不重试、长 Retry-After 不提前重试、未知用量不当零；发送超时不加好感 |
| A14 人物/问答 | 提示词与 8 个自编语气样例已审阅；**真实模型的人物还原和问答质量待 B** |
| A15 路径/日志 | 项目产物、私有 Python、依赖、测试在 E 盘；拒绝越界与联接清理；备份排除秘密；**QQ 原生路径待 B** |
| A16 启停 | 真实模拟子进程：认证、互斥、重复启动、停止、PID 复用拒绝、Windows Job 仅关闭自己子进程 |
| A17 负载 | 队列有界、两个并行处理器、空闲队列移除、溢出本机可见；**真实 QQ 活跃群占用待 B** |
| A18 用量 | 205 次尝试统计、202 条连续完成后仍回复；费用未知、每日提醒重置，不停止服务 |
| A19 本人群消息 | 无 @、重复文字仍逐条回应；真实 AstrBot 流水线 + 模拟 OneBot 已验证 |

发送回执集成测试使用固定 aiocqhttp 的真实调用通道，模拟返回 status=ok、retcode=0、data.message_id，确认能提交数据库。错误令牌拒绝；不使用的 HTTP 事件入口显式关闭。真实框架默认 LLM 与内置回复关闭，插件 stop_event 后独占回复。

## 审查与修复

开发中逐项先运行缺失或边界失败测试，再实现/修复。修复了发布归档缺锁、插件专用根目录导入、HTTP 入口认证差异、上下文遗忘依赖、普通带引用消息参与、改好感请求、异常响应统计、非有限 Retry-After、停机迟到回复、跨日费用提醒。最后执行一次完整回归。

4 个告警来自上游 audioop 弃用和 jieba 正则转义，未修改上游源码。当前固定 Python 3.12.16 下测试通过；这不代表未来升级版本已经验证。

审批记录：新增直接显示控制令牌的便利选项被自动审批拒绝，已取消；最终状态入口不包含任何凭据显示功能。本次没有 Git 提交、发布、服务器操作、系统 PATH/注册表变更、真实 QQ 登录或付费 API 请求。

后续真实接入文件、次数及确认事项见 [operations.md](operations.md)。
