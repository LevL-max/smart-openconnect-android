# Smart Open Connect 0.3.3

Smart Open Connect 0.3.3 is a public-ready Android build based on OpenConnect for Android 1.12. It adds Smart Relay selection for VPN hostnames that may resolve to several physical relay IPs when only some of those paths are reachable from the current network.

All examples below use reserved documentation-only hostnames and IP ranges. They are not real infrastructure.

## Smart Relay - how it works

A VPN profile keeps its normal logical hostname and port, for example:

```text
vpn.example.com:443
```

Smart Relay does not replace that hostname with a different VPN identity. The hostname remains the logical identity of the VPN server throughout TLS and authentication.

```text
VPN profile hostname
        |
        v
candidate discovery
        |
        v
parallel TCP/TLS probes
        |
        v
rank healthy candidates by quality + latency
        |
        v
select fastest TLS-healthy relay
        |
        v
native libopenconnect resolver override
        |
        +---- physical TCP destination ---> selected relay IP
        |
        +---- logical VPN identity -------> original hostname
                                             TLS SNI
                                             certificate/hostname processing
                                             HTTP Host / OpenConnect auth
```

### Candidate discovery

Before OpenConnect starts authentication, Smart Relay builds a candidate pool for the selected logical hostname. Candidate sources include the Android/system DNS view, Google DNS-over-HTTPS, Cloudflare DNS-over-HTTPS, and the local persistent Smart Relay cache. Duplicate addresses are removed before probing.

Candidates are discovered dynamically. A discovered IP is only a possible physical path and is not automatically treated as a trusted VPN identity.

### Parallel health and speed probing

Candidates are probed in parallel rather than one by one. The selector checks the actual VPN TCP port and, when TCP is reachable, performs a TLS handshake using the original logical hostname as SNI.

A candidate can therefore be classified as:

- **TLS healthy** - TCP and TLS both succeed;
- **TCP only** - TCP answers but the TLS-aware probe does not complete successfully;
- **dead/unreachable** - TCP fails or times out.

No VPN username or password is sent by Smart Relay health probes.

### Fastest healthy relay selection

TLS-healthy candidates rank ahead of TCP-only candidates. Within the best available class, Smart Relay selects the candidate with the lowest observed connection latency.

Illustrative example using RFC 5737 documentation addresses:

```text
203.0.113.10   TCP 20 ms + TLS 90 ms  = 110 ms  -> selected
203.0.113.11   TCP 35 ms + TLS 140 ms = 175 ms
203.0.113.12   timeout                         -> rejected
```

The selector therefore prefers the fastest usable TLS path rather than merely selecting the first address returned by DNS.

### Android VPN routing protection

Relay probes are explicitly excluded from the Android VPN using `VpnService.protect()` so the pre-connection checks do not loop back into an already active VPN tunnel.

0.3.3 includes an Android socket-initialization fix: the probe socket is given a usable file descriptor before `VpnService.protect()` is called. This allows the probes to measure the real underlying network path reliably.

### Physical IP vs logical VPN identity

After a relay is selected, Smart Open Connect installs a narrow native libopenconnect resolver override for the selected logical hostname.

For example:

```text
Logical VPN server:   vpn.example.com:443
Selected physical IP: 203.0.113.10
Physical connection:  203.0.113.10:443
```

OpenConnect still treats `vpn.example.com` as the server identity. The original hostname remains in use for TLS SNI, certificate/hostname processing, HTTP Host where applicable, and normal OpenConnect authentication.

The core design rule is:

```text
Physical destination = selected relay IP
Logical VPN identity = original hostname
```

Smart Relay changes where the TCP connection is physically sent, not which VPN identity OpenConnect authenticates.

### Relay IP visibility

The Connect screen shows the VPN tunnel IP and the selected physical Relay IP separately. The Relay IP is persisted per VPN profile, with a profile UUID-keyed fallback so one profile cannot accidentally display another profile's relay.

### Fallback behaviour

If Smart Relay cannot find a usable candidate, it does not permanently rewrite the profile or invent an endpoint. The resolver override is not installed and OpenConnect falls back to its normal DNS connection behaviour.

If a selected relay passes the pre-probe but then fails during the real OpenConnect connection, a new Connect attempt runs Smart Relay selection again.

## One-tap saved authentication

Smart Open Connect uses the normal locally saved authentication form values supported by OpenConnect for Android. It does not embed usernames or passwords in the repository or APK source.

When a complete saved form is available, it is submitted automatically on the first presentation. If the exact same authentication form is returned again, automatic submission stops and the normal interactive dialog is shown. This prevents a stale or incorrect saved password from creating an automatic retry loop.

Normal saved-profile flow:

```text
Connect -> Smart Relay selection -> saved authentication -> VPN connected
```

## Recent profiles and one-handed UI

The three most recently selected VPN profiles appear directly above the main Connect/Disconnect button. The full profile list and editing remain under **Servers**. Bottom navigation remains fixed as:

```text
Connect / Servers / Log
```

## UI, Settings and launcher icon

0.3.3 uses the Smart Open Connect dark visual system across the main UI and profile/settings screens. The launcher artwork is delivered as a proper Android adaptive icon to avoid compatibility trays around a legacy launcher drawable on modern launchers.

## Clearer Android log messages

Two native OpenConnect conditions are expected on many Android devices but can look like fatal failures in a raw log. 0.3.3 presents them as informational messages:

```text
INFO: vhost-net unavailable on Android; using standard TUN
INFO: DTLS address not provided; using CSTP/TCP
```

This changes presentation only. Security-relevant TLS and certificate-verification messages remain visible.

## Persistent signing and Android updates

0.3.3 uses a persistent project signing key rather than a newly generated CI debug certificate on every build. Future APKs signed with the same key can be installed as normal Android updates without uninstalling the application first.

Users already on the persistent-signed 0.3.2 line can install 0.3.3 directly as an update. Older experimental APKs signed by transient CI keys may require one final uninstall before moving to the persistent-signed line.

## Architecture and security notes

- Base client: **OpenConnect for Android 1.12**.
- Application ID: `net.openconnect_vpn.android.smart`.
- Architecture: **arm64-v8a**.
- Smart Relay runs inside the Android client and native libopenconnect integration; no Termux process or companion helper app is required.
- Relay addresses are dynamic routing candidates, not hard-coded trust decisions.
- The original hostname remains authoritative for TLS/SNI and VPN identity.
- Turning Smart Relay off leaves the normal OpenConnect path available.
- The project remains subject to the upstream OpenConnect/Android GPL licensing obligations.

## Build verification

The 0.3.3 CI build verifies the Android version, application label, persistent signing certificate, rebuilt arm64 native library, final APK signature and APK checksum before publishing.

APK SHA-256:

```text
7b4e546072e031365e29dc7740c786d34a740a6e5d9e7de557de9db03f70015d
```

## Known limitations / future work

- **No same-attempt relay failover yet.** If the selected relay dies after probing but during the real connection, candidate #2 is not automatically attempted inside the same authentication attempt.
- **Candidate cache is persistent/additive.** Time-based aging, failure cooldown and relay health history are future improvements.
- **DNS-first fast path is not yet implemented.** A future version may probe normal system-DNS answers first and expand discovery only if those addresses are unusable.
- **arm64-v8a only in this release.**

The selected relay controls the physical route only. The original VPN hostname remains the logical identity used by OpenConnect.