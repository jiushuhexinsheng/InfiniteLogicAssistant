# 创建带项目图标的桌面快捷方式（Windows）。
# Create a desktop shortcut carrying the project icon.
#
# 用法 / Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1 -Name "无限逻辑"
param(
    [string]$Name = "无限逻辑·语音助手"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root "start.bat"
$icon = Join-Path $root "assets\icon.ico"

if (-not (Test-Path $target)) { throw "找不到启动脚本：$target" }
if (-not (Test-Path $icon)) { throw "找不到图标文件：$icon" }

$desktop = [Environment]::GetFolderPath("Desktop")
$linkPath = Join-Path $desktop "$Name.lnk"

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($linkPath)
$link.TargetPath = $target
$link.WorkingDirectory = $root
$link.IconLocation = "$icon,0"
$link.Description = "无限逻辑·语音全控智能体"
$link.Save()

Write-Host "已创建快捷方式：$linkPath"
Write-Host "图标：$icon"
