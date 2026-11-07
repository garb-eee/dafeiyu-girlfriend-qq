# S0 离线验收入口（Windows PowerShell）
# 运行全部 S0 检查。不联网、不连接 QQ/NapCat、不发送任何消息。
# 用法：.\scripts\run-s0.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }

if ($py) {
    & $py.Source tests/s0_checks.py
    exit $LASTEXITCODE
} else {
    Write-Error "未找到 python，请先安装 Python 3（仅标准库即可）。"
    exit 1
}
