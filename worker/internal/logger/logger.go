// Package logger provides structured JSON logging for the Worker.
//
// Every log line is a single JSON object written to stdout, matching the
// gAIOps log schema defined in docs/log-schema.md.
package logger

import (
	"encoding/json"
	"os"
	"sync"
	"time"
)

// Level represents a log severity.
type Level string

const (
	LevelDebug Level = "debug"
	LevelInfo  Level = "info"
	LevelWarn  Level = "warn"
	LevelError Level = "error"
)

// Entry is the structured log record.
type Entry struct {
	Timestamp  string      `json:"timestamp"`
	Level      Level       `json:"level"`
	Module     string      `json:"module"`
	TraceID    string      `json:"trace_id"`
	MsgID      string      `json:"msg_id,omitempty"`
	Action     string      `json:"action,omitempty"`
	Message    string      `json:"message"`
	ErrorCode  string      `json:"error_code,omitempty"`
	Data       interface{} `json:"data,omitempty"`
	DurationMs int64       `json:"duration_ms,omitempty"`
	PID        int         `json:"pid"`
}

// Logger is a simple JSON structured logger.
type Logger struct {
	module string
	mu     sync.Mutex
	enc    *json.Encoder
}

// New creates a Logger that writes JSON to stdout.
func New(module string) *Logger {
	return &Logger{
		module: module,
		enc:    json.NewEncoder(os.Stdout),
	}
}

func (l *Logger) log(level Level, msg string, opts ...Option) {
	e := Entry{
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Level:     level,
		Module:    l.module,
		TraceID:   "no-trace",
		Message:   msg,
		PID:       os.Getpid(),
	}
	for _, opt := range opts {
		opt(&e)
	}
	l.mu.Lock()
	l.enc.Encode(e)
	l.mu.Unlock()
}

// Debug emits a debug-level log line.
func (l *Logger) Debug(msg string, opts ...Option) { l.log(LevelDebug, msg, opts...) }

// Info emits an info-level log line.
func (l *Logger) Info(msg string, opts ...Option) { l.log(LevelInfo, msg, opts...) }

// Warn emits a warn-level log line.
func (l *Logger) Warn(msg string, opts ...Option) { l.log(LevelWarn, msg, opts...) }

// Error emits an error-level log line.
func (l *Logger) Error(msg string, opts ...Option) { l.log(LevelError, msg, opts...) }

// Option configures a log Entry.
type Option func(*Entry)

// WithTraceID sets the trace_id field.
func WithTraceID(traceID string) Option {
	return func(e *Entry) { e.TraceID = traceID }
}

// WithMsgID sets the msg_id field.
func WithMsgID(msgID string) Option {
	return func(e *Entry) { e.MsgID = msgID }
}

// WithAction sets the action field.
func WithAction(action string) Option {
	return func(e *Entry) { e.Action = action }
}

// WithErrorCode sets the error_code field.
func WithErrorCode(code string) Option {
	return func(e *Entry) { e.ErrorCode = code }
}

// WithData sets the data payload.
func WithData(data interface{}) Option {
	return func(e *Entry) { e.Data = data }
}

// WithDurationMs sets the duration in milliseconds.
func WithDurationMs(ms int64) Option {
	return func(e *Entry) { e.DurationMs = ms }
}
