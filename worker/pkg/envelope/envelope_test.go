package envelope_test

import (
	"testing"

	"github.com/gaiops/worker/pkg/envelope"
)

// Override time/UUID helpers for deterministic tests.
func init() {
	envelope.SetNow(func() int64 { return 1715000000 })
	envelope.SetNewUUID(func() string { return "00000000-0000-0000-0000-000000000000" })
}

func TestNewRequestDefaults(t *testing.T) {
	e := envelope.NewRequest(
		"a1b2c3d4-e5f6-7890-abcd-ef1234567890",
		"00000000-0000-0000-0000-000000000001",
		"ping.icmp",
		map[string]interface{}{"target": "localhost"},
	)

	if e.ProtoVersion != "1.1" {
		t.Errorf("ProtoVersion = %q, want 1.1 (v2.0 upgrade)", e.ProtoVersion)
	}
	if e.MsgType != envelope.MsgRequest {
		t.Errorf("MsgType = %q, want request", e.MsgType)
	}
	if e.Source != envelope.RoleMaster {
		t.Errorf("Source = %q, want master", e.Source)
	}
	if e.Target != envelope.RoleWorker {
		t.Errorf("Target = %q, want worker", e.Target)
	}
	if e.Priority != envelope.PriorityNormal {
		t.Errorf("Priority = %d, want 0", e.Priority)
	}
	if e.TTLSeconds != 30 {
		t.Errorf("TTLSeconds = %d, want 30", e.TTLSeconds)
	}
	if e.Payload.Status != envelope.StatusPending {
		t.Errorf("Status = %q, want pending", e.Payload.Status)
	}
}

func TestNewRequestOptions(t *testing.T) {
	e := envelope.NewRequest(
		"a1b2c3d4-e5f6-7890-abcd-ef1234567890",
		"00000000-0000-0000-0000-000000000001",
		"disk.usage",
		nil,
		envelope.WithTargetID("worker-1"),
		envelope.WithPriority(envelope.PriorityEmergency),
		envelope.WithTTL(60),
	)

	if e.TargetID != "worker-1" {
		t.Errorf("TargetID = %q, want worker-1", e.TargetID)
	}
	if e.Priority != envelope.PriorityEmergency {
		t.Errorf("Priority = %d, want 2", e.Priority)
	}
	if e.TTLSeconds != 60 {
		t.Errorf("TTLSeconds = %d, want 60", e.TTLSeconds)
	}
}

func TestNewResponse(t *testing.T) {
	req := envelope.NewRequest(
		"trace-1", "msg-req-1", "service.status",
		map[string]interface{}{"name": "nginx"},
	)

	resp := envelope.NewResponse(req, envelope.StatusSuccess,
		map[string]interface{}{"status": "running"}, nil)

	if resp.TraceID != req.TraceID {
		t.Errorf("TraceID mismatch")
	}
	if resp.CorrelationID != req.MsgID {
		t.Errorf("CorrelationID = %q, want %q", resp.CorrelationID, req.MsgID)
	}
	if resp.Source != envelope.RoleWorker {
		t.Errorf("Source = %q, want worker", resp.Source)
	}
	if resp.Target != envelope.RoleMaster {
		t.Errorf("Target = %q, want master", resp.Target)
	}
	if resp.Payload.Status != envelope.StatusSuccess {
		t.Errorf("Status = %q, want success", resp.Payload.Status)
	}
}

func TestNewResponseWithError(t *testing.T) {
	req := envelope.NewRequest("trace-1", "msg-req-1", "exec.run", nil)
	resp := envelope.NewResponse(req, envelope.StatusFailure, nil,
		&envelope.ErrorInfo{
			Code:    "COMMAND_NOT_ALLOWED",
			Message: "command not in whitelist",
			Raw:     "/bin/rm: not allowed",
		})

	if resp.Payload.Status != envelope.StatusFailure {
		t.Errorf("Status = %q, want failure", resp.Payload.Status)
	}
	if resp.Payload.Error == nil {
		t.Fatal("Error should not be nil")
	}
	if resp.Payload.Error.Code != "COMMAND_NOT_ALLOWED" {
		t.Errorf("Error.Code = %q", resp.Payload.Error.Code)
	}
}

func TestValidateValid(t *testing.T) {
	e := envelope.NewRequest(
		"a1b2c3d4-e5f6-7890-abcd-ef1234567890",
		"00000000-0000-0000-0000-000000000001",
		"ping.icmp",
		map[string]interface{}{"target": "localhost"},
	)

	errs := e.Validate()
	if len(errs) > 0 {
		t.Errorf("unexpected validation errors: %v", errs)
	}
}

func TestValidateMissingFields(t *testing.T) {
	e := &envelope.Envelope{Payload: envelope.Payload{}}
	errs := e.Validate()
	if len(errs) == 0 {
		t.Fatal("expected validation errors, got none")
	}
}

func TestValidateFailureRequiresError(t *testing.T) {
	e := envelope.NewRequest(
		"a1b2c3d4-e5f6-7890-abcd-ef1234567890",
		"00000000-0000-0000-0000-000000000001",
		"service.status", nil,
	)
	e.Payload.Status = envelope.StatusFailure

	errs := e.Validate()
	found := false
	for _, err := range errs {
		if err == "payload.error is required when status=failure" {
			found = true
		}
	}
	if !found {
		t.Errorf("expected error about missing error field, got: %v", errs)
	}
}

func TestMarshalUnmarshalRoundtrip(t *testing.T) {
	original := envelope.NewRequest(
		"a1b2c3d4-e5f6-7890-abcd-ef1234567890",
		"00000000-0000-0000-0000-000000000001",
		"disk.usage",
		map[string]interface{}{"path": "/"},
		envelope.WithPriority(envelope.PriorityImportant),
		envelope.WithTTL(45),
	)

	data, err := original.Marshal()
	if err != nil {
		t.Fatalf("Marshal: %v", err)
	}

	parsed, err := envelope.Unmarshal(data)
	if err != nil {
		t.Fatalf("Unmarshal: %v", err)
	}

	if parsed.TraceID != original.TraceID {
		t.Errorf("TraceID mismatch after roundtrip")
	}
	if parsed.MsgType != original.MsgType {
		t.Errorf("MsgType mismatch after roundtrip")
	}
	if parsed.Priority != original.Priority {
		t.Errorf("Priority mismatch after roundtrip")
	}
	if parsed.Payload.Action != original.Payload.Action {
		t.Errorf("Action mismatch after roundtrip")
	}
	path, _ := parsed.Payload.Params["path"].(string)
	if path != "/" {
		t.Errorf("Params.path = %q, want /", path)
	}
}

func TestUnmarshalInvalidJSON(t *testing.T) {
	_, err := envelope.Unmarshal([]byte("{bad json"))
	if err == nil {
		t.Fatal("expected unmarshal error, got nil")
	}
}

func TestMsgTypeValid(t *testing.T) {
	cases := []struct {
		mt    envelope.MsgType
		valid bool
	}{
		{envelope.MsgRequest, true},
		{envelope.MsgResponse, true},
		{envelope.MsgEvent, true},
		{envelope.MsgAck, true},
		{envelope.MsgHeartbeat, true},
		{"invalid", false},
		{"", false},
	}

	for _, c := range cases {
		if got := c.mt.Valid(); got != c.valid {
			t.Errorf("MsgType(%q).Valid() = %v, want %v", c.mt, got, c.valid)
		}
	}
}

func TestStatusValid(t *testing.T) {
	if !envelope.StatusSuccess.Valid() {
		t.Error("StatusSuccess should be valid")
	}
	if envelope.Status("bogus").Valid() {
		t.Error("bogus status should be invalid")
	}
}

func TestPriorityValid(t *testing.T) {
	if !envelope.PriorityNormal.Valid() {
		t.Error("PriorityNormal should be valid")
	}
	if envelope.Priority(99).Valid() {
		t.Error("priority 99 should be invalid")
	}
}

// Test that a fully populated envelope round-trips through JSON correctly,
// including nested objects like Progress and ErrorInfo.
// ── v1.1 tests ─────────────────────────────────────────────────────────────

func TestMsgTypeV11Valid(t *testing.T) {
	cases := []struct {
		mt    envelope.MsgType
		valid bool
	}{
		{envelope.MsgToolDeploy, true},
		{envelope.MsgToolCode, true},
		{envelope.MsgToolStatus, true},
	}
	for _, c := range cases {
		if got := c.mt.Valid(); got != c.valid {
			t.Errorf("MsgType(%q).Valid() = %v, want %v", c.mt, got, c.valid)
		}
	}
}

func TestMsgTypeIsV1(t *testing.T) {
	if envelope.MsgToolDeploy.IsV1() {
		t.Error("MsgToolDeploy should not be v1 compatible")
	}
	if !envelope.MsgRequest.IsV1() {
		t.Error("MsgRequest should be v1 compatible")
	}
	if !envelope.MsgHeartbeat.IsV1() {
		t.Error("MsgHeartbeat should be v1 compatible")
	}
}

func TestValidateV11ToolDeployMissingFields(t *testing.T) {
	e := &envelope.Envelope{
		ProtoVersion: "1.1",
		TraceID:      "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
		MsgID:        "00000000-0000-0000-0000-000000000001",
		MsgType:    