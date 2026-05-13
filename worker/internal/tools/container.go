package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "container.list",
		Timeout:      10 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeContainerList,
	})
	registry.Global.Register(registry.Tool{
		Action:       "container.logs",
		Timeout:      15 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeContainerLogs,
	})
}

// dockerContainer represents a slim Docker container from the API.
type dockerContainer struct {
	ID    string `json:"Id"`
	Names []string `json:"Names"`
	Image string `json:"Image"`
	State string `json:"State"`
	Status string `json:"Status"`
	Ports  []dockerPort `json:"Ports"`
	Created int64 `json:"Created"`
}

type dockerPort struct {
	PrivatePort int `json:"PrivatePort"`
	PublicPort  int `json:"PublicPort"`
	Type        string `json:"Type"`
}

func executeContainerList(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	all := false
	if a, ok := params["all"].(bool); ok {
		all = a
	}

	// Docker API via Unix socket.
	containers, err := queryDockerAPI(ctx, all)
	if err != nil {
		return nil, executor.NewErr("DOCKER_FAILED", fmt.Sprintf("cannot list containers: %v", err))
	}

	results := make([]map[string]interface{}, 0, len(containers))
	for _, c := range containers {
		name := ""
		if len(c.Names) > 0 {
			name = c.Names[0]
			// Docker returns names with leading "/".
			if len(name) > 0 && name[0] == '/' {
				name = name[1:]
			}
		}

		ports := make([]string, 0, len(c.Ports))
		for _, p := range c.Ports {
			if p.PublicPort > 0 {
				ports = append(ports, fmt.Sprintf("%d:%d/%s", p.PublicPort, p.PrivatePort, p.Type))
			} else {
				ports = append(ports, fmt.Sprintf("%d/%s", p.PrivatePort, p.Type))
			}
		}

		results = append(results, map[string]interface{}{
			"id":      c.ID[:12], // short ID
			"name":    name,
			"image":   c.Image,
			"status":  c.Status,
			"state":   c.State,
			"ports":   ports,
			"created": c.Created,
		})
	}

	return map[string]interface{}{
		"containers": results,
		"count":      len(results),
	}, nil
}

func executeContainerLogs(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	containerID, _ := params["container_id"].(string)
	if containerID == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "container_id is required")
	}

	tail, _ := params["tail"].(int)
	if tail <= 0 || tail > 500 {
		tail = 50
	}

	logs, err := queryDockerLogs(ctx, containerID, tail)
	if err != nil {
		return nil, executor.NewErr("DOCKER_FAILED", fmt.Sprintf("cannot get container logs: %v", err))
	}

	return map[string]interface{}{
		"container_id": containerID,
		"logs":         logs,
		"line_count":   len(logs),
	}, nil
}

func queryDockerLogs(ctx context.Context, containerID string, tail int) ([]string, error) {
	socketPath := "/var/run/docker.sock"

	client := http.Client{
		Transport: &http.Transport{
			DialContext: func(_ context.Context, _, _ string) (net.Conn, error) {
				return net.Dial("unix", socketPath)
			},
		},
		Timeout: 15 * time.Second,
	}

	urlPath := fmt.Sprintf("/containers/%s/logs?stdout=true&stderr=true&tail=%d", containerID, tail)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, "http://unix"+urlPath, nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("docker API call failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return nil, fmt.Errorf("docker API returned %d: %s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 65536))
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	// Docker log stream uses 8-byte header per line, strip them.
	lines := []string{}
	for i := 0; i < len(body); {
		if i+8 >= len(body) {
			break
		}
		// Skip 8-byte Docker stream header.
		size := int(body[i+7]) | int(body[i+6])<<8 | int(body[i+5])<<16 | int(body[i+4])<<24
		i += 8
		if i+size > len(body) {
			size = len(body) - i
		}
		lines = append(lines, strings.TrimRight(string(body[i:i+size]), "\n\r"))
		i += size
	}

	// Fallback if header parsing yielded nothing.
	if len(lines) == 0 && len(body) > 0 {
		lines = strings.Split(strings.TrimRight(string(body), "\n"), "\n")
	}

	return lines, nil
}

func queryDockerAPI(ctx context.Context, all bool) ([]dockerContainer, error) {
	// Connect to Docker daemon Unix socket.
	// The socket path can be overridden via DOCKER_HOST env, default /var/run/docker.sock.
	socketPath := "/var/run/docker.sock"

	dialer := net.Dialer{}
	conn, err := dialer.DialContext(ctx, "unix", socketPath)
	if err != nil {
		return nil, fmt.Errorf("cannot connect to Docker socket: %w", err)
	}
	defer conn.Close()

	client := http.Client{
		Transport: &http.Transport{
			DialContext: func(_ context.Context, _, _ string) (net.Conn, error) {
				return net.Dial("unix", socketPath)
			},
		},
		Timeout: 10 * time.Second,
	}

	urlPath := "/containers/json?all=false"
	if all {
		urlPath = "/containers/json?all=true"
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, "http://unix"+urlPath, nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("docker API call failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return nil, fmt.Errorf("docker API returned %d: %s", resp.StatusCode, string(body))
	}

	var containers []dockerContainer
	if err := json.NewDecoder(resp.Body).Decode(&containers); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	return containers, nil
}
