# Smart Open Connect 0.3.10 - stale Connect / TLS recovery

## Problem reproduced

After the app had been idle or backgrounded, pressing **Connect** could occasionally start a new attempt that reached:

```text
LIB: Connected to <relay>:<port>
LIB: SSL negotiation with <vpn-hostname>
```

and then made no further progress. Force-stopping the Android app and opening it again cleared the condition.

The observed failure is consistent with stale process-local OpenConnect state or an older management thread surviving long enough to overlap a new manual connection attempt.

## Changes

### 1. Manual Connect no longer overlaps an older VPN thread

Before starting a fresh manual connection, Smart Open Connect stops the previous OpenConnect management session.

If the old Java/native VPN thread is still alive after the normal stop/join period, the app does **not** start a second OpenConnect session beside it. Instead it hands the connection to the same controlled full-session restart path introduced in 0.3.9 for network changes:

```text
Connect
  -> stop old session
  -> old thread still alive?
       -> yes: controlled full reset
       -> wait until old thread exits
       -> create new OpenConnectManagementThread
       -> Smart Relay + authentication run from a clean session
```

Expected diagnostic line:

```text
CONNECT: stale VPN thread survived stop; resetting before new session
```

### 2. Native TLS handshake watchdog

A watchdog is armed only when libopenconnect reports:

```text
SSL negotiation with ...
```

If the native TLS handshake makes no progress for **10 seconds**, the attempt is cancelled instead of remaining stuck indefinitely.

Expected diagnostics:

```text
TLS: handshake watchdog armed for 10000ms
TLS: handshake timeout after 10000ms; canceling native attempt
TLS: handshake timeout - resetting OpenConnect session for retry 1/1
```

The watchdog is cleared as soon as the connection reaches certificate validation or the authentication form.

### 3. One automatic fresh-session retry

A TLS-timeout recovery creates a new libopenconnect/OpenConnect session and retries once.

With Smart Relay enabled, if the timed-out relay was the top-ranked candidate and another healthy probed candidate exists, the retry skips the timed-out relay and uses the next candidate.

Expected diagnostic:

```text
SMART RELAY: retry skipping timed-out <old-ip>; using <next-ip>
```

If there is no alternate healthy candidate, the same relay may be retried once.

## Unchanged behavior

- Smart Relay discovery and Java TCP/TLS pre-probing remain unchanged.
- Original VPN hostname remains the logical TLS/SNI/authentication identity.
- Saved credentials remain one-tap when all required values are present.
- Full-session network-change reconnect behavior remains in place.
- Signing key remains the existing Smart Open Connect persistent signing key.
- Build remains arm64-v8a.

## Version

- Version name: **0.3.10**
- Version code: **13**
- Base client: **OpenConnect for Android 1.12**
- Status: **stable release**
- Architecture: **arm64-v8a**
- GitHub Actions build: **36339524568**
- APK SHA-256: **eba93c20bd253abce64741238232700c08c3fc886dbe148c7528f6c645803976**
