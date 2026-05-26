package tools

import (
	"context"
	"testing"
)

// --- port.go tests ---

func TestExecutePortCheckMissingHost(t *testing.T) {
	_, err := executePortCheck(context.Background(), map[string]interface{}{})
	if err == nil {
		t.Error("expected error for missing host")
	}
}

func TestExecutePortScanNoPorts(t *testing.T) {
	_, err := executePortScan(context.Background(), map[string]interface{}{
		"host": "localhost",
	})
	if err == nil {
		t.Error("expected error for missing ports list")
	}
}

// --- ping.go tests ---

func TestExecutePingMissingTarget(t *testing.T) {
	_, err := executePing(context.Background(), map[string]interface{}{})
	if err == nil {
		t.Error("expected error for missing target")
	}
}

// --- disk.go tests ---

func TestExecuteDiskUsageDefaultPath(t *testing.T) {
	result, err := executeDiskUsage(context.Background(), map[string]interface{}{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if _, ok := result["path"]; !ok {
		t.Error("expected path field")
	}
	if _, ok := result["total_bytes"]; !ok {
		t.Error("expected total_bytes field")
	}
}

// --- http.go tests ---

func TestExecuteHTTPGetNoURL(t *testing.T) {
	_, err := executeHTTPGet(context.Background(), map[string]interface{}{})
	if err == nil {
		t.Error("expected error for missing url")
	}
}

func TestExecuteHTTPGetInvalidScheme(t *testing.T) {
	_, err := executeHTTPGet(context.Background(), map[string]interface{}{
		"url": "ftp://example.com",
	})
	if err == nil {
		t.Error("expected error for invalid scheme")
	}
}

// --- ssl.go tests ---

func TestExecuteSSLCertCheckMissingHostname(t *testing.T) {
	_, err := executeSSLCertCheck(context.Background(), map[string]interface{}{})
	if err == nil {
		t.Error("expected error for missing hostname")
	}
}

// --- service.go tests ---

func TestExecuteServiceStatusNoName(t *testing.T) {
	_, err := executeServiceStatus(context.Background(), map[string]interface{}{})
	if err == nil {
		t.Error("expected error for missing service name")
	}
}

// --- exec.go additional tests ---

func TestContainsShellMetaNoMeta(t *testing.T) {
	if containsShellMeta("hello world") {
		t.Error("expected no shell metacharacters in simple string")
	}
	if containsShellMeta("/usr/bin/systemctl status nginx") {
		t.Error("expected no shell metacharacters in typical command")
	}
}
