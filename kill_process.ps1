param (
    [Parameter(Mandatory = $false)][int]$Scene,
    [Parameter(Mandatory = $false)][int]$ParallelCount,
    [Parameter(Mandatory = $false)][string]$MainScript,
    [Parameter(Mandatory = $false)][string]$ArgFile
)

$processLogFile = "..\logs/process_status.txt"

if (-not (Test-Path $processLogFile)) {
    Write-Host "⚠️ 进程日志文件不存在"
    exit
}

# 构建过滤条件
$filters = @()
if ($PSBoundParameters.ContainsKey('Scene')) { $filters += "Scene: $Scene" }
if ($PSBoundParameters.ContainsKey('ParallelCount')) { $filters += "Parallel: $ParallelCount" }
if ($PSBoundParameters.ContainsKey('MainScript')) { $filters += "Main: $MainScript" }
if ($PSBoundParameters.ContainsKey('ArgFile')) { $filters += "ArgsFile: $ArgFile" }

if ($filters.Count -eq 0) {
    Write-Host "⚠️ 请至少指定一个过滤条件（Scene/ParallelCount/MainScript/ArgFile）"
    exit
}

# 生成正则表达式模式
$pattern = ($filters -join ".*") -replace " ", "\s*"

# 查找匹配进程
$content = Get-Content $processLogFile
$matchedProcesses = $content | Where-Object { $_ -match $pattern }

if (-not $matchedProcesses) {
    Write-Host "ℹ️ 未找到匹配的进程"
    exit
}

# 终止进程并更新日志
$remainingProcesses = @()
$content | ForEach-Object {
    if ($_ -match $pattern) {
        if ($_ -match "PID: (\d+)") {
            $processId = $matches[1]
            try {
                Stop-Process -Id $processId -Force -ErrorAction Stop
                Write-Host "🛑 已终止进程 | $_"
            } catch {
                Write-Host "❌ 终止失败 | PID:${processId} | 错误: $_" -ForegroundColor Red
                $remainingProcesses += $_
            }
        }
    } else {
        $remainingProcesses += $_
    }
}

# 更新进程日志
$remainingProcesses | Set-Content $processLogFile

Write-Host "`n✅ 操作完成 | 共终止 $($matchedProcesses.Count) 个进程"