param(
    [string]$TaskName = "KDCA Weekly Infectious Disease Kakao Report",
    [string]$PythonExe = "python",
    [string]$ScriptPath = "D:\감영병 모니터링\kdca_kakao_report.py",
    [string]$StartTime = "08:30"
)

$scriptFullPath = (Resolve-Path -LiteralPath $ScriptPath).Path
$workingDirectory = Split-Path -Parent $scriptFullPath
$action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$scriptFullPath`"" `
    -WorkingDirectory $workingDirectory

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At $StartTime
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Send the latest KDCA weekly infectious disease report to KakaoTalk every Friday morning." `
    -Force

Write-Host "Registered task: $TaskName"
Write-Host "Schedule: every Friday at $StartTime"
Write-Host "Script: $scriptFullPath"
