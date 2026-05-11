package tools

import (
	"context"
	"fmt"
	"os/exec"
	"runtime"
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
		RiskLevel:    "write",
		Execute:      executeProcessKill,
	})
}

func executeProcessList(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	var cmd *exec.Cmd
	if runtime.GOOS == "windows" {
		cmd = exec.CommandContext(ctx, "tasklist", "/FO", "CSV", "/NH")
	} else {
		cmd = exec.CommandContext(ctx, "ps", "-eo", "pid,ppid,user,pcpu,rss,comm", "--no-header")
	}

	out, err := cmd.Output()
	if err != nil {
		return nil, executor.NewErr("PROCESS_LIST_FAILED", fmt.Sprintf("failed to list processes: %v", err))
	}

	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	processes := make([]map[string]interface{}, 0, len(lines))
	count := 0

	for _, line := range lines {
		if count >= 500 {
			break
		}
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}

		if runtime.GOOS == "windows" {
			// tasklist CSV: "image","pid","session","session#","mem"
			parts := strings.Split(line, ",")
			if len(parts) >= 2 {
				pidStr := strings.Trim(parts[1], "\"")
				pid, _ := strconv.Atoi(pidStr)
				processes = append(processes, map[string]interface{}{
					"pid":   pid,
					"name":  strings.Trim(parts[0], "\""),
					"mem":   strings.Trim(parts[4], "\""),
				})
				count++
			}
		} else {
			pid, _ := strconv.Atoi(fields[0])
			rss, _ := strconv.Atoi(fields[4])
			processes = append(processes, map[string]interface{}{
				"pid":    pid,
				"ppid":   fields[1],
				"user":   fields[2],
				"cpu_pct": fields[3],
				"rss_kb":  rss,
				"command": strings.Join(fields[5:], " "),
			})
			count++
		}
	}

	return map[string]interface{}{
		"processes": processes,
		"count":     len(processes),
	}, nil
}

func executeProcessKill(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	pidRaw, ok := params["pid"]
	if !ok {
		return nil, executor.NewErr("INVALID_PARAMS", "pid is required")
	}

	var pid int
	switch v := pidRaw.(type) {
	case float64:
		pid = int(v)
	case int:
		pid = v
	case string:
		p, err := strconv.Atoi(v)
		if err != nil {
			return nil, executor.NewErr("INVALID_PARAMS", fmt.Sprintf("invalid pid: %s", v))
		}
		pid = p
	default:
		return nil, executor.NewErr("INVALID_PARAMS", "pid must be a number")
	}

	signal := "TERM"
	if s, ok := params["signal"].(string); ok {
		signal = s
	}

	var cmd *exec.Cmd
	if runtime.GOOS == "windows" {
		flag := "/T" // kill process tree
		if signal == "KILL" || signal == "9" {
			flag = "/F /T"
		}
		cmd = exec.CommandContext(ctx, "taskkill", "/PID", fmt.Sprintf("%d", pid), flag)
	} else {
		sigFlag := fmt.Sprintf("-%s", signal)
		cmd = exec.CommandContext(ctx, "kill", sigFlag, fmt.Sprintf("%d", pid))
	}

	if err := cmd.Run(); err != nil {
		return nil, executor.NewErr("KILL_FAILED", fmt.Sprintf("failed to kill pid %d: %v", pid, err))
	}

	return map[string]interface{}{
		"pid":    pid,
		"signal": signal,
		"killed": true,
	}, nil
}
