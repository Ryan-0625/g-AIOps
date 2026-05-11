// Package envelope defines the gAIOps Envelope Protocol v1.
//
// Every cross-layer message (Brain↔Master↔Worker) is wrapped in an Envelope.
// The JSON Schema lives at proto/envelope.schema.json; this file is the Go
// representation. Keep both in sync when adding fields.
package envelope

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/google/uuid"
)

// --- Message types ---

type MsgType string

const (
	MsgRequest   MsgType = "request"
	MsgResponse  MsgType = "response"
	MsgEvent     MsgType = "event"
	MsgAck       MsgType = "ack"
	MsgHeartbeat MsgType = "heartbeat"
)

func (t MsgType) Valid() bool {
	switch t {
	case MsgRequest, MsgResponse, MsgEvent, MsgAck, MsgHeartbeat:
		return true
	}
	return false
}

// --- Roles ---

type Role string

const (
	RoleBrain   Role = "brain"
	RoleMaster  Role = "master"
	RoleWorker  Role = "worker"
	RoleBroadcast Role = "broadcast"
)

func (r Role) Valid() bool {
	switch r {
	case RoleBrain, RoleMaster, RoleWorker, RoleBroadcast:
		return true
	}
	return false
}

// --- Status ---

type Status string

const (
	StatusSuccess   Status = "success"
	StatusFailure   Status = "failure"
	StatusPending   Status = "pending"
	StatusCancelled Status = "cancelled"
)

func (s Status) Valid() bool {
	switch s {
	case StatusSuccess, StatusFailure, StatusPending, StatusCancelled:
		return true
	}
	return false
}

// --- Priority ---

type Priority int

const (
	PriorityNormal   Priority = 0
	PriorityImportant Priority = 1
	PriorityEmergency Priority = 2
)

func (p Priority) Valid() bool {
	return p >= 0 && p <= 2
}

// --- Core types ---

type Progress struct {
	Percent int    `json:"percent"`
	Message string `json:"message"`
}

func (p *Progress) Valid() bool {
	return p != nil && p.Percent >= 0 && p.Percent <= 100 && len(p.Message) <= 200
}

type ErrorInfo struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Raw     string `json:"raw,omitempty"`
}

func (e *ErrorInfo) Valid() bool {
	return e != nil && e.Code != "" && e.Message != ""
}

type Payload struct {
	Action      string                 `json:"action"`
	Params      map[string]interface{} `json:"params,omitempty"`
	Status      Status                 `json:"status"`
	Data        map[string]interface{} `json:"data,omitempty"`
	Truncated   bool                   `json:"truncated,omitempty"`
	TruncatedAt int64                  `json:"truncated_at,omitempty"`
	Progress    *Progress              `json:"progress,omitempty"`
	Error       *ErrorInfo             `json:"error,omitempty"`
}

// Envelope is the top-level wire format for all gAIOps messages.
type Envelope struct {
	ProtoVersion  string            `json:"proto_version"`
	TraceID       string            `json:"trace_id"`
	MsgID         string            `json:"msg_id"`
	MsgType       MsgType           `json:"msg_type"`
	Timestamp     int64             `json:"timestamp"`
	Source        Role              `json:"source"`
	SourceID      string            `json:"source_id,omitempty"`
	Target        Role              `json:"target"`
	TargetID      string            `json:"target_id,omitempty"`
	CorrelationID string            `json:"correlation_id,omitempty"`
	Priority      Priority          `json:"priority,omitempty"`
	TTLSeconds    int               `json:"ttl_seconds,omitempty"`
	Payload       Payload           `json:"payload"`
}

// --- Validation ---

var (
	uuidRe   = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
	versionRe = regexp.MustCompile(`^\d+\.\d+$`)
)

func isValidUUID(s string) bool {
	return s == "" || uuidRe.MatchString(s)
}

// Validate checks all required fields and constraints.
// Returns a list of problems; empty slice means valid.
func (e *Envelope) Validate() []string {
	var errs []string
	add := func(msg string) { errs = append(errs, msg) }

	if !versionRe.MatchString(e.ProtoVersion) {
		add("proto_version must match semver (e.g. 1.0)")
	}
	if !uuidRe.MatchString(e.TraceID) {
		add("trace_id must be a valid UUID")
	}
	if !uuidRe.MatchString(e.MsgID) {
		add("msg_id must be a valid UUID")
	}
	if !e.MsgType.Valid() {
		add(fmt.Sprintf("invalid msg_type: %s", e.MsgType))
	}
	if e.Timestamp < 1000000000 {
		add("timestamp looks invalid (before 2001)")
	}
	if !e.Source.Valid() {
		add(fmt.Sprintf("invalid source: %s", e.Source))
	}
	if e.Target != RoleBroadcast && !e.Target.Valid() {
		add(fmt.Sprintf("invalid target: %s", e.Target))
	}
	if !isValidUUID(e.CorrelationID) && e.CorrelationID != "" {
		add("correlation_id must be a valid UUID or empty")
	}
	if !e.Priority.Valid() {
		add("priority must be 0, 1, or 2")
	}
	if e.TTLSeconds < 1 || e.TTLSeconds > 300 {
		add("ttl_seconds must be between 1 and 300")
	}

	// Payload
	if e.Payload.Action == "" {
		add("payload.action is required")
	} else if !strings.Contains(e.Payload.Action, ".") {
		add("payload.action must be namespace.format (e.g. ping.icmp)")
	}
	if !e.Payload.Status.Valid() {
		add(fmt.Sprintf("invalid payload.status: %s", e.Payload.Status))
	}
	if e.Payload.Status == StatusFailure && e.Payload.Error == nil {
		add("payload.error is required when status=failure")
	}
	if e.Payload.Status == StatusFailure && e.Payload.Error != nil && !e.Payload.Error.Valid() {
		add("payload.error.code and message are required")
	}
	if e.Payload.Progress != nil && !e.Payload.Progress.Valid() {
		add("payload.progress.percent must be 0-100")
	}
	if e.Payload.Truncated && e.Payload.TruncatedAt <= 0 {
		add("truncated_at must be >0 when truncated=true")
	}

	return errs
}

// --- Serialisation helpers ---

func (e *Envelope) Marshal() ([]byte, error) {
	return json.Marshal(e)
}

func Unmarshal(data []byte) (*Envelope, error) {
	var e Envelope
	if err := json.Unmarshal(data, &e); err != nil {
		return nil, fmt.Errorf("envelope unmarshal: %w", err)
	}
	return &e, nil
}

// MustMarshal panics on error — for use in tests and hot paths where the
// caller is certain the envelope is valid.
func MustMarshal(e *Envelope) []byte {
	b, err := e.Marshal()
	if err != nil {
		panic(fmt.Sprintf("envelope marshal: %v", err))
	}
	return b
}

// --- Constructors ---

// NewRequest creates a request envelope targeting a worker.
func NewRequest(traceID, msgID, action string, params map[string]interface{}, opts ...RequestOption) *Envelope {
	e := &Envelope{
		ProtoVersion: "1.0",
		TraceID:      traceID,
		MsgID:        msgID,
		MsgType:      MsgRequest,
		Timestamp:    now(),
		Source:       RoleMaster,
		Target:       RoleWorker,
		TargetID:     "*",
		Priority:     PriorityNormal,
		TTLSeconds:   30,
		Payload: Payload{
			Action: action,
			Params: params,
			Status: StatusPending,
		},
	}
	for _, opt := range opts {
		opt(e)
	}
	return e
}

type RequestOption func(*Envelope)

func WithTargetID(id string) RequestOption        { return func(e *Envelope) { e.TargetID = id } }
func WithPriority(p Priority) RequestOption        { return func(e *Envelope) { e.Priority = p } }
func WithTTL(ttl int) RequestOption                { return func(e *Envelope) { e.TTLSeconds = ttl } }
func WithCorrelationID(id string) RequestOption    { return func(e *Envelope) { e.CorrelationID = id } }

// NewResponse creates a response envelope correlated to a request.
func NewResponse(req *Envelope, status Status, data map[string]interface{}, errInfo *ErrorInfo) *Envelope {
	return &Envelope{
		ProtoVersion:  req.ProtoVersion,
		TraceID:       req.TraceID,
		MsgID:         newUUID(),
		MsgType:       MsgResponse,
		Timestamp:     now(),
		Source:        req.Target,
		SourceID:      req.TargetID,
		Target:        req.Source,
		CorrelationID: req.MsgID,
		Payload: Payload{
			Action: req.Payload.Action,
			Status: status,
			Data:   data,
			Error:  errInfo,
		},
	}
}

// --- Platform helpers (overridden in tests) ---

var now = func() int64 { return timeNow() }
var newUUID = func() string { return uuidV7() }

// SetNow replaces the time source (for tests).
func SetNow(fn func() int64) { now = fn }

// SetNewUUID replaces the UUID source (for tests).
func SetNewUUID(fn func() string) { newUUID = fn }

func timeNow() int64 {
	return time.Now().Unix()
}

func uuidV7() string {
	return uuid.NewString()
}
