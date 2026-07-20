# Security Policy

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please report vulnerabilities privately:

1. Go to the GitHub repository's **Security** tab
2. Click **Report a vulnerability**
3. Provide a detailed description, including steps to reproduce and potential impact

You will receive a response within 72 hours.

## Security Measures

| Area | Measure |
|---|---|
| Credential storage | Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256) |
| Authentication | Admin token (bearer) or session cookie |
| Path traversal | `posixpath.normpath` + workdir confinement check |
| WebSocket auth | Per-connection token verification |
| CORS | Configurable origins, credentials required |
| File upload | Size limit (`EXPLORER_MAX_UPLOAD_BYTES`, default 100MB) |

## Supported Versions

| Version | Supported |
|---|---|
| 0.1.x | ✅ |
| < 0.1 | ❌ |
