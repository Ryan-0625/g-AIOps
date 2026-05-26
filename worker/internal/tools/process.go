package tools

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "process.list",
		Timeout:      5 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeProcessList,
	})
	registry.Global.Register(registry.Tool{
		Action:       "process.kill",
		Timeout:      10 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "dangerous",
		Execute:      executeProcessKill,
	})
}

func executeProcessList(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	name, _ := params["name"].(string)

	args := []string{"axo", "pid,ppid,user,%cpu,%mem,rss,etime,command"}
	cmd := exec.CommandContext(ctx, "ps", args...)
	output, err := cmd.Output()
	if err != nil {
		return nil, executor.NewErr("PROCESS_LIST_FAILED",
			fmt.Sprintf("failed to list processes: %v", err))
	}

	lines := strings.Split(string(output), "\n")
	var processes []map[string]interface{}
	for i, line := range lines {
		if i == 0 || strings.TrimSpace(line) == "" {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 8 {
			continue
		}

		proc := map[string]interface{}{
			"pid":     safeAtoi(fields[0]),
			"ppid":    safeAtoi(fields[1]),
			"user":    fields[2],
			"cpu_pct": fields[3],
			"mem_pct": fields[4],
			"rss_kb":  safeAtoi(fields[5]),
			"elapsed": fields[6],
			"command": strings.Join(fields[7:], " "),
		}

		if name != "" && !strings.Contains(proc["command"].(string), name) {
			continue
		}
		processes = append(processes, proc)
	}

	return map[string]interface{}{
		"total":     len(processes),
		"processes": processes,
		"filter":    name,
	}, nil
}

func executeProcessKill(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	pidRaw := params["pid"]
	var pid int
	switch v := pidRaw.(type) {
	case int:
		pid = v
	case float64:
		pid = int(v)
	default:
		return nil, executor.NewErr("INVALID_PARAMS", "pid is required (integer)")
	}

	if pid <= 0 {
		return nil, executor.NewErr("INVALID_PARAMS", "pid must be > 0")
	}

	signal := "SIGTERM"
	if s, ok := params["signal"].(string); ok && s != "" {
		signal = s
	}

	proc, err := os.FindProcess(pid)
	if err != nil {
		return nil, executor.NewErr("PROCESS_NOT_FOUND",
			fmt.Sprintf("process %d not found: %v", pid, err))
	}

	sig := parseSignal(signal)
	if sig != nil {
		if err := proc.Signal(sig); err != nil {
			return nil, executor.NewErr("KILL_FAILED",
				fmt.Sprintf("failed to signal process %d: %v", pid, err))
		}
	}

	return map[string]interface{}{
		"pid":    pid,
		"signal": signal,
		"status": "signaled",
	}, nil
}

func safeAtoi(s string) int {
	v, err := strconv.Atoi(strings.TrimSpace(s))
	if err != nil {
		return 0
	}
	return v
}

func parseSignal(s string) os.Signal {
	switch strings.ToUpper(s) {
	case "SIGTERM", "TERM", "15":
		return os.Interrupt
	case "SIGKILL", "KILL", "9":
		return os.Kill
	case "SIGHUP", "HUP", "1":
		return os.Interrupt
	default:
		return os.Interrupt
	}
}

