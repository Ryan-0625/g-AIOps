#!/usr/bin/env python3
"""
gAIOps 全自动演示脚本
所有操作均通过真实 CLI 工具执行，输出实时截取展示

前置条件：docker compose up -d master worker brain
"""

import subprocess
import sys
import time
import os
import tempfile

if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

os.environ["CLUSTER_TOKEN"] = "dev-token-change"

# ── 输出样式 ────────────────────────────────────────────────────────────────

GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
RESET = "\033[0m"


def c(text, color):
    return f"{color}{text}{RESET}"


def section(title):
    """场景分隔线"""
    print(f"\n  {c('┌' + '─' * 58 + '┐', CYAN)}")
    print(f"  {c('│' + title.center(56) + '│', CYAN)}")
    print(f"  {c('└' + '─' * 58 + '┘', CYAN)}")
    time.sleep(1)


def note(text):
    """简短旁白，作为注释"""
    print(f"\n  {c('# ' + text, DIM)}")
    time.sleep(0.8)


def run_cmd(cmd, wait=4):
    """执行 CLI 命令并截取真实输出"""
    print(f"\n  {c('$ ' + cmd, BOLD)}")
    time.sleep(1)
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, timeout=60,
            encoding='utf-8', errors='replace'
        )
        output = (result.stdout + result.stderr).strip()
        for line in output.split('\n'):
            line = line.strip()
            if line:
                print(f"  {line}")
    except subprocess.TimeoutExpired:
        print(f"  {c('[TIMEOUT]', RED)}")
    print()
    time.sleep(wait)


def run_chat(question, wait=4):
    """通过真实 CLI chat 模式执行对话，截取 Brain 回答"""
    print(f"\n  {c('$ python cli/gaiops chat', BOLD)}")
    time.sleep(0.8)
    print(f"\n  > {question}")
    time.sleep(1)

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.txt') as f:
        f.write(f'{question}\n/exit\n'.encode('utf-8'))
        tmpfile = f.name

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'

    try:
        result = subprocess.run(
            f'python cli/gaiops chat < "{tmpfile}"',
            shell=True, capture_output=True, timeout=60, env=env
        )
        stdout = result.stdout.decode('utf-8')

        # 截取 Brain 回答部分
        lines = stdout.split('\n')
        in_brain = False
        for line in lines:
            stripped = line.rstrip()
            if 'Brain' in stripped and '[' in stripped and ']' in stripped:
                in_brain = True
                print(f"  {stripped}")
                continue
            if in_brain:
                if '─' in stripped and len(stripped) > 10:
                    in_brain = False
                    if stripped.strip():
                        print(f"  {stripped}")
                    continue
                if stripped.strip():
                    print(f"  {stripped}")
    except Exception as e:
        print(f"  [{e}]")
    finally:
        os.unlink(tmpfile)
    time.sleep(wait)


# ═════════════════════════════════════════════════════════════════════════════
# Demo Start
# ═════════════════════════════════════════════════════════════════════════════

os.system('cls' if os.name == 'nt' else 'clear')

print(f"""
  {c('╔══════════════════════════════════════════════════════════╗', CYAN)}
  {c('║', CYAN)}       gAIOps CLI 全自动演示 — 运维场景模拟       {c('║', CYAN)}
  {c('║', CYAN)}    LLM驱动的分布式运维决策系统                     {c('║', CYAN)}
  {c('╚══════════════════════════════════════════════════════════╝', CYAN)}
""")
time.sleep(1.5)

try:
    input(f"  {c('按 Enter 开始演示...', DIM)}")
except (EOFError, KeyboardInterrupt):
    pass

# ═════════════════════════════════════════════════════════════════════════════
# 场景一：日常巡检 —— 检查集群健康状态
# ═════════════════════════════════════════════════════════════════════════════

section("场景一：日常巡检 — 查看集群概况")

note("检查集群和节点状态")
run_cmd("python cli/gaiops health", wait=3)

note("查看 Worker 节点列表")
run_cmd("python cli/gaiops worker list", wait=3)

# ═════════════════════════════════════════════════════════════════════════════
# 场景二：系统巡检 —— 逐项检查 CPU/内存/磁盘/网络
# ═════════════════════════════════════════════════════════════════════════════

section("场景二：系统巡检 — 采集系统指标")

note("系统基础信息")
run_cmd("python cli/gaiops execute system.info --wait", wait=3)

note("CPU 使用率")
run_cmd("python cli/gaiops execute cpu.usage --wait", wait=3)

note("内存使用情况")
run_cmd("python cli/gaiops execute memory.usage --wait", wait=3)

note("磁盘使用率")
run_cmd("python cli/gaiops execute disk.usage --wait", wait=3)

note("DNS 解析测试")
run_cmd("python cli/gaiops execute dns.lookup hostname=baidu.com --wait", wait=3)

note("HTTP 外网连通性")
run_cmd("python cli/gaiops execute http.get url=https://httpbin.org/get --wait", wait=3)

# ═════════════════════════════════════════════════════════════════════════════
# 场景三：AI 自然语言交互 —— 真实 chat 模式
# ═════════════════════════════════════════════════════════════════════════════

section("场景三：AI 自然语言交互 — 智能诊断")

note("通过 chat 模式用自然语言询问系统状态")
run_chat("当前系统状态怎么样", wait=3)

note("追问 CPU 负载指标")
run_chat("检查CPU负载", wait=3)

note("ping 测试网络延迟")
run_chat("ping 百度", wait=4)

# ═════════════════════════════════════════════════════════════════════════════
# 场景四：问题定位 —— 链路追踪展示
# ═════════════════════════════════════════════════════════════════════════════

section("场景四：问题定位 — 链路追踪")

note("回顾以上所有 execute 操作，每一条都包含了 trace_id")
note("trace_id 贯穿 Brain -> Master -> Worker，每一步都可回溯")
note("通过 TraceID 可快速定位问题根因，适用于复杂运维场景")

# ═════════════════════════════════════════════════════════════════════════════
# 场景五：模拟告警 —— 事故响应流程
# ═════════════════════════════════════════════════════════════════════════════

section("场景五：模拟告警响应")

note("模拟磁盘告警，先确认节点状态")
run_cmd("python cli/gaiops status", wait=3)

note("用 AI 快速查看磁盘")
run_chat("检查磁盘使用率", wait=3)

note("生产场景下，Brain 会启动诊断管道：")
note("磁盘分析 -> 定位大文件 -> 评估风险 -> 清理建议，TraceID 全程记录")

# ═════════════════════════════════════════════════════════════════════════════
# 场景六：总结
# ═════════════════════════════════════════════════════════════════════════════

section("场景六：演示总结")

print(f"""
  {c('╔══════════════════════════════════════════════════════════╗', CYAN)}
  {c('║', CYAN)}                  演示总结                        {c('║', CYAN)}
  {c('╠══════════════════════════════════════════════════════════╣', CYAN)}
  {c('║', CYAN)}  系统架构                                        {c('║', CYAN)}
  {c('║', CYAN)}    单主机 Master + 远程 Worker 节点拓扑          {c('║', CYAN)}
  {c('║', CYAN)}    Brain LLM 推理层解析自然语言指令              {c('║', CYAN)}
  {c('╠══════════════════════════════════════════════════════════╣', CYAN)}
  {c('║', CYAN)}  核心能力                                        {c('║', CYAN)}
  {c('║', CYAN)}    意图路由：快速通道 / 多步推理管道             {c('║', CYAN)}
  {c('║', CYAN)}    状态机：Analyst->Planner->Execute->Reflector  {c('║', CYAN)}
  {c('║', CYAN)}    全链路追踪：TraceID 贯穿三层                  {c('║', CYAN)}
  {c('║', CYAN)}    重试降级：指数退避 + read-only 模式          {c('║', CYAN)}
  {c('╠══════════════════════════════════════════════════════════╣', CYAN)}
  {c('║', CYAN)}  覆盖场景                                        {c('║', CYAN)}
  {c('║', CYAN)}    健康检查 + 节点管理                           {c('║', CYAN)}
  {c('║', CYAN)}    系统巡检：info/cpu/memory/disk                {c('║', CYAN)}
  {c('║', CYAN)}    网络诊断：dns/http                            {c('║', CYAN)}
  {c('║', CYAN)}    AI 自然语言对话                              {c('║', CYAN)}
  {c('║', CYAN)}    链路追踪 + 告警响应                          {c('║', CYAN)}
  {c('╚══════════════════════════════════════════════════════════╝', CYAN)}
""")

print(f"\n  {c('演示结束。', GREEN)}")
print(f"  {c('交互模式：python cli/gaiops chat / shell', DIM)}")
print()
