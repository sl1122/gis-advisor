$ErrorActionPreference = "Stop"

# Keep PowerShell and Python subprocess text output in UTF-8 for this session.
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
chcp 65001 | Out-Null

# Load user-level API keys if the current shell has not set them.
$userDeepSeekKey = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")
if (-not $env:DEEPSEEK_API_KEY -and $userDeepSeekKey) {
  $env:DEEPSEEK_API_KEY = $userDeepSeekKey
}

$userOpenAIKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")
if (-not $env:OPENAI_API_KEY -and $userOpenAIKey) {
  $env:OPENAI_API_KEY = $userOpenAIKey
}

Set-Location -LiteralPath $PSScriptRoot
python -m autogis web
