package connection

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/reporter"
	"github.com/gaiops/worker/pkg/envelope"
)

// Client manages the WebSocket connection to Master.
type Client struct {
	config  Config
	auth    *Auth
	exec    *executor.Executor
	dedup   *DedupCache
	policy  *ReconnectPolicy
	reporter *reporter.Reporter
	conn    *websocket.Conn
	mu      sync.Mutex
	done    chan struct{}
}

// Config groups connection-related parameters.
type Config struct {
	MasterURL         string
	ClusterToken      string
	HeartbeatInterval int // seconds
	ReconnectBase     int // seconds
	ReconnectMax      int // seconds
	Actions           []string          // tool actions for capability advert
	RiskLevels        map[string]string // per-action risk level
	MaxConcurrent     int               // max concurrent tool executions
	WorkerVersion     string            // build version
}

func New(cfg Config, exec *executor.Executor) *Client {
	return &Client{
		config: cfg,
		auth:   NewAuth(cfg.ClusterToken),
		exec:   exec,
		dedup:  NewDedupCache(1024),
		policy: NewReconnectPolicy(cfg.ReconnectBase, cfg.ReconnectMax),
	}
}

// Run connects to Master and processes messages. Blocks until ctx is
// cancelled or a non-retryable error occurs.
func (c *Client) Run(ctx context.Context) error {
	attempt := 0
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		err := c.connect(ctx)
		if err == nil {
			attempt = 0 // reset on successful connect
			c.runSession(ctx)
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		delay := c.policy.Delay(attempt)
		attempt++
		log.Printf("reconnecting in %v (attempt %d)", delay, attempt)
		select {
		case <-time.After(delay):
		case <-ctx.Done():
			return ctx.Err()
		}
	}
}

// connect performs the WebSocket handshake with auth.
func (c *Client) connect(ctx context.Context) error {
	header := http.Header{}
	c.auth.Apply(&header)

	conn, _, err := websocket.DefaultDialer.DialContext(ctx, c.config.MasterURL, header)
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}

	c.mu.Lock()
	c.conn = conn
	c.done = make(chan struct{})
	c.mu.Unlock()

	log.Println("connected to Master")
	return nil
}

// runSession handles the message loop for a single connection.
// Returns when the connection drops or ctx is cancelled.
func (c *Client) runSession(ctx context.Context) {
	defer c.close()

	// Start heartbeat in a separate goroutine.
	go NewHeartbeat(c.config.HeartbeatInterval).Start(c.conn, c.done)

	// Advertise capabilities so Master knows what this worker supports.
	c.SendCapabilityAdvertise(
		c.config.Actions,
		c.config.RiskLevels,
		c.config.MaxConcurrent,
		c.config.WorkerVersion,
	)

	// Read loop.
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		_, msg, err := c.conn.ReadMessage()
		if err != nil {
			log.Printf("read error: %v", err)
			return
		}

		c.handleMessage(ctx, msg)
	}
}

// handleMessage dispatches a single incoming envelope.
func (c *Client) handleMessage(ctx context.Context, raw []byte) {
	env, err := envelope.Unmarshal(raw)
	if err != nil {
		log.Printf("invalid envelope: %v", err)
		return
	}

	// Only handle requests from Master.
	if env.MsgType != envelope.MsgRequest || env.Source != envelope.RoleMaster {
		return
	}

	// Dedup: check if this msg_id was already processed.
	if cached := c.dedup.Get(env.MsgID); cached != nil {
		c.send(cached)
		return
	}

	// Check TTL.
	if time.Now().Unix()-env.Timestamp > int64(env.TTLSeconds) {
		log.Printf("dropping expired request: msg_id=%s action=%s", env.MsgID, env.Payload.Action)
		return
	}

	// Send ack.
	ack := &envelope.Envelope{
		ProtoVersion:  env.ProtoVersion,
		TraceID:       env.TraceID,
		MsgID:         env.MsgID,
		MsgType:       envelope.MsgAck,
		Timestamp:     time.Now().Unix(),
		Source:        envelope.RoleWorker,
		Target:        envelope.RoleMaster,
		CorrelationID: env.MsgID,
		Payload: envelope.Payload{
			Action: env.Payload.Action,
			Status: envelope.StatusPending,
		},
	}
	c.send(ack)

	// Execute the tool.
	result := c.exec.Run(ctx, env.Payload.Action, env.Payload.Params)

	// Record execution metrics.
	if c.reporter != nil {
		c.reporter.RecordExecution(result.Success,
			result.Error != nil && result.Error.Code == "TOOL_PANIC",
			result.Error != nil && result.Error.Code == "EXECUTION_TIMEOUT",
		)
	}

	// Build response.
	var status envelope.Status
	var errInfo *envelope.ErrorInfo
	if result.Success {
		status = envelope.StatusSuccess
	} else {
		status = envelope.StatusFailure
		errInfo = &envelope.ErrorInfo{
			Code:    result.Error.Code,
			Message: result.Error.Message,
			Raw:     result.Error.Raw,
		}
	}

	data := result.Data
	if result.Truncated {
		if data == nil {
			data = make(map[string]interface{})
		}
		data["_truncated"] = true
		data["_truncated_at"] = result.TruncatedAt
	}

	resp := envelope.NewResponse(env, status, data, errInfo)
	c.dedup.Set(env.MsgID, resp)
	c.send(resp)
}

// send marshals and writes an envelope to the WebSocket connection.
func (c *Client) send(env *envelope.Envelope) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.conn == nil {
		return
	}

	data, err := json.Marshal(env)
	if err != nil {
		log.Printf("marshal error: %v", err)
		return
	}

	if err := c.conn.WriteMessage(websocket.TextMessage, data); err != nil {
		log.Printf("write error: %v", err)
	}
}

// close tears down the current connection.
func (c *Client) close() {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.conn != nil {
		c.conn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""))
		c.conn.Close()
		c.conn = nil
	}
	close(c.done)
}

// SetReporter attaches a performance reporter for execution metrics.
func (c *Client) SetReporter(r *reporter.Reporter) {
	c.reporter = r
}

// SendEnvelope marshals and delivers an envelope to Master.
// Thread-safe; safe to call from the Reporter's background goroutine.
func (c *Client) SendEnvelope(env *envelope.Envelope) {
	c.send(env)
}

// SendCapabilityAdvertise announces supported actions to Master.
func (c *Client) SendCapabilityAdvertise(actions []string, riskLevels map[string]string, maxConcurrent int, version string) {
	env := &envelope.Envelope{
		ProtoVersion: "1.0",
		MsgID:        fmt.Sprintf("cap-%d", time.Now().UnixNano()),
		MsgType:      envelope.MsgEvent,
		Timestamp:    time.Now().Unix(),
		Source:       envelope.RoleWorker,
		Target:       envelope.RoleMaster,
		Payload: envelope.Payload{
			Action: "capability.advertise",
			Status: envelope.StatusSuccess,
			Params: map[string]interface{}{
				"actions":            actions,
				"risk_levels":        riskLevels,
				"max_concurrent":     maxConcurrent,
				"worker_version":     version,
				"heartbeat_interval": c.config.HeartbeatInterval,
			},
		},
	}
	c.send(env)
}
