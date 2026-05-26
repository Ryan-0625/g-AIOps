# Claude Desktop MCP Config Tool - Add Shell MCP Server
$configPath = "$env:LOCALAPPDATA\Claude-3p\claude_desktop_config.json"
$shellMcp = @{
    command = "npx"
    args = @("-y", "@anthropic/mcp-server-shell")
}

if (Test-Path $configPath) {
    $raw = Get-Content $configPath -Raw
    $config = $raw | ConvertFrom-Json
    if ($null -eq $config.mcpServers) {
        $config | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue @{} -Force
    }
    $config.mcpServers | Add-Member -NotePropertyName "shell" -NotePropertyValue $shellMcp -Force
    $config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8
    Write-Host "[OK] Updated: $configPath"
} else {
    Write-Host "[ERROR] File not found: $configPath"
    exit 1
}

Write-Host ""
Write-Host "Current config:"
Get-Content $configPath -Raw | ConvertFrom-Json | ConvertTo-Json -Depth 10
Write-Host ""
Write-Host "[IMPORTANT] Restart Cowork app to apply changes"
