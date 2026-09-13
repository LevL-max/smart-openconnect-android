# Smart Open Connect

**Smart Open Connect** is an Android OpenConnect client with an additional **Smart Relay** layer for VPN hostnames that may resolve to multiple physical IP addresses, where some addresses can be slow, unreachable, or intermittently blocked from the current network.

It keeps the normal OpenConnect profile, hostname, authentication flow and TLS identity, but chooses a usable physical relay before the real VPN connection starts.

Current public release: **v0.3.4**

- [Download Smart Open Connect v0.3.4](https://github.com/LevL-max/smart-openconnect-android/releases/tag/v0.3.4)
- Android: API 23+
- ABI: arm64-v8a
- Base client: OpenConnect for Android 1.12

## Why this exists

A normal OpenConnect connection typically asks DNS for the VPN hostname and then connects to one of the returned addresses.

That works well when every address behind the hostname is equally reachable. It works less well when DNS returns several relay IPs and the current mobile/Wi-Fi network can reach only some of them.

A typical failure pattern looks like this:

```text
vpn.example.com
    |
    +-- 192.0.2.10       reachable
    +-- 198.51.100.20    timeout
    +-- 203.0.113.30     reachable, but slower
```

A normal client may try `198.51.100.20` first and spend a long time waiting for a network timeout before trying another address.

Smart Open Connect performs a short discovery and health-selection stage first, then tells libopenconnect which physical IP to use while preserving the original VPN hostname as the logical server identity.

## How Smart Relay works

The high-level flow is:

```text
OpenConnect profile
      |
      v
logical VPN hostname
      |
      v
candidate discovery
      |
      v
parallel TCP + TLS probes
      |
      v
rank usable candidates
      |
      v
select fastest TLS-healthy relay
      |
      v
libopenconnect resolver override
      |
      +---- physical TCP connection ----> selected relay IP
      |
      +---- logical VPN identity --------> original hostname
                                           TLS SNI
                                           certificate processing
                                           HTTP Host / authentication
```

### 1. Candidate discovery

Smart Relay builds a temporary pool of IPv4 candidates for the selected VPN hostname.

The current public build can use:

- previously cached relay addresses from successful/previous discovery;
- Android/system DNS;
- Google DNS-over-HTTPS;
- Cloudflare DNS-over-HTTPS.

Duplicate addresses are removed. The pool is currently limited to **32 candidates**.

The public build deliberately does not contain provider-specific hostname rules or private infrastructure mappings.

### 2. Parallel probing

Discovered addresses are not trusted just because DNS returned them.

Smart Relay probes the actual VPN port for every candidate. Up to **8 candidates are tested in parallel**.

For each candidate it performs:

1. a TCP connection to the candidate IP and VPN port;
2. if TCP succeeds, a TLS handshake over that same physical connection;
3. the **original VPN hostname is supplied as TLS SNI** during that probe.

Current probe limits are approximately:

```text
DNS request timeout:  1400 ms
TCP connect timeout:  1800 ms
TLS probe timeout:    2200 ms
```

Parallel probing is important: five dead addresses should not automatically mean five sequential timeout periods.

### 3. Android VPN protection

Probe sockets must use the physical network rather than accidentally routing back into an already active Android VPN.

Smart Open Connect therefore exempts probe sockets with `VpnService.protect()` before connecting them.

On Android, a newly constructed Java socket may not yet have a usable native file descriptor. The current implementation first binds the socket to an ephemeral local port, then calls `VpnService.protect()`, then connects to the candidate relay.

Conceptually:

```text
new Socket()
    -> bind(local ephemeral port)
    -> VpnService.protect(socket)
    -> connect(candidate IP, VPN port)
```

### 4. Health classification

Each candidate is placed into one of three groups:

```text
TLS healthy
TCP-only healthy
failed / unreachable
```

A TLS-healthy relay is preferred over a TCP-only relay. A known failed candidate is never intentionally selected.

The Java TLS probe is a **reachability/SNI probe**, not the final certificate trust decision. It intentionally does not perform the same trust validation as the real OpenConnect connection.

The actual VPN connection still goes through libopenconnect and its normal certificate/hostname validation path.

### 5. Fastest healthy relay selection

Within the best available health class, candidates are sorted by measured latency.

For TLS-healthy candidates the effective comparison is approximately:

```text
score = TCP connect time + TLS handshake time
```

Example using documentation-only addresses:

```text
192.0.2.10       TCP 24 ms + TLS 180 ms = 204 ms  <- selected
203.0.113.30     TCP 32 ms + TLS 260 ms = 292 ms
198.51.100.20    timeout                          <- rejected
```

So Smart Relay does not merely select the first address that responds. It prefers the fastest candidate among the best available health class.

### 6. Physical destination vs logical VPN identity

This is the most important design rule in Smart Relay.

Assume the profile contains:

```text
vpn.example.com:443
```

and Smart Relay chooses:

```text
192.0.2.10
```

The physical network connection becomes:

```text
192.0.2.10:443
```

but OpenConnect still treats the server as:

```text
vpn.example.com
```

The original hostname remains in use for the parts where identity matters:

- TLS SNI;
- certificate/hostname processing;
- HTTP Host where applicable;
- OpenConnect authentication;
- the profile shown to the user.

Smart Relay therefore changes **where the TCP connection goes**, not **which VPN server identity is authenticated**.

### 7. Native libopenconnect integration

Once a relay is selected, the Android layer installs a narrow resolver override in the native OpenConnect integration.

Only the selected logical VPN hostname is pinned to the chosen physical address. The profile itself is not rewritten to an IP address.

This is what allows the client to connect physically to a chosen relay while keeping the hostname intact for TLS and OpenConnect protocol handling.

## Fallback behavior

Smart Relay is designed to fail open to normal OpenConnect behavior rather than permanently modifying a profile.

If no candidates can be discovered, or if no candidate passes the health checks:

```text
Smart Relay selection fails
        |
        v
no resolver override is installed
        |
        v
OpenConnect uses its normal DNS connection path
```

Turning Smart Relay off also leaves the normal OpenConnect path available.

## What Smart Relay does not do

Smart Relay does **not**:

- replace the logical VPN hostname with an IP in the profile;
- send the VPN username/password during relay probes;
- treat the Java TLS reachability probe as the final certificate trust decision;
- require Termux, shell scripts or a companion Android application;
- contain private relay IPs or provider-specific production mappings in the public build.

## One-tap saved authentication

OpenConnect for Android already stores authentication form values locally when configured to do so.

Smart Open Connect changes the interaction flow so a fully populated saved authentication form can be submitted automatically on its first presentation.

The flow is:

```text
Connect
   -> Smart Relay selection
   -> OpenConnect auth form arrives
   -> saved values are complete
   -> submit once automatically
```

There is an important guard: if the **same authentication form is returned again**, automatic submission stops and the normal interactive dialog is shown.

This prevents a stale or incorrect saved password from creating an automatic retry loop.

Credentials are not hard-coded into the application or repository.

## Connect screen

The main screen is designed for one-handed use.

It shows:

- connection state;
- tunnel IP;
- selected physical Relay IP;
- traffic statistics;
- current VPN profile;
- Smart Relay state;
- the three recently used profiles;
- a large Connect/Disconnect control in the lower thumb zone.

The bottom navigation remains fixed:

```text
Connect / Servers / Log
```

## Recent 3 profiles

The Connect screen exposes exactly three recent profile slots.

In v0.3.4, **selection** and **MRU ordering** are intentionally separate operations:

- tapping a Recent 3 item selects the profile immediately;
- simply selecting it does not reorder the controls under the user's finger;
- the MRU list is promoted when the profile is actually used via Connect;
- the row always contains exactly three equal-width slots;
- long names are ellipsized instead of pushing another profile off-screen.

## Server selection behavior

The selected profile is authoritative while the VPN is disconnected.

Older builds could receive the previous tunnel's `service.profile` after disconnect and accidentally use that stale state to visually replace a newly selected server. The result looked as if a server could only be changed after restarting the application.

v0.3.4 fixes this by ensuring that:

- selection from **Servers** is committed before returning to Connect;
- the explicitly selected profile wins while disconnected;
- a stale profile from the previous tunnel cannot overwrite the new selection.

## Relay IP display

The Connect screen intentionally shows two different IP concepts:

```text
Tunnel IP  = address assigned inside the VPN
Relay IP   = physical Internet-side address selected by Smart Relay
```

The selected Relay IP is persisted per profile so switching between profiles does not display another profile's relay.

## Logging

The Log screen keeps the OpenConnect diagnostic stream, including Smart Relay discovery/probe information.

Two Linux/OpenConnect messages that are normally harmless on Android are normalized into informational text:

```text
vhost-net unavailable on Android; using standard TUN
DTLS address not provided; using CSTP/TCP
```

Security-relevant certificate messages are intentionally not hidden.

## Updates and signing

Current builds use a persistent Smart Open Connect signing certificate rather than a fresh ephemeral GitHub Actions debug key for every build.

That means releases signed with the same project key can be installed as normal Android updates without uninstalling the application and losing profiles/settings.

Signing certificate SHA-256 fingerprint:

```text
D5:1B:2B:0C:B3:20:AA:D1:62:61:64:1A:1D:CE:C7:CE:92:CC:D6:A9:DC:29:DD:70:2D:B9:5E:8B:58:B1:C2:CC
```

## Current limitations

Smart Open Connect v0.3.4 intentionally keeps the relay algorithm that has been tested on real devices.

Known limitations:

- **No same-attempt relay failover yet.** If the selected relay passes the pre-probe and then fails during the real OpenConnect connection, the current attempt does not automatically continue with candidate #2. Pressing Connect again performs a fresh selection pass.
- **The relay cache is additive.** Cached candidates are re-probed, but there is no time-based aging/failure cooldown model yet.
- **No DNS-first fast path yet.** The current selector builds the broader candidate pool before probing it. A future optimization can first test only system-DNS answers and expand to DoH/cache only if necessary.
- **arm64-v8a only** in the current published APK.

## Build model

The repository keeps the Smart Open Connect modifications as a reproducible overlay on top of the maintained OpenConnect for Android source.

The GitHub Actions pipeline:

```text
fetch OpenConnect for Android 1.12
        |
        v
apply Smart Relay / UI patch
        |
        v
apply versioned overlays and fixes
        |
        v
rebuild native libopenconnect for arm64-v8a
        |
        v
build Android APK
        |
        v
sign with persistent project key
        |
        v
verify version / label / signing fingerprint
        |
        v
SHA-256 + release artifact
```

The native library is rebuilt because Smart Relay includes JNI/native resolver-override integration with libopenconnect.

## Release integrity

Latest release:

**Smart Open Connect v0.3.4**

APK:

```text
SmartOpenConnect-0.3.4-arm64.apk
```

SHA-256:

```text
a14a55bde1b4786999920e7584834fb568a0d86b8f159a5a1fc965480415fcb1
```

The v0.3.4 release APK is the exact artifact produced by the tested GitHub Actions build, rather than a separate rebuild performed during publication.

## Upstream and license

Smart Open Connect is derived from **OpenConnect for Android** and includes a rebuilt OpenConnect native library.

The project remains subject to the applicable upstream GPL licensing requirements. See the repository license/source files and the upstream OpenConnect projects for details.

---

For version-specific changes, see the [GitHub Releases](https://github.com/LevL-max/smart-openconnect-android/releases) page. The README is intended to describe the stable project architecture and behavior; release notes describe what changed in a particular version.
