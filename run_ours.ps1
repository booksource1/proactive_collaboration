param (
    [Parameter(Mandatory = $false)][string]$ArgFile,
    [Parameter(Mandatory = $true)][int]$Scene,
    [Parameter(Mandatory = $true)][int]$ParallelCount
)

$config = @{
    Servers    = @("192.168.1.53", "192.168.1.90", "192.168.1.131", "192.168.1.16")
    PortStart  = 7210
    PortEnd    = 7249
    BlackPorts = @(7226)
}

# 获取主程序名称（不带路径）
$mainScriptName = Split-Path $MyInvocation.MyCommand.Path -Leaf

function Initialize-Environment {
    param (
        [string]$BaseDir,
        [string]$LogsDir
    )
    
    if (-not (Test-Path $LogsDir)) {
        New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
    }
    
    return @{
        Args       = Join-Path $BaseDir "args/select_args.json"
        Main       = Join-Path $BaseDir "main.py"
        PortLog    = Join-Path $LogsDir "trans.log"
        ProcessLog = Join-Path $LogsDir "process_status.txt"
        LastUsed   = Join-Path $LogsDir "last_server_port.json"
    }
}

function Update-ConfigFile {
    param (
        [string]$ArgsPath,
        [string]$Server,
        [int]$Port,
        [int]$Scene,
        [string]$ArgFile
    )
    
    $selectArgs = @{
        "remote_url" = "http://$($Server):$($Port)/"
        "scene"      = $Scene
    }
    
    if (-not [string]::IsNullOrEmpty($ArgFile)) {
        $selectArgs["args_file"] = $ArgFile
    }
    
    $selectArgs | ConvertTo-Json | Set-Content $ArgsPath
}

function Update-MainFile {
    param (
        [string]$MainPath,
        [int]$ParallelCount,
        [int]$CurrentNum
    )
    
    $content = Get-Content $MainPath -Raw
    $pattern = '(?<=if __name__ == "__main__":\r?\n\s{4})SCRIPT_COUNT = \d+\r?\n\s{4}SCRIPT_NUM = \d+'
    $replacement = "SCRIPT_COUNT = $ParallelCount`r`n    SCRIPT_NUM = $CurrentNum"
    $newContent = $content -replace $pattern, $replacement
    Set-Content -Path $MainPath -Value $newContent -NoNewline
}

function Get-NextServerPort {
    param (
        [int]$LastServerIndex,
        [int]$LastPort,
        [hashtable]$Config
    )
    
    $port = $LastPort
    $serverIndex = $LastServerIndex
    
    do {
        if ($port -eq $Config.PortEnd) {
            $serverIndex = ($LastServerIndex + 1) % $Config.Servers.Length
            $port = $Config.PortStart
        }
        else {
            $port = $port + 1
        }
    } until (-not ($Config.BlackPorts -contains $port))
    
    return @{
        ServerIndex = $serverIndex
        Port        = $port
        Server      = $Config.Servers[$serverIndex]
    }
}
# 修改事务日志记录逻辑
function Write-TransactionLog {
    param (
        [string]$LogPath,
        [int]$Scene,
        [int]$ParallelCount,
        [string]$MainScript,
        [string]$Server,
        [int]$Port,
        [string]$ArgFile
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = @(
        "Timestamp: $timestamp",
        "Scene: $Scene",
        "ParallelCount: $ParallelCount",
        "Main: $MainScript",
        "Server: ${Server}:$Port",
        "ArgsFile: $(if ($ArgFile) { $ArgFile } else { 'N/A' })"
    ) -join " | "
    
    $logEntry | Add-Content $LogPath
}

# 修改进程记录逻辑
function Write-ProcessLog {
    param (
        [string]$LogPath,
        [int]$Scene,
        [int]$ParallelCount,
        [string]$MainScript,
        [int]$ProcessID,
        [string]$ArgFile
    )
    
    $logEntry = @(
        "Scene: $Scene",
        "Parallel: $ParallelCount",
        "Main: $MainScript",
        "PID: $ProcessID",
        "ArgsFile: $(if ($ArgFile) { $ArgFile } else { 'N/A' })"
    ) -join " | "
    
    $logEntry | Add-Content $LogPath
}

# 初始化环境（日志目录改为上层）
$logsDir = Join-Path $PSScriptRoot "..\logs"
$paths = Initialize-Environment -BaseDir $PSScriptRoot -LogsDir $logsDir

Write-Host "正在初始化环境..."
try {
    conda activate dynamic_teaming
    Write-Host "✅ Conda环境激活成功"
}
catch {
    Write-Error "❌ Conda环境激活失败: $_"
    exit 1
}

$lastUsed = if (Test-Path $paths.LastUsed) {
    Get-Content $paths.LastUsed | ConvertFrom-Json
}
else {
    @{
        serverIndex = 0
        port        = $config.PortStart - 1
    }
}

Write-Host "正在启动 $ParallelCount 个并行任务 (场景: $Scene)..."
for ($i = 0; $i -lt $ParallelCount; $i++) {
    try {
        $nextServer = Get-NextServerPort -LastServerIndex $lastUsed.serverIndex -LastPort $lastUsed.port -Config $config
        
        # 更新配置文件
        Update-ConfigFile -ArgsPath $paths.Args -Server $nextServer.Server -Port $nextServer.Port -Scene $Scene -ArgFile $ArgFile
        
        # 更新主程序文件
        Update-MainFile -MainPath $paths.Main -ParallelCount $ParallelCount -CurrentNum $i

        # 启动进程
        $process = Start-Process -FilePath "python" -ArgumentList $paths.Main -PassThru -WindowStyle Hidden

        # 记录事务日志
        Write-TransactionLog -LogPath $paths.PortLog -Scene $Scene -ParallelCount $ParallelCount `
            -MainScript $mainScriptName -Server $nextServer.Server -Port $nextServer.Port -ArgFile $ArgFile
        
        # 记录进程日志
        Write-ProcessLog -LogPath $paths.ProcessLog -Scene $Scene -ParallelCount $ParallelCount `
            -MainScript $mainScriptName -ProcessID $process.Id -ArgFile $ArgFile
        
        Write-Host "🟢 启动成功 | 场景:$Scene | 并行数:$ParallelCount | 主程序:$mainScriptName | PID:$($process.Id)"
        
        if ($i -eq ($ParallelCount - 1)) {
            @{
                serverIndex = $nextServer.ServerIndex
                port        = $nextServer.Port
            } | ConvertTo-Json | Set-Content $paths.LastUsed
        }
        
        $lastUsed.serverIndex = $nextServer.ServerIndex
        $lastUsed.port = $nextServer.Port
        Start-Sleep -Seconds 2
    }
    catch {
        Write-Host "❌ 启动失败 | 场景:$Scene | 并行数:$ParallelCount | 错误: $_" -ForegroundColor Red
    }
}

Write-Host "`n✅ 所有 $ParallelCount 个进程已成功启动！"
Write-Host "📜 事务日志: $($paths.PortLog)"
Write-Host "📊 进程日志: $($paths.ProcessLog)"