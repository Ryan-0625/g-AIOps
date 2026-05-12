package tools

import (
	"bufio"
	"context"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "network.connections",
		Timeout:      10 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeNetworkConnections,
	})
}

func executeNetworkConnections(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	protocol := "tcp"
	if p, ok := params["protocol"].(string); ok {
		switch p {
		case "tcp", "udp", "all":
			protocol = p
		}
	}
	stateFilter := "all"
	if s, ok := params["state"].(string); ok {
		switch s {
		case "established", "listening", "all":
			stateFilter = s
		}
	}

	var connections []map[string]interface{}

	// Parse TCP connections from /proc/net/tcp (Linux).
	if protocol == "tcp" || protocol == "all" {
		tcpConns, err := parseProcNetTCP("/proc/net/tcp", stateFilter, "tcp")
		if err == nil {
			connections = append(connections, tcpConns...)
		}
		// Also check TCP6.
		tcp6Conns, err := parseProcNetTCP("/proc/net/tcp6", stateFilter, "tcp6")
		if err == nil {
			connections = append(connections, tcp6Conns...)
		}
	}

	if protocol == "udp" || protocol == "all" {
		udpConns, err := parseProcNetTCP("/proc/net/udp", stateFilter, "udp")
		if err == nil {
			connections = append(connections, udpConns...)
		}
	}

	return map[string]interface{}{
		"connections": connections,
		"count":       len(connections),
	}, nil
}

// TCP state codes from /proc/net/tcp.
var tcpStates = map[string]string{
	"01": "established",
	"02": "syn_sent",
	"03": "syn_recv",
	"04": "fin_wait1",
	"05": "fin_wait2",
	"06": "time_wait",
	"07": "close",
	"08": "close_wait",
	"09": "last_ack",
	"0A": "listening",
	"0B": "closing",
}

func parseProcNetTCP(path, stateFilter, protocol string) ([]map[string]interface{}, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	var conns []map[string]interface{}
	scanner := bufio.NewScanner(f)
	// Skip header line.
	if scanner.Scan() {
		// skip
	}

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		fields := strings.Fields(line)
		if len(fields) < 10 {
			continue
		}

		localAddr := fields[1]
		remAddr := fields[2]
		stateCode := fields[3]

		state := tcpStates[stateCode]
		if state == "" {
			continue
		}

		// Filter by state.
		switch stateFilter {
		case "established":
			if state != "established" {
				continue
			}
		case "listening":
			if state != "listening" {
				continue
			}
		}

		localIP, localPort := parseHexAddr(localAddr)
		remIP, remPort := parseHexAddr(remAddr)

		conn := map[string]interface{}{
			"protocol":      protocol,
			"local_address": net.JoinHostPort(localIP, strconv.Itoa(localPort)),
			"remote_address": net.JoinHostPort(remIP, strconv.Itoa(remPort)),
			"state":         state,
		}

		// Parse PID (field 9 is tx_queue:rx_queue, skip, field 10 is tr, tm->when, field 11 is retrnsmt,
		// field 12 is uid, field 13 is timeout, field 14 is inode).
		if len(fields) >= 14 {
			inode := fields[13]
			if inode != "0" {
				conn["inode"] = inode
			}
		}

		conns = append(conns, conn)
	}

	return conns, nil
}

// parseHexAddr converts "0100007F:0035" to ("127.0.0.1", 53).
func parseHexAddr(hexAddr string) (string, int) {
	parts := strings.SplitN(hexAddr, ":", 2)
	if len(parts) != 2 {
		return "0.0.0.0", 0
	}
	ipHex := parts[0]
	portHex := parts[1]

	port, _ := strconv.ParseInt(portHex, 16, 32)

	// IPv4: 8 hex chars (4 bytes, little-endian).
	if len(ipHex) == 8 {
		ip := fmt.Sprintf("%d.%d.%d.%d",
			parseHexByte(ipHex[6:8]),
			parseHexByte(ipHex[4:6]),
			parseHexByte(ipHex[2:4]),
			parseHexByte(ipHex[0:2]),
		)
		return ip, int(port)
	}

	// IPv6: 32 hex chars.
	if len(ipHex) == 32 {
		// Format as IPv6 address.
		var bytes [16]byte
		for i := 0; i < 16; i++ {
			bytes[i] = parseHexByte(ipHex[(15-i)*2 : (15-i)*2+2])
		}
		ip := net.IP(bytes[:]).String()
		return ip, int(port)
	}

	return "0.0.0.0", int(port)
}

func parseHexByte(s string) byte {
	v, _ := strconv.ParseInt(s, 16, 8)
	return byte(v)
}
