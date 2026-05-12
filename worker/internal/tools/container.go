package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
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
