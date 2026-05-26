//go:build !linux

package dynamic

import (
    "context"
)

type SandboxExecutor struct{}

func NewSandboxExecutor(dataDir string) *SandboxExecutor {
    return &SandboxExecutor{}
}

func (s *SandboxExecutor) Execute(ctx context.Context, code string, lang string, params map[string]interface{}) (map[string]interface{}, error) {
    return map[string]interface{}{"error": "sandbox not supported"}, nil
}
