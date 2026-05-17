#!/usr/bin/env python3
"""
gAIOps 全自动演示脚本
—— LLM驱动的分布式运维决策系统
设计为"场景故事"形式，模拟真实运维操作流程

前置条件：docker compose up -d master worker brain
"""

import subprocess
import sys
import time
import os
import json
import urllib.request
import urllib.error

# 强制 UTF-8 输出，避免 GBK 编码问题
if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

os.environ["CLUSTER_TOKEN"] = "dev-token-change"
BASE_URL = "http://localhost:8080"
BRAIN_URL = "http://localhost:9091"

# ── 输出样式 ─────────────────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def c(text, color):
    return f"{color}{text}{RESET}"


def section(title):
    print(f"\n  {c('┌' + '─' * 58 + '┐', CYAN)}")
    print(f"  {c('│' + title.center(56) + '│', CYAN)}")
    print(f"  {c('└' + '─' * 58 + '┘', CYAN)}")
    time.sleep(1)


def narration(text):
    print(f"\n  {c('• ' + text, YELLOW)}")
    time.sleep(1.5)


def run_cmd(cmd, wait=4):
    """执行命令并输出结果"""
    print(f"\n  {c('$ ' + cmd, GREEN)}")
    time.sleep(1)
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=60,
            encoding='utf-8', errors='replace'
        )
        output = (result.stdout + result.stderr).strip()
        for line in output.split('\n'):
            line = line.strip()
            if line:
                print(f"  {line}")
    except subprocess.TimeoutExpired:
        print(f"  {c('[TIMEOUT] Command timed out', RED)}")
    print()
    time.sleep(wait)


def chat_turn(question, wait=4):
    """直接调用 Brain API 进行自然语言对话"""
    print(f"\n  {c('User:', BOLD)} {question}")
    time.sleep(1)

    url = f"{BRAIN_URL}/api/chat"
    headers = {
        "Authorization": f"Bearer {os.environ['CLUSTER_TOKEN']}",
        "Content-Type": "application/json",
    }
    body = json.dumps({"message": question}).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        conclusion = data.get("conclusion", "").strip()
        if conclusion:
            print(f"\n  {c('Brain:', CYAN)} {conclusion}")
        else:
            print(f"\n  {c('Brain:', CYAN)} (no response)")
    except urllib.error.HTTPError as e:
        print(f"\n  {c(f'[API Error] {e.code}', RED)}")
    except Exception as e:
        print(f"\n  {c(f'[API Error] {e}', RED)}")
    time.sleep(wait)


# ═══════════════════════════════════════════════════════════════════════════════
# Demo Start
# ═══════════════════════════════════════════════════════════════════════════════

os.system('cls' if os.name == 'nt' else 'clear')

print(f"""
  {c('╔══════════════════════════════════════════════════════════╗', CYAN)}
  {c('║', CYAN)}       gAIOps CLI 全自动演示 — 运维场景模拟       {c('║', CYAN)}
  {c('║', CYAN)}    LLM驱动的分布式运维决策系统                     {c('║', CYAN)}
  {c('╚══════════════════════════════════════════════════════════╝', CYAN)}
""")
time.sleep(2)

try:
    input(f"  {c('按 Enter 开始演示...', DIM)}")
except (EOFError, KeyboardInterrupt):
    print()
    pass
print()

# ═══════════════════════════════════════════════════════════════════════════════
# 场景一：登录巡检
# ═══════════════════════════════════════════════════════════════════════════════

section("场景一：日常巡检 — 查看集群概况")

narration("运维工程师第一件事：检查集群是否正常、节点是否在线。")

run_cmd("python cli/gaiops health", wait=3)

narration("1 个 Worker 在线，一切正常。让我看看是哪个节点。")

run_cmd("python cli/gaiops worker list", wait=3)

# ═══════════════════════════════════════════════════════════════════════════════
# 场景二：发现异常
# ═══════════════════════════════════════════════════════════════════════════════

section("场景二：系统巡检 — 发现问题")

narration("做一轮系统巡检：先看系统概览，再看 CPU、内存、磁盘。")

run_cmd("python cli/gaiops execute system.info --wait", wait=3)

narration("20 核 CPU，7.6GB 内存，Linux 系统。基础信息正常。继续检查 CPU 负载。")

run_cmd("python cli/gaiops execute cpu.usage --wait", wait=3)

narration("CPU 空闲 99%，负载很低。看来不是 CPU 的问题。检查内存使用。")

run_cmd("python cli/gaiops execute memory.usage --wait", wait=3)

narration("内存使用率 58% 左右，属于正常范围。再看看磁盘。")

run_cmd("python cli/gaiops execute disk.usage --wait", wait=3)

narration("磁盘使用率只有 5.5%，非常充裕。但作为监控系统，不能只看一次数据。")

narration("顺便做个网络检查，避免节点间通信出问题。")

run_cmd("python cli/gaiops execute dns.lookup hostname=baidu.com --wait", wait=3)

narration("DNS 解析正常，4 个 IP 返回。再测一下外网连通性。")

run_cmd("python cli/gaiops execute http.get url=https://httpbin.org/get --wait", wait=3)

narration("HTTP 200，延迟正常。综合来看节点状态健康，暂未发现异常。")

# ═══════════════════════════════════════════════════════════════════════════════
# 场景三：AI 交互诊断
# ═══════════════════════════════════════════════════════════════════════════════

section("场景三：AI 自然语言交互 — 智能诊断")

narration("场景：运维工程师不在电脑前，通过自然语言询问系统状态。")

chat_turn("当前系统状态怎么样", wait=3)

narration("Brain 返回了简洁的集群健康报告。继续追问具体指标。")

chat_turn("检查CPU负载", wait=3)

narration("CPU 负载很低，运行平稳。再 ping 一下百度检查网络延迟。")

chat_turn("ping 百度", wait=4)

narration("网络连通正常。AI 交互演示完成，接下来进入链路追踪环节。")

# ═══════════════════════════════════════════════════════════════════════════════
# 场景四：问题定位
# ═══════════════════════════════════════════════════════════════════════════════

section("场景四：问题定位 — 模拟排查")

narration("运维中出了问题需要回溯操作记录，Trace 机制可以帮我们找到当时的上下文。")

narration("回顾刚才执行的每条命令，输出中都包含了 trace_id。以 system.info 为例，每条操作都有唯一的追踪标识。")

narration("TraceID 贯穿 Brain -> Master -> Worker 三层，每一步都有记录，方便运维人员回溯问题根因。")

# ═══════════════════════════════════════════════════════════════════════════════
# 场景五：模拟预警
# ═══════════════════════════════════════════════════════════════════════════════

section("场景五：模拟告警响应")

narration("假设收到告警：节点磁盘使用率突然冲高到 85%，需要紧急排查。")

narration("首先确认告警节点是否在线。")

run_cmd("python cli/gaiops status", wait=3)

narration("节点在线。用 AI 快速查看磁盘状态。")

chat_turn("检查磁盘使用率", wait=3)

narration("在实际生产环境中，Brain 收到告警后会启动完整的诊断管道：")
narration("执行磁盘分析 -> 定位大文件 -> 评估扩容风险 -> 给出清理建议，全部通过 TraceID 记录可追溯。")

# ═══════════════════════════════════════════════════════════════════════════════
# 场景六：演示收尾
# ═══════════════════════════════════════════════════════════════════════════════

section("场景六：演示收尾 — 成果总结")

narration("完整的运维场景演示已完成。下面回顾系统设计理念。")

print(f"""
  {c('╔══════════════════════════════════════════════════════════╗', CYAN)}
  {c('║', CYAN)}                  演示总结                        {c('║', CYAN)}
  {c('╠══════════════════════════════════════════════════════════╣', CYAN)}
  {c('║', CYAN)}  系统架构                                        {c('║', CYAN)}
  {c('║', CYAN)}    单主机 Master + 轻量化远程 Worker 节点拓扑    {c('║', CYAN)}
  {c('║', CYAN)}    Worker 通过 WebSocket 向 Master 注册能力      {c('║', CYAN)}
  {c('║', CYAN)}    Brain 作为 LLM 推理层，解析自然语言指令       {c('║', CYAN)}
  {c('╠══════════════════════════════════════════════════════════╣', CYAN)}
  {c('║', CYAN)}  核心能力                                        {c('║', CYAN)}
  {c('║', CYAN)}    意图路由：快速执行通道 / 多步推理管道         {c('║', CYAN)}
  {c('║', CYAN)}    状态机：Analyst -> Planner -> Execute -> Reflector{c('║', CYAN)}
  {c('║', CYAN)}    链路可视：TraceID 全链路追踪                 {c('║', CYAN)}
  {c('║', CYAN)}    重试降级：指数退避 + read-only 模式          {c('║', CYAN)}
  {c('╠══════════════════════════════════════════════════════════╣', CYAN)}
  {c('║', CYAN)}  演示覆盖场景                                    {c('║', CYAN)}
  {c('║', CYAN)}    集群健康检查 + 节点管理                       {c('║', CYAN)}
  {c('║', CYAN)}    系统巡检：info / cpu / memory / disk          {c('║', CYAN)}
  {c('║', CYAN)}    网络诊断：dns / http                          {c('║', CYAN)}
  {c('║', CYAN)}    AI 自然语言对话 + 智能诊断                    {c('║', CYAN)}
  {c('║', CYAN)}    链路追踪：全链路操作回溯                      {c('║', CYAN)}
  {c('║', CYAN)}    告警响应：问题定位 + AI 修复方案              {c('║', CYAN)}
  {c('╚══════════════════════════════════════════════════════════╝', CYAN)}
""")

print(f"\n  {c('演示脚本运行完毕。', GREEN)}")
print(f"  {c('交互模式：python cli/gaiops chat / shell', DIM)}")
print()
