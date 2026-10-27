# 满穗 QQ 聊天伙伴

程序与依赖已制作在 **E:\QQAgent**。本次交付的是完成离线验证的本地版本；真实 QQ 小号、测试群和 DeepSeek Key 尚未接入。首次接入前还需核对 QQ 自身的会话目录，启动自检会对此明确阻止，不会自行登录账号。

| 双击入口 | 用途 |
| --- | --- |
| 配置满穗.cmd | 本机填写本人 QQ、小号 QQ、允许群和 API Key；Key 输入不回显 |
| 启动满穗.cmd | 自检后在后台启动 |
| 查看状态.cmd | 查看连接、队列、未应答和 API 用量 |
| 停止满穗.cmd | 有序停止本项目及其自己启动的子进程 |

接入后，你的私聊以及已启用群里的每条消息都会进入必回复流程，别人只能在允许群里互动。别人 @ 满穗会回复；普通群话题由满穗结合语境决定是否参与。相同文字但不同消息仍分别回应；同一事件重复投递只处理一次。

第一版支持文字。纯图片、语音和转发会提示补充文字，不自动识别附件。人格保留满穗的警觉、克制和主见，不默认恋爱关系。好感度表示信任，不影响是否回复你。

没有每天 200 次的停聊限制，也没有每小时三次的发言限制。API 按模型服务计费，实际聊天、重试和压缩摘要都可能产生调用；状态中用量缺失时显示未知。价格与提醒阈值未填写时不会编造费用。

每会话最多等待 10 条，最多并行处理两个会话。网络故障或队列满时，状态中显示未完成记录。发送结果不明的消息不自动重发。正常使用时电脑必须开机、保持唤醒并联网；锁屏通常不影响后台运行，睡眠、休眠或断网会中断服务。

本人私聊可发送：

- `/满穗 帮助`
- `/满穗 关系`
- `/满穗 记住 喜欢喝茶`
- `/满穗 记忆`
- `/满穗 纠正 1 喜欢喝花茶`
- `/满穗 遗忘 1`
- `/满穗 重置关系 确认`

聊天原文默认保留 30 天，明确记住的内容长期保留。私聊与各个群的记忆隔离。遗忘会使来源及引用它的后续上下文失效，其他独立保存的事实保留。

详细步骤见 [使用与接入说明](docs/operations.md)，测试证据见 [离线验收记录](docs/acceptance.md)，版本与目录见 [兼容记录](docs/compatibility.md)。

## 换电脑继续开发

仓库保存源码、人设、测试、文档、示例配置和依赖锁定文件。Python、AstrBot、NapCat 等运行环境由安装脚本下载；API Key、QQ 登录资料、聊天记录与本机配置不随 Git 同步。

当前脚本固定使用 **E:\QQAgent**。家中 Windows 电脑需有 E 盘、安装 Git，并保持这个目录为空或尚不存在。在 PowerShell 中执行：

```powershell
git clone https://github.com/hanser-05-V/mansui_Agent.git E:\QQAgent
powershell -NoProfile -ExecutionPolicy Bypass -File E:\QQAgent\scripts\prepare.ps1
& E:\QQAgent\runtime\venv\Scripts\python.exe -B E:\QQAgent\scripts\preflight.py --offline
```

安装脚本使用仓库中的 `app/AstrBot/uv.lock` 恢复已锁定依赖，下载与缓存都在 E:\QQAgent 内。下载需要访问 GitHub 和 Python 包源。离线自检成功只代表运行环境就绪；QQ 小号和 DeepSeek Key 仍需在新电脑上单独配置，并完成 [首次接入核验](docs/operations.md#下一阶段真实接入范围尚未执行)。

主要编辑 `plugins/mansui_companion`（角色与聊天逻辑）、`scripts`（本机配置与启停）和 `tests`。插件源码修改后，先停止满穗，再重新运行 `prepare.ps1` 同步安装副本和版本记录。

离线测试命令（使用模拟接口，不调用真实模型或 QQ）：

```powershell
& E:\QQAgent\runtime\venv\Scripts\python.exe -B -m pytest E:\QQAgent\tests -q -p no:cacheprovider --asyncio-mode=auto --tb=short --show-capture=no --basetemp=E:\QQAgent\runtime\test-state\pytest-dev
```

两台电脑接力时，开始修改前在项目目录执行 `git pull --ff-only`，结束后检查 `git diff` 和 `git status`，再提交并推送；如有本地未提交改动，先处理这些改动。各电脑需要自行登录 GitHub 才能推送。`.gitignore` 已排除运行资料与密钥，不要强制添加这些文件。
