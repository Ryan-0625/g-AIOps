// Package executor provides tool execution with concurrency control, timeout,
// panic recovery, and progress streaming for long-running tools.
package executor

import (
	"bufio"
	"encoding/json"
	
	"io"
	"strings"
	"sync"
)

// 鈹€鈹€ ProgressReporter 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

// ProgressReporter allows long-running tools to report execution progress.
// Tools output progress JSON lines to stderr in the format:
//
//	{"progress": 45, "message": "姝ｅ湪娓呯悊 /tmp 缂撳瓨..."}
type ProgressReporter struct {
	mu       sync.Mutex
	callback func(percent int, message string)
}

// NewProgressReporter creates a reporter that invokes callback on each
// progress update parsed from the reader.
func NewProgressReporter(callback func(percent int, message string)) *ProgressReporter {
	return &ProgressReporter{callback: callback}
}

// StartReader reads from r line-by-line, looking for progress JSON.
// Run in a goroutine. Returns when r is exhausted or closed.
func (pr *ProgressReporter) StartReader(r io.Reader) {
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if !strings.HasPrefix(line, "{") {
			continue
		}
		var entry struct {
			Progress int    `json:"progress"`
			Message  string `json:"message"`
		}
		if err := json.Unmarshal([]byte(line), &entry); err != nil {
			continue
		}
		if entry.Progress > 0 && entry.Message != "" {
			pr.mu.Lock()
			if pr.callback != nil {
				pr.callback(entry.Progress, entry.Message)
			}
			pr.mu.Unlock()
		}
	}
}

// ReportProgress directly reports a progress update (used by the framework
// when parsing tool progress from stderr).
func (pr *ProgressReporter) ReportProgress(percent int, message string) {
	pr.mu.Lock()
	defer pr.mu.Unlock()
	if pr.callback != nil {
		pr.callback(percent, message)
	}
}

// 鈹€鈹€ ProgressEvent 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

// ProgressEvent is a structured progress event for long-running tasks.
type ProgressEvent struct {
	Percent int    `json:"percent"`
	Message string `json:"message"`
}

// FormatProgressEvent returns a JSON string suitable for writing to stderr.
func FormatProgressEvent(percent int, message string) string {
	event := ProgressEvent{Percent: percent, Message: message}
	data, _ := json.Marshal(event)
	return string(data)
}


