@'
{
  "mcpServers": {
    "shell": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-shell"]
    }
  }
}
'@ | Out-File -Encoding UTF8 "$env:APPDATA\Claude\claude_desktop_config.json"

Write-Host "✅ MCP 配置已创建: $env:APPDATA\Claude\claude_desktop_config.json"
Write-Host "⚠️  请重启 Claude Desktop / Cowork 应用使配置生效"
Write-Host ""
Write-Host "验证方法: 重启后，我就可以调用 shell 工具了"
