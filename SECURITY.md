# Security and audit notes

Reviewed 2026-11-16. This is a source and local regression review of the wrapper, not an independent penetration test or a complete audit of upstream projects.

## Boundaries

- No analytics or automatic upload of logs, diagnostic reports, proxy keys or personal configuration.
- Runtime files live under `~/Library/Application Support/SWPulse`, outside the repository. The directory is owner-only; new JSON files, proxy logs and reports are owner-readable/writable only.
- The local proxy listens on `127.0.0.1`. Optional forwarding binds explicit RFC1918 addresses of active physical `en*` interfaces and admits only RFC1918 peers in the matching subnet. VPN, public, IPv6, wildcard and Internet-facing listeners are not created by the wrapper.
- Disabling sharing revokes new relay admission, closes listeners and cancels existing relays. Network-mask changes invalidate old callbacks.
- Access keys are hidden in generic connection details. Explicit reveal, connect and QR actions use the key locally. Dedicated clipboard copies are cleared after 60 seconds if unchanged. Clipboard managers may retain copies independently.
- The proxy log formatter redacts the configured key case-insensitively, including formatted exceptions, and Telegram connection links. This is defense in depth, not permission to publish logs.
- DNS changes retain recovery state before mutation. Failed enable operations attempt rollback and retain unrecovered backups. Manual DNS changes are respected when disabling or repairing.
- User-space installation snapshots managed files privately and restores them on activation failure. The DNS installer separately stages inputs and attempts rollback on failure. Power loss, rollback failure, concurrent configuration changes and all possible macOS failure modes are not covered.

## Network requests

Builds contact GitHub and Python package indexes for upstream code and dependencies. Runtime DNS queries go to SWPulse over HTTPS. TG WS Proxy connects to Telegram and may use its configured upstream fallback providers. Diagnostic probes contact the domains and check endpoints named in `source/network_check.py`. There is no promise of anonymity or protection from a compromised local user account.

## Publication controls

`.gitignore` excludes generated builds, runtime JSON, logs, reports, environments, private-key files and app bundles. `package.py` uses a fixed source allowlist, refuses symlinks, scans common credential patterns, and can compare publication files with locally installed proxy keys without printing them. It creates a source-only ZIP and staging directory. Run it before publishing. Pattern scanning cannot prove the absence of every possible secret.

## Validation and limits

Regression tests cover owner-only atomic JSON, private physical-interface selection, log and exception redaction, DNS enable rollback, LAN admission after disable or mask changes, cancellation of existing relays, installer rollback, and publication filtering. Icon checks verify one blue left eye or one purple right eye, with both normal when healthy. Swift compilation and code-signature verification are checked locally on Apple Silicon.

The wrapper depends on private upstream Python integration APIs and latest stable releases. dnsproxy archives are checked against GitHub's release digest. TG source archive hashes are recorded for traceability, not an independent signature. Python transitive dependencies are resolved on each build. An upstream compromise or incompatible release remains a supply-chain risk.

A temporary local backend start completed an MTProto handshake and bound only loopback; it was then stopped to restore the previous state. Both proxy logs were checked for the locally configured key without printing it.

No live VPN-off test was performed during this audit. No real second-device LAN test or Intel hardware test was performed. Current health checks test one Telegram data center and a fresh DNS response; Fake TLS health checks are unsupported. Diagnostic reports contain local network information and must be reviewed before sharing.

Report a suspected issue privately to the repository owner. Do not post live keys, QR codes, logs or network snapshots in issues.
