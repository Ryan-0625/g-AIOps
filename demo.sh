#!/bin/bash
# gAIOps CLI Demo Script
# Usage: ./demo.sh
# Prerequisites: docker compose up -d master worker brain

set -e

export CLUSTER_TOKEN=dev-token-change
export BASE_URL="http://localhost:8080"
export BRAIN_URL="http://localhost:9091"

CLI="python cli/gaiops"
DELAY=1.5

# ── Helper ───────────────────────────────────────────────────────────────────

section() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    sleep 0.5
}

comment() {
    echo ""
    echo "  💬 $1"
    sleep 0.3
}

# ── Demo Start ───────────────────────────────────────────────────────────────

clear

section "🚀 gAIOps CLI Demo — LLM驱动的分布式运维决策系统"
sleep 1

# ── 1. Logo & Help ──────────────────────────────────────────────────────────

section "1. 入口展示 — Logo 与命令列表"
comment "直接输入 gaiops，展示系统标识与可用命令"
sleep 1
$CLI
sleep $DELAY

# ── 2. Health Check ─────────────────────────────────────────────────────────

section "2. 集群健康检查"
comment "查看 Master、Worker、待处理任务的整体状态"
$CLI health
sleep $DELAY

# ── 3. Worker Nodes ─────────────────────────────────────────────────────────

section "3. 节点管理 — 查看在线 Worker"
comment "单主机 Master + 轻量化远程 Worker 架构，节点自动注册"
$CLI worker list
sleep $DELAY

# ── 4. System Inspection ────────────────────────────────────────────────────

section "4. 运维场景一：系统巡检"
comment "查看系统基础信息"
$CLI execute system.info --wait
sleep $DELAY

comment "检查 CPU 负载"
$CLI execute cpu.usage --wait
sleep $DELAY

comment "检查内存使用"
$CLI execute memory.usage --wait
sleep $DELAY

comment "检查磁盘空间"
$CLI execute disk.usage --wait
sleep $DELAY

# ── 5. Network Diagnosis ────────────────────────────────────────────────────

section "5. 运维场景二：网络诊断"
comment "DNS 解析测试"
$CLI execute dns.lookup hostname=baidu.com --wait
sleep $DELAY

comment "HTTP 连通性测试"
$CLI execute http.get url=https://httpbin.org/get --wait
sleep $DELAY

# ── 6. Status Dashboard ─────────────────────────────────────────────────────

section "6. 状态仪表板"
comment "聚合展示集群健康、节点负载、待处理任务"
$CLI status
sleep $DELAY

# ── 7. Trace Tracking ───────────────────────────────────────────────────────

section "7. 链路追踪"
comment "查看最近的操作记录"
$CLI trace list
sleep $DELAY

# ── 8. Chat Mode — Natural Language ─────────────────────────────────────────

section "8. 自然语言交互 — Chat 模式"
comment "进入 Chat，用中文直接询问系统状态"
sleep 1

# Use a here-document to feed chat commands
$CLI chat << 'CHAT_EOF'
查看系统状态
CPU负载怎么样
检查百度是否可用
/exit
CHAT_EOF

sleep $DELAY

# ── 9. Shell Mode ───────────────────────────────────────────────────────────

section "9. 交互式 Shell"
comment "进入交互式 Shell，支持 tab 补全和会话保持"
sleep 1

# Feed shell commands
$CLI shell << 'SHELL_EOF'
health
workers
status
exit
SHELL_EOF

sleep $DELAY

# ── 10. Config ──────────────────────────────────────────────────────────────

section "10. 配置管理"
comment "查看当前配置，Token 自动掩码"
$CLI config show
sleep $DELAY

# ── End ─────────────────────────────────────────────────────────────────────

section "✅ Demo 完成"
echo ""
echo "  📋 覆盖功能："
echo "     • 集群健康检查 (health)"
echo "     • 节点管理 (worker list)"
echo "     • 工具执行 (execute)"
echo "     • 状态仪表板 (status)"
echo "     • 链路追踪 (trace)"
echo "     • 自然语言交互 (chat)"
echo "     • 交互式 Shell (shell)"
echo "     • 配置管理 (config)"
echo ""
echo "  🔧 演示场景："
echo "     • 系统巡检：info → cpu → memory → disk"
echo "     • 网络诊断：dns → http"
echo "     • AI 交互：自然语言查询与多轮对话"
echo ""
