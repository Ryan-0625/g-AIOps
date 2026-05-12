package tools

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "http.get",
		Timeout:      30 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeHTTPGet,
	})
	registry.Global.Register(registry.Tool{
		Action:       "http.post",
		Timeout:      30 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "dangerous",
		Execute:      executeHTTPPost,
	})
}

func executeHTTPGet(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	return doHTTP(ctx, params, http.MethodGet)
}

func executeHTTPPost(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	return doHTTP(ctx, params, http.MethodPost)
}

func doHTTP(ctx context.Context, params map[string]interface{}, method string) (map[string]interface{}, error) {
	rawURL, _ := params["url"].(string)
	if rawURL == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "url is required")
	}

	// Validate URL.
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return nil, executor.NewErr("INVALID_PARAMS", fmt.Sprintf("invalid url: %v", err))
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return nil, executor.NewErr("INVALID_PARAMS", "scheme must be http or https")
	}

	// Block private/internal IPs.
	if err := blockPrivateTarget(parsed.Host); err != nil {
		return nil, executor.NewErr("BLOCKED_TARGET", err.Error())
	}

	// Timeout from params.
	timeout := 30
	if t, ok := params["timeout_seconds"].(int); ok && t > 0 && t <= 60 {
		timeout = t
	}
	requestCtx, cancel := context.WithTimeout(ctx, time.Duration(timeout)*time.Second)
	defer cancel()

	// Build request.
	var bodyReader io.Reader
	if method == http.MethodPost {
		bodyStr, _ := params["body"].(string)
		if len(bodyStr) > 1_048_576 { // 1MB max
			return nil, executor.NewErr("BODY_TOO_LARGE", "request body exceeds 1MB limit")
		}
		bodyReader = strings.NewReader(bodyStr)
	}

	req, err := http.NewRequestWithContext(requestCtx, method, rawURL, bodyReader)
	if err != nil {
		return nil, executor.NewErr("REQUEST_FAILED", fmt.Sprintf("create request: %v", err))
	}

	// Custom headers.
	if headers, ok := params["headers"].(map[string]interface{}); ok {
		for k, v := range headers {
			req.Header.Set(k, fmt.Sprintf("%v", v))
		}
	}
	if method == http.MethodPost {
		if ct, ok := params["content_type"].(string); ok && ct != "" {
			req.Header.Set("Content-Type", ct)
		}
	}

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, executor.NewErr("HTTP_FAILED", fmt.Sprintf("%v", err))
	}
	defer resp.Body.Close()

	// Read response body (max 64KB for preview).
	bodyBytes, _ := io.ReadAll(io.LimitReader(resp.Body, 65536))
	bodyStr := string(bodyBytes)
	truncated := false
	bodySize := int64(len(bodyBytes))

	// Check if there's more.
	if resp.ContentLength > bodySize || resp.ContentLength == -1 {
		// Try to peek if more data exists.
		var one [1]byte
		if _, err := resp.Body.Read(one[:]); err == nil {
			truncated = true
		}
	}

	// Collect response headers.
	respHeaders := make(map[string]string)
	for k, v := range resp.Header {
		if len(v) > 0 {
			respHeaders[k] = v[0]
		}
	}

	result := map[string]interface{}{
		"status_code": resp.StatusCode,
		"headers":     respHeaders,
		"body_size":   bodySize,
		"body_preview": truncateString(bodyStr, 4096),
	}
	if truncated || bodySize > 4096 {
		result["truncated"] = true
	}
	return result, nil
}

// blockPrivateTarget rejects requests to private / internal network targets.
func blockPrivateTarget(host string) error {
	// Strip port.
	h := host
	if strings.Contains(host, ":") {
		var err error
		h, _, err = net.SplitHostPort(host)
		if err != nil {
			return fmt.Errorf("invalid host: %v", err)
		}
	}

	// Block localhost / 127.0.0.1 by name.
	if h == "localhost" || h == "127.0.0.1" || h == "::1" {
		return fmt.Errorf("target is a loopback address: %s", host)
	}

	// Try IP resolution.
	ip := net.ParseIP(h)
	if ip != nil {
		if isPrivateIP(ip) {
			return fmt.Errorf("target is a private IP: %s", host)
		}
		return nil
	}

	// Resolve hostname and check all IPs.
	addrs, err := net.DefaultResolver.LookupHost(context.Background(), h)
	if err != nil {
		return nil // Allow if resolution fails (target may be unreachable anyway).
	}
	for _, a := range addrs {
		ip := net.ParseIP(a)
		if ip != nil && isPrivateIP(ip) {
			return fmt.Errorf("target resolves to a private IP: %s (%s)", host, a)
		}
	}
	return nil
}

func isPrivateIP(ip net.IP) bool {
	if ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsPrivate() {
		return true
	}
	return false
}

func truncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen]
}
