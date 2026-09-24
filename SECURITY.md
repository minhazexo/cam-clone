# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| `master` / latest release | ✅ |
| Older releases | ❌ (please upgrade) |

## Reporting a vulnerability

Please **do not** report security vulnerabilities through public GitHub issues.

Instead, use one of these private channels:

1. **GitHub Security Advisories (preferred):**  
   [https://github.com/minhazexo/cam-clone/security/advisories/new](https://github.com/minhazexo/cam-clone/security/advisories/new)
2. If advisories are unavailable, open a minimal public issue titled `SECURITY: contact requested` asking for a private contact — **do not** include exploit details in the public issue.

Please include:

- Description of the issue and potential impact
- Affected route/component (e.g. `/api/scan`, on-device worker, upload handling)
- Steps to reproduce or a proof of concept
- Suggested fix, if you have one

## What to expect

- Acknowledgement when the report is received
- An initial assessment and timeline
- Credit in the changelog if you want it (opt-in)

We aim to fix confirmed issues promptly and to coordinate disclosure.

## Scope notes

- This app handles user documents. Reports about **data exfiltration, path traversal, SSRF, unsafe deserialization, XSS in rendered filenames, or DoS via crafted images/PDFs** are especially welcome.
- The on-device path (`/scan-pdf`) processes files in the browser; still report WASM/worker sandbox issues if found.
- Social-engineering, physical attacks, and issues in third-party dependencies without a demonstrated impact on this project are out of scope until proven reachable here.
