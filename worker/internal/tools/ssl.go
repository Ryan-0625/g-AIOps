package tools

import (
	"context"
	"crypto/tls"
	"fmt"
	"net"
	"strings"
	"time"

	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "ssl.cert_check",
		Timeout:      15 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeSSLCertCheck,
	})
}

func executeSSLCertCheck(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	hostname, _ := params["hostname"].(string)
	if hostname == "" {
		return nil, fmt.Errorf("hostname is required")
	}

	port := 443
	if p, ok := params["port"].(int); ok && p > 0 && p < 65536 {
		port = p
	}

	addr := net.JoinHostPort(hostname, fmt.Sprintf("%d", port))
	var dialer net.Dialer
	conn, err := dialer.DialContext(ctx, "tcp", addr)
	if err != nil {
		return nil, fmt.Errorf("connection to %s failed: %w", addr, err)
	}
	defer conn.Close()

	tlsConn := tls.Client(conn, &tls.Config{
		ServerName:         hostname,
		InsecureSkipVerify: true,
	})
	defer tlsConn.Close()

	if err := tlsConn.HandshakeContext(ctx); err != nil {
		return nil, fmt.Errorf("TLS handshake failed: %w", err)
	}

	state := tlsConn.ConnectionState()
	var certInfo []map[string]interface{}
	for _, cert := state.PeerCertificates {
		if cert == nil {
			continue
		}
		info := map[string]interface{}{
			"subject":      cert.Subject.CommonName,
			"issuer":       cert.Issuer.CommonName,
			"not_before":   cert.NotBefore.Format(time.RFC3339),
			"not_after":    cert.NotAfter.Format(time.RFC3339),
			"expired":      time.Now().After(cert.NotAfter),
			"days_remaining": int(time.Until(cert.NotAfter).Hours() / 24),
			"serial":       fmt.Sprintf("%X", cert.SerialNumber),
			"is_ca":        cert.IsCA,
		}

		var sans []string
		sans = append(sans, cert.DNSNames...)
		sans = append(sans, cert.EmailAddresses...)
		for _, ip := range cert.IPAddresses {
			sans = append(sans, ip.String())
		}
		if len(sans) > 0 {
			info["subject_alt_names"] = strings.Join(sans, ", ")
		}
		certInfo = append(certInfo, info)
	}

	return map[string]interface{}{
		"hostname":      hostname,
		"port":          port,
		"certificates":  certInfo,
		"cert_count":    len(certInfo),
		"tls_version":   fmt.Sprintf("TLS %d.%d", state.Version>>8, state.Version&0xFF),
	}, nil
}
