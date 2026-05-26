# Security Policy

## Supported Versions

| Version | Supported          |
|---------|-------------------|
| 1.x     | Active development |

## Reporting a Vulnerability

Please **do not** report security vulnerabilities through public GitHub issues.

Report vulnerabilities by email to the security team.
We will acknowledge receipt within 72 hours and provide a fix within 90 days.

## Security Practices

- All Worker commands execute in a sandboxed environment (restricted Linux namespaces)
- High-risk operations require human approval at the Master level
- Cluster tokens are verified on every WebSocket handshake
- TLS is optional but recommended for production deployments
- Audit logging captures all cross-layer requests for forensic analysis
- ParamFilter rejects shell metacharacters, path traversal, and command chaining
