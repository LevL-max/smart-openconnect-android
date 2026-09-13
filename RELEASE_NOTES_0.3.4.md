# Smart Open Connect v0.3.4

This release fixes server-selection and recent-profile UI behavior found during real-device testing of the 0.3.x interface.

## Fixed: server selection now changes immediately

Selecting a server from the **Servers** screen now becomes the active profile immediately and remains selected when returning to **Connect**.

The root cause was not only asynchronous preference persistence. The Connect screen could receive `service.profile` from the previous VPN session even while the service was already disconnected, and that stale profile could overwrite or visually replace the user's new selection. This is why a newly selected server could appear not to change until the application was restarted.

v0.3.4 changes the disconnected-state profile logic so that:

- the explicitly selected profile is authoritative while disconnected;
- a stale `service.profile` from the previous tunnel cannot overwrite the user's choice;
- selection from the Servers screen is committed synchronously before returning to Connect;
- no application restart is required for the new server to appear and be used.

## Fixed: Recent 3 no longer jump while being selected

The previous implementation updated the MRU list inside the same profile-selection action used by the recent-profile buttons. Tapping one of the Recent 3 entries therefore immediately reordered the row underneath the user's finger, which could make the selected item jump sideways and made the control feel unreliable.

v0.3.4 separates **selection** from **MRU promotion**:

- tapping a Recent 3 profile selects it without reordering the row;
- the MRU order is updated only when that profile is actually used by pressing Connect;
- rendering the Recent 3 strip no longer mutates the stored MRU list.

## Fixed: exactly three stable recent-profile slots

The recent-profile row is now constrained to exactly three equal slots.

- `weightSum=3` is used for the row;
- each recent-profile control has zero minimum width and equal weight;
- long profile names are ellipsized rather than pushing another item outside the visible area;
- there is no fourth partially visible profile at the side of the screen.

## Smart Relay and connection logic

This release does not change the core Smart Relay selection algorithm or OpenConnect connection behavior. The fixes are focused on GUI/profile-selection state and the Recent 3 control.

Smart Relay continues to discover and probe candidate relay addresses automatically, select a usable relay, and keep the original logical VPN hostname for OpenConnect/TLS handling.

## Build

- Version: `0.3.4`
- Version code: `7`
- ABI: `arm64-v8a`
- Android package: Smart Open Connect
- Signed with the persistent Smart Open Connect signing key used by the current 0.3.x builds
- Tested source commit: `3667e05781b96dca4415dd2465ae9a339c815db1`
- Tested GitHub Actions run: `34783154257`

The APK attached to this release is the exact artifact produced by that tested run. It is not rebuilt during publication.

## SHA-256

`a14a55bde1b4786999920e7584834fb568a0d86b8f159a5a1fc965480415fcb1  SmartOpenConnect-0.3.4-arm64.apk`
