$configPath = "$env:APPDATA\Claude\claude_desktop_config.json"
$shellConfig = @{
    command = "npx"
    args = @("-y", "@anthropic/mcp-server-shell")
}

if (Test-Path $configPath) {
    # 读取已有配置，追加新的 MCP
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    if (-not $config.mcpServers) {
        $config | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue @{}
    }
    # 如果要追加，取消下面一行的注释
    # $config.mcpServers | Add-Member -NotePropertyName "shell" -NotePropertyValue $shellConfig -Force
    Write-Host "⚠️  已有配置文件: $configPath"
    Write-Host "请手动添加以下内容到 mcpServers 节点中:"
    Write-Host ""
    Write-Host ($shellConfig | ConvertTo-Json)
} else {
    # 创建全新配置
    $config = @{
        mcpServers = @{
            shell = $shellConfig
        }
    }
    $config | ConvertTo-Json -Depth 10 | Out-File -Encoding UTF8 $configPath
    Write-Host "✅ 新配置已创建: $configPath"
}

Write-Host ""
Write-Host "⚠️  请重启 Claude Desktop / Cowork 应用使配置生效"
