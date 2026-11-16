$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'git_sound.py'
$existing = Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe', 'pythonw.exe') -and $_.CommandLine -like "*`"$scriptPath`"*" }
if ($existing) { Write-Host 'Git Sound is already running.'; exit }
$tunnelPath = Join-Path $PSScriptRoot 'bin\cloudflared.exe'
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cloudflared.exe' -and $_.ExecutablePath -eq $tunnelPath } | ForEach-Object { Stop-Process -Id $_.ProcessId }
$python = (Get-Command pythonw.exe).Source
Start-Process -FilePath $python -ArgumentList @('"' + $scriptPath + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
