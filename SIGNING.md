# Smart OpenConnect stable debug signing

All future test APKs should be signed with one persistent debug key so Android can install a new version over the previous one without requiring uninstall/reinstall.

## GitHub Actions secret

Repository Actions must contain this secret:

`SMARTCONNECT_DEBUG_KEYSTORE_B64`

The secret value is the base64-encoded contents of the private `smartconnect-debug.keystore` file. The keystore itself must **not** be committed to this public repository.

The workflow restores the secret to:

`~/.android/debug.keystore`

The keystore intentionally uses Android's conventional debug credentials:

- alias: `androiddebugkey`
- store password: `android`
- key password: `android`

Only the keystore bytes are secret. The passwords above are conventional debug values and are not intended as the security boundary.

## Certificate fingerprint

SHA-256 certificate fingerprint:

`D5:1B:2B:0C:B3:20:AA:D1:62:61:64:1A:1D:CE:C7:CE:92:CC:D6:A9:DC:29:DD:70:2D:B9:5E:8B:58:B1:C2:CC`

Validity: 2026-09-13 through 2056-09-05.

## Why this is required

GitHub-hosted runners are disposable. If Gradle creates a fresh debug keystore on each build, each APK is signed by a different certificate. Android then rejects an update with `INSTALL_FAILED_UPDATE_INCOMPATIBLE` / conflicting signature even though the application ID is unchanged.

Restoring the same private debug keystore before Gradle builds the APK makes every later Smart OpenConnect test build use the same signing certificate, allowing normal in-place updates while preserving profiles, saved credentials, and app settings.
