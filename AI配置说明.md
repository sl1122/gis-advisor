# AI 配置说明

## DeepSeek

本工具默认优先使用 DeepSeek。

在启动 Web 服务前，在 PowerShell 中设置：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
```

然后使用 UTF-8 启动脚本：

```powershell
.\start_web_utf8.ps1
```

默认模型：

```text
deepseek-v4-flash
```

也可以在网页的“模型”输入框中临时改成其他模型。

## OpenAI

如果需要切换到 OpenAI：

```powershell
$env:OPENAI_API_KEY="你的 OpenAI API Key"
.\start_web_utf8.ps1
```

然后在网页里把 AI 选择为 OpenAI。

## 关于中文乱码

不要用 PowerShell 直接写入包含大量中文的源码。项目内手写中文 UI 时优先使用：

- HTML 实体
- JavaScript Unicode 转义
- UTF-8 文件

推荐始终用 `start_web_utf8.ps1` 启动本项目，脚本会为当前会话设置：

```text
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
chcp 65001
PowerShell Input/OutputEncoding = UTF-8
```

不建议自动修改全局 PowerShell Profile，因为这会影响你其他课程软件和命令行工具。

