$scriptPath = Join-Path $PSScriptRoot 'git_sound.py'
Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe', 'pythonw.exe') -and $_.CommandLine -like "*`"$scriptPath`"*" } | ForEach-Object { Stop-Process -Id $_.ProcessId }
$tunnelPath = Join-Path $PSScriptRoot 'bin\cloudflared.exe'
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cloudflared.exe' -and $_.ExecutablePath -eq $tunnelPath } | ForEach-Object { Stop-Process -Id $_.ProcessId }
Write-Host 'Git Sound je zaustavljen.'
