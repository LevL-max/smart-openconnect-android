# Smart Open Connect 0.3.9

Smart Open Connect 0.3.9 focuses on connection lifecycle reliability, server-selection stability, and predictable behavior when the Android device changes between Wi-Fi and mobile data.

This release uses the stable Smart Relay / UI base and replaces the unreliable upstream-style in-session network reconnect with a full OpenConnect session restart when **Reconnect on Network Change** is enabled.

## Resolved / Fixed

### Reconnect on Network Change

The expected behavior is now explicit:

- **Reconnect on Network Change = OFF** - when the active network changes, the VPN disconnects and remains disconnected.
- **Reconnect on Network Change = ON** - when the active network changes, the current OpenConnect session is stopped and a fresh session is started automatically on the new network.

The important change in 0.3.9 is that ON no longer relies on the old `OpenConnectManagementThread.reconnect()` / pause-mainloop behavior. That path could tear down the existing tunnel but fail to create a usable new session after a real Wi-Fi/mobile uplink change.

0.3.9 performs a full session restart instead:

```text
network changes
      |
      v
stop current OpenConnect management thread
      |
      v
wait until the old thread has actually exited
      |
      v
start a fresh OpenConnect management thread
      |
      v
Smart Relay selection runs again
      |
      v
saved authentication is reused
      |
      v
VPN reconnects on the new network
```

This is intentionally closer to pressing Disconnect + Connect automatically than trying to preserve the old transport session across a changed uplink.

Additional protections in this path:

- duplicate network-change events cannot schedule multiple simultaneous reconnects;
- manual Disconnect cancels a pending automatic reconnect;
- a late completion callback from the previous VPN thread cannot stop the newly started session;
- the restart waits for the old VPN thread to finish before creating the replacement thread.

This behavior was tested on-device in both directions between Wi-Fi and mobile data before publication.

### Settings no longer stalls when changing the reconnect option

Changing **Reconnect on Network Change** while the VPN is active no longer immediately broadcasts that preference into the running VPN management path.

The setting is simply stored and its value is read when a real network-change event occurs. This removes the unnecessary runtime work that could make Settings slow to leave after toggling the option.

### Server selection updates immediately

A server selected from the **Servers** screen is now committed before returning to the Connect screen.

While disconnected, the explicit user-selected profile is authoritative. A stale `service.profile` left by the previous tunnel can no longer overwrite the new selection and make it appear that the server did not change until the application was restarted.

### Recent 3 profiles no longer jump while being selected

The three recent-profile controls are now stable while the user is tapping them.

- selecting a recent profile does not reorder the row immediately;
- MRU ordering is updated when the selected profile is actually used via Connect;
- the row contains exactly three equal-width slots;
- long labels are constrained rather than pushing an additional item off the side of the screen.

This removes the previous behavior where the selected item could move under the user's finger and a partial fourth item could appear outside the intended layout.

## Smart Relay

The Smart Relay architecture remains unchanged from the tested 0.3.x line:

- dynamic candidate discovery from local cache, Android/system DNS, Google DoH and Cloudflare DoH;
- parallel TCP/TLS reachability probes;
- fastest TLS-healthy relay selection;
- original VPN hostname retained for TLS SNI, certificate/hostname handling and OpenConnect authentication;
- physical relay IP pinned only through the native resolver override;
- fallback to normal OpenConnect DNS behavior when Smart Relay cannot select a usable candidate.

Relay probes do not send VPN credentials.

## Authentication

Saved authentication remains one-tap when all required form values are already present locally.

If the same authentication form is returned again, automatic submission stops and the standard interactive dialog is shown, preventing a retry loop with stale credentials.

## About the 0.3.7 experiment

An experimental 0.3.7 build attempted to introduce a separate modern Android physical-network monitor using `NetworkCallback`. It caused a connection-start regression on-device and was not published as a release.

That approach is **not** present in the final 0.3.9 APK.

0.3.9 is built from the stable pre-0.3.7 runtime path plus the tested full-session reconnect implementation described above.

## Build and integrity

- Product: **Smart Open Connect**
- Version: **0.3.9**
- Android `versionCode`: **12**
- Architecture: **arm64-v8a**
- Minimum Android API: **23**
- Base client: **OpenConnect for Android 1.12**
- Tested source commit: `ded2c00d4da7f503b96b0b09205b13db3a366afd`
- GitHub Actions build: `34818348752`
- Artifact: `SmartOpenConnect-0.3.9-arm64`
- APK: `SmartOpenConnect-0.3.9-arm64.apk`

APK SHA-256:

```text
fc6fff1ad52933681fe171375ea23229ee3053c9761c4788cfb4d93191c54d83
```

The public release uses the exact APK that passed the device test. The release publication step does not rebuild the application.

## Signing

0.3.9 is signed with the same persistent Smart Open Connect signing key used by the stable-signed release line, so it can be installed as a normal update over compatible prior builds without removing profiles/settings.

Signing certificate SHA-256 fingerprint:

```text
D5:1B:2B:0C:B3:20:AA:D1:62:61:64:1A:1D:CE:C7:CE:92:CC:D6:A9:DC:29:DD:70:2D:B9:5E:8B:58:B1:C2:CC
```

## Known limitations

- no same-attempt automatic failover to relay candidate #2 if the chosen relay fails after pre-probing;
- relay cache is persistent/additive and does not yet implement time-based aging or failure cooldown;
- no DNS-first fast path yet;
- current published APK is arm64-v8a only.

## License

Smart Open Connect is derived from OpenConnect for Android and includes a rebuilt OpenConnect native library. The project remains subject to the applicable upstream GPL licensing requirements.
