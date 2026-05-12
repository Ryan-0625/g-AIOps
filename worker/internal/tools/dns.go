package tools

import (
	"context"
	"fmt"
	"net"
	"strings"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "dns.lookup",
		Timeout:      10 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeDNSLookup,
	})
}

func executeDNSLookup(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	hostname, _ := params["hostname"].(string)
	if hostname == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "hostname is required")
	}

	recordType := "A"
	if rt, ok := params["record_type"].(string); ok {
		rt = strings.ToUpper(rt)
		switch rt {
		case "A", "AAAA", "MX", "TXT", "CNAME":
			recordType = rt
		default:
			return nil, executor.NewErr("INVALID_PARAMS", fmt.Sprintf("unsupported record type: %s", rt))
		}
	}

	resolver := net.DefaultResolver

	switch recordType {
	case "A":
		ips, err := resolver.LookupHost(ctx, hostname)
		if err != nil {
			return nil, executor.NewErr("DNS_FAILED", fmt.Sprintf("lookup A record: %v", err))
		}
		return map[string]interface{}{
			"hostname":    hostname,
			"record_type": "A",
			"addresses":   ips,
		}, nil

	case "AAAA":
		ips, err := resolver.LookupIPAddr(ctx, hostname)
		if err != nil {
			return nil, executor.NewErr("DNS_FAILED", fmt.Sprintf("lookup AAAA record: %v", err))
		}
		addrs := make([]string, 0, len(ips))
		for _, ip := range ips {
			addrs = append(addrs, ip.String())
		}
		return map[string]interface{}{
			"hostname":    hostname,
			"record_type": "AAAA",
			"addresses":   addrs,
		}, nil

	case "MX":
		mxRecords, err := resolver.LookupMX(ctx, hostname)
		if err != nil {
			return nil, executor.NewErr("DNS_FAILED", fmt.Sprintf("lookup MX record: %v", err))
		}
		records := make([]map[string]interface{}, 0, len(mxRecords))
		for _, mx := range mxRecords {
			records = append(records, map[string]interface{}{
				"host": mx.Host,
				"pref": mx.Pref,
			})
		}
		return map[string]interface{}{
			"hostname":    hostname,
			"record_type": "MX",
			"records":     records,
		}, nil

	case "TXT":
		txts, err := resolver.LookupTXT(ctx, hostname)
		if err != nil {
			return nil, executor.NewErr("DNS_FAILED", fmt.Sprintf("lookup TXT record: %v", err))
		}
		return map[string]interface{}{
			"hostname":    hostname,
			"record_type": "TXT",
			"records":     txts,
		}, nil

	case "CNAME":
		cname, err := resolver.LookupCNAME(ctx, hostname)
		if err != nil {
			return nil, executor.NewErr("DNS_FAILED", fmt.Sprintf("lookup CNAME record: %v", err))
		}
		return map[string]interface{}{
			"hostname":    hostname,
			"record_type": "CNAME",
			"target":      cname,
		}, nil
	}

	return nil, executor.NewErr("UNSUPPORTED", "unsupported record type")
}
