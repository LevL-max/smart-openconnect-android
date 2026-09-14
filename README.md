# Smart Open Connect

**Smart Open Connect** is an Android OpenConnect client with an additional **Smart Relay** layer for VPN hostnames that may resolve to multiple physical IP addresses, where some addresses can be slow, unreachable, or intermittently blocked from the current network.

It keeps the normal OpenConnect profile, hostname, authentication flow and TLS identity, but chooses a usable physical relay before the real VPN connection starts.

Current public release: **v0.3.9**

- [Download Smart Open Connect v0.3.9](https://github.com/LevL-max/smart-openconnect-android/releases/tag/v0.3.9)
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

A normal client may try an unreachable address first and spend a long time waiting for a network timeout before trying another address.

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

### Candidate discovery

Smart Relay builds a temporary pool of IPv4 candidates for the selected VPN hostname.

The current public build can use:

- previously cached relay addresses;
- Android/system DNS;
- Google DNS-over-HTTPS;
- Cloudflare DNS-over-HTTPS.

Duplicate addresses are removed. The pool is currently limited to **32 candidates**.

The public build deliberately does not contain provider-specific hostname rules or private infrastructure mappings.

### Parallel probing

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

Parallel probing is important: several dead addresses should not automatically mean several sequential timeout periods.

### Android VPN protection

Probe sockets must use the physical network rather than accidentally routing back into an already active Android VPN.

Smart Open Connect therefore exempts probe sockets with `VpnService.protect()` before connecting them.

On Android, a newly constructed Java socket may not yet have a usable native file descriptor. The current implementation first binds the socket to an ephemeral local port, then calls `VpnService.protect()`, then connects to the candidate relay.

```text
new Socket()
    -> bind(local ephemeral port)
    -> VpnService.protect(socket)
    -> connect(candidate IP, VPN port)
```

### Health classification and selection

Each candidate is placed into one of three groups:

```text
TLS healthy
TCP-only healthy
failed / unreachable
```

A TLS-healthy relay is preferred over a TCP-only relay. A known failed candidate is never intentionally selected.

Within the best available health class, candidates are sorted by measured latency. For TLS-healthy candidates the comparison is approximately:

```text
score = TCP connect time + TLS handshake time
```

The Java TLS probe is a **reachability/SNI probe**, not the final certificate trust decision. The actual VPN connection still goes through libopenconnect and its normal certificate/hostname validation path.

### Physical destination vs logical VPN identity

This is the most important Smart Relay rule.

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

The original hostname remains in use for:

- TLS SNI;
- certificate/hostname processing;
- HTTP Host where applicable;
- OpenConnect authentication;
- the profile shown to the user.

Smart Relay changes **where the TCP connection goes**, not **which VPN server identity is authenticated**.

### Native libopenconnect integration

Once a relay is selected, the Android layer installs a narrow resolver override in the native OpenConnect integration.

Only the selected logical VPN hostname is pinned to the chosen physical address. The profile itself is not rewritten to an IP address.

## Fallback behavior

If no candidates can be discovered, or if no candidate passes the health checks, no resolver override is installed and OpenConnect falls back to its normal DNS connection path.

Turning Smart Relay off also leaves the normal OpenConnect path available.

## One-tap saved authentication

OpenConnect for Android already stores authentication form values locally when configured to do so.

Smart Open Connect changes the interaction flow so a fully populated saved authentication form can be submitted automatically on its first presentation:

```text
Connect
   -> Smart Relay selection
   -> OpenConnect auth form arrives
   -> saved values are complete
   -> submit once automatically
```

If the **same authentication form is returned again**, automatic submission stops and the normal interactive dialog is shown. This prevents a stale or incorrect saved password from creating an automatic retry loop.

Credentials are not hard-coded into the application or repository.

## Reconnect on Network Change

Smart Open Connect 0.3.9 gives this option explicit behavior.

### Option disabled

When **Reconnect on Network Change** is OFF:

```text
Wi-Fi/mobile network changes
      |
      v
current VPN session is stopped
      |
      v
VPN remains disconnected
```

This is useful when the user wants a network transition to require an explicit new Connect action.

### Option enabled

When **Reconnect on Network Change** is ON, Smart Open Connect performs a **full OpenConnect session restart** rather than attempting to preserve the old transport session across the changed uplink.

```text
Wi-Fi/mobile network changes
      |
      v
stop current OpenConnect management thread
      |
      v
wait for the old thread to exit
      |
      v
start a fresh OpenConnect management thread
      |
      v
run Smart Relay again
      |
      v
reuse saved authentication
      |
      v
establish VPN on the new network
```

This matters because the upstream-style in-session reconnect can tear down the old tunnel without reliably creating a usable new session after the physical uplink changes.

The 0.3.9 restart path includes several guards:

- duplicate network-change events cannot schedule multiple simultaneous reconnects;
- manual Disconnect cancels a pending automatic reconnect;
- the new session is not started until the old VPN thread has actually finished;
- a late completion callback from the previous thread cannot stop the newly started session.

The setting is read when a real network-change event occurs. Simply toggling the checkbox in Settings does not immediately restart or manipulate the active VPN, which also avoids the previous Settings UI delay.

The final 0.3.9 behavior was tested on-device in both directions between Wi-Fi and mobile data before publication.

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

Selection and MRU ordering are intentionally separate operations:

- tapping a Recent 3 item selects the profile immediately;
- simply selecting it does not reorder the controls under the user's finger;
- the MRU list is promoted when the profile is actually used via Connect;
- the row contains exactly three equal-width slots;
- long names are constrained instead of pushing another item off-screen.

## Server selection behavior

The selected profile is authoritative while the VPN is disconnected.

Older builds could receive the previous tunnel's `service.profile` after disconnect and accidentally use that stale state to replace a newly selected server. That made it appear that server selection only took effect after restarting the application.

Current behavior ensures that:

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

## What is not in the final 0.3.9 release

An experimental 0.3.7 build introduced a separate modern Android physical-network monitor using `NetworkCallback`. It caused a connection-start regression during device testing and was not published as a stable release.

That experimental monitor is **not present** in the final 0.3.9 APK.

The published 0.3.9 runtime is based on the stable pre-0.3.7 path plus the tested full-session reconnect implementation described above.

## Current limitations

Known limitations in v0.3.9:

- **No same-attempt relay failover yet.** If the selected relay passes the pre-probe and then fails during the real OpenConnect connection, the current attempt does not automatically continue with candidate #2. Pressing Connect again performs a fresh selection pass.
- **The relay cache is additive.** Cached candidates are re-probed, but there is no time-based aging/failure cooldown model yet.
- **No DNS-first fast path yet.** The selector still builds the broader candidate pool before probing it.
- **arm64-v8a only** in the current published APK.

## Build model

The repository keeps the Smart Open Connect modifications as a reproducible overlay on top of the maintained OpenConnect for Android source.

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

**Smart Open Connect v0.3.9**

APK:

```text
SmartOpenConnect-0.3.9-arm64.apk
```

SHA-256:

```text
fc6fff1ad52933681fe171375ea23229ee3053c9761c4788cfb4d93191c54d83
```

Tested source commit:

```text
ded2c00d4da7f503b96b0b09205b13db3a366afd
```

GitHub Actions build:

```text
34818348752
```

The v0.3.9 release APK is the exact artifact that passed the device test. Publication does not rebuild the APK.

## Upstream and license

Smart Open Connect is derived from **OpenConnect for Android** and includes a rebuilt OpenConnect native library.

The project remains subject to the applicable upstream GPL licensing requirements. See the repository license/source files and the upstream OpenConnect projects for details.

---

For version-specific changes, see the [GitHub Releases](https://github.com/LevL-max/smart-openconnect-android/releases) page. The README describes the stable project architecture and behavior; release notes describe what changed in a particular version.
