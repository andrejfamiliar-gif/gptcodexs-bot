$project = $PSScriptRoot
$logDirectory = Join-Path $project "logs"
$logPath = Join-Path $logDirectory "bot.log"

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$python = (Get-Command python.exe -ErrorAction Stop).Source

$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -LiteralPath $logPath -Value "`n--- bot start $startedAt ---"
& $python -u (Join-Path $project "bot.py") 2>&1 | Tee-Object -FilePath $logPath -Append
exit $LASTEXITCODE
