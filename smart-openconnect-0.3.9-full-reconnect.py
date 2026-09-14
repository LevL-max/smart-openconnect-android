#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent / "source"


def read(rel):
    p = ROOT / rel
    if not p.exists():
        raise SystemExit(f"missing expected source file: {rel}")
    return p.read_text(encoding="utf-8")


def write(rel, text):
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# Build from the known-good 0.3.6 runtime (0.3.7 physical-network monitor is
# intentionally NOT applied) and move past rollback build versionCode 11.
p = "app/build.gradle"
s = read(p)
s = replace_once(
    s,
    'versionCode 9\n        versionName "0.3.6"',
    'versionCode 12\n        versionName "0.3.9"',
    "0.3.9 version bump",
)
write(p, s)

# ON must be a real new VPN session, not libopenconnect's in-place pause-based
# reconnect. Avoid briefly resuming the old session after a transient no-network
# interval; the full restart stops the old management thread instead.
p = "app/src/main/java/net/openconnect_vpn/android/core/DeviceStateReceiver.java"
s = read(p)
pattern = re.compile(
    r'(?P<indent>^[ \t]*)if \(mPaused\) \{[ \t]*\n'
    r'[ \t]*Log\.i\(TAG, "network changed after transient loss: clearing pause before reconnect"\);[ \t]*\n'
    r'[ \t]*mManagement\.resume\(\);[ \t]*\n'
    r'[ \t]*mPaused = false;[ \t]*\n'
    r'[ \t]*\}[ \t]*\n'
    r'[ \t]*Log\.i\(TAG, "network changed: reconnecting VPN on new network"\);[ \t]*\n'
    r'[ \t]*mManagement\.reconnect\(\);',
    flags=re.MULTILINE,
)
match = pattern.search(s)
if not match:
    raise SystemExit("DeviceStateReceiver full reconnect branch not found")
indent = match.group("indent")
replacement = (
    f'{indent}if (mPaused) {{\n'
    f'{indent}\tLog.i(TAG, "network changed after transient loss: full reconnect will clear pause");\n'
    f'{indent}\tmPaused = false;\n'
    f'{indent}}}\n'
    f'{indent}Log.i(TAG, "network changed: starting full VPN reconnect on new network");\n'
    f'{indent}mManagement.reconnect();'
)
s = s[:match.start()] + replacement + s[match.end():]
write(p, s)

# Reinterpret management reconnect as a service-level full session restart.
p = "app/src/main/java/net/openconnect_vpn/android/core/OpenConnectManagementThread.java"
s = read(p)
pattern = re.compile(
    r'\n\s*public void reconnect\(\) \{\s*\n'
    r'\s*log\("RECONNECT"\);.*?\n'
    r'\s*\}\s*\n'
    r'\s*@Override\s*\n\s*public void pause',
    flags=re.DOTALL,
)
replacement = '''\n    public void reconnect() {\n        log("RECONNECT: requesting full VPN session restart");\n        mOpenVPNService.restartVPNOnNetworkChange();\n    }\n\n    @Override\n    public void pause'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit(f"OpenConnectManagementThread reconnect method: expected 1 match, found {n}")
write(p, s)

# Keep OpenVpnService alive while the old management thread exits, then create a
# fresh thread using the same profile. The restart runnable waits for the old Java
# thread to be fully dead so a late threadDone() cannot tear down the new session.
p = "app/src/main/java/net/openconnect_vpn/android/core/OpenVpnService.java"
s = read(p)

marker = "private PendingIntent getMainActivityIntent()"
marker_pos = s.find(marker)
if marker_pos < 0:
    raise SystemExit("OpenVpnService getMainActivityIntent marker not found")
line_start = s.rfind("\n", 0, marker_pos) + 1

block = r'''    private boolean mNetworkRestartPending;
    private Runnable mNetworkRestartRunnable;

    private synchronized void cancelPendingNetworkRestart() {
        if (mNetworkRestartRunnable != null) {
            mHandler.removeCallbacks(mNetworkRestartRunnable);
        }
        mNetworkRestartRunnable = null;
        mNetworkRestartPending = false;
    }

    public void restartVPNOnNetworkChange() {
        final String uuid;
        synchronized (this) {
            if (mNetworkRestartPending) {
                Log.i(TAG, "NETWORK: full VPN restart already pending");
                return;
            }
            if (mUUID == null || mUUID.length() == 0) {
                Log.w(TAG, "NETWORK: cannot restart VPN without profile UUID");
                return;
            }
            mNetworkRestartPending = true;
            uuid = mUUID;
        }

        Log.i(TAG, "NETWORK: scheduling full VPN session restart");
        doStopVPN();

        final Runnable restart = new Runnable() {
            private int waits;

            @Override
            public void run() {
                synchronized (OpenVpnService.this) {
                    if (!mNetworkRestartPending) {
                        return;
                    }
                }

                // Do not race a late threadDone() from the old session against
                // the replacement session. Wait until the old Java thread is
                // truly no longer alive before assigning mVPN/mVPNThread again.
                if (mVPNThread != null && mVPNThread.isAlive()) {
                    waits++;
                    if (waits >= 50) {
                        Log.e(TAG, "NETWORK: old VPN thread did not terminate; aborting reconnect");
                        synchronized (OpenVpnService.this) {
                            mNetworkRestartPending = false;
                            mNetworkRestartRunnable = null;
                        }
                        ProfileManager.setConnectedVpnProfileDisconnected();
                        stopSelf();
                        return;
                    }
                    mHandler.postDelayed(this, 100);
                    return;
                }

                VpnProfile restartProfile = ProfileManager.get(uuid);
                if (restartProfile == null) {
                    Log.e(TAG, "NETWORK: profile disappeared before VPN restart");
                    synchronized (OpenVpnService.this) {
                        mNetworkRestartPending = false;
                        mNetworkRestartRunnable = null;
                    }
                    ProfileManager.setConnectedVpnProfileDisconnected();
                    stopSelf();
                    return;
                }

                unregisterReceivers();

                OpenConnectManagementThread next = new OpenConnectManagementThread(
                        getApplicationContext(), restartProfile, OpenVpnService.this);
                Thread nextThread = new Thread(next, "OpenVPNManagementThread");

                synchronized (OpenVpnService.this) {
                    profile = restartProfile;
                    mUUID = uuid;
                    mVPN = next;
                    mVPNThread = nextThread;
                    mNetworkRestartPending = false;
                    mNetworkRestartRunnable = null;
                }

                registerDeviceStateReceiver(next);
                ProfileManager.setConnectedVpnProfile(restartProfile);
                Log.i(TAG, "NETWORK: starting fresh VPN session on new network");
                nextThread.start();
            }
        };

        synchronized (this) {
            mNetworkRestartRunnable = restart;
        }
        // Give Android a short moment to finish the route/interface handoff
        // before the replacement session reruns Smart Relay and authentication.
        mHandler.postDelayed(restart, 600);
    }

'''
s = s[:line_start] + block + s[line_start:]

# When the old thread terminates as part of a controlled restart, keep the service
# alive. The delayed restart runnable owns the lifecycle until a new thread starts.
pattern = re.compile(r'(?P<indent>^[ \t]*)public synchronized void threadDone\(\) \{[ \t]*\n', re.MULTILINE)
match = pattern.search(s)
if not match:
    raise SystemExit("OpenVpnService threadDone marker not found")
indent = match.group("indent")
insert = (
    match.group(0) +
    f'{indent}\tif (mNetworkRestartPending) {{\n'
    f'{indent}\t\tLog.i(TAG, "NETWORK: old VPN thread terminated; keeping service for restart");\n'
    f'{indent}\t\tmVPN = null;\n'
    f'{indent}\t\treturn;\n'
    f'{indent}\t}}\n'
)
s = s[:match.start()] + insert + s[match.end():]

# Manual user stop must never be followed by a delayed automatic restart.
pattern = re.compile(
    r'(?P<indent>^[ \t]*)public void stopVPN\(\) \{[ \t]*\n'
    r'[ \t]*killVPNThread\(false\);[ \t]*\n'
    r'[ \t]*ProfileManager\.setConnectedVpnProfileDisconnected\(\);[ \t]*\n'
    r'[ \t]*\}',
    re.MULTILINE,
)
match = pattern.search(s)
if not match:
    raise SystemExit("OpenVpnService stopVPN method not found")
indent = match.group("indent")
replacement = (
    f'{indent}public void stopVPN() {{\n'
    f'{indent}\tcancelPendingNetworkRestart();\n'
    f'{indent}\tkillVPNThread(false);\n'
    f'{indent}\tProfileManager.setConnectedVpnProfileDisconnected();\n'
    f'{indent}}}'
)
s = s[:match.start()] + replacement + s[match.end():]

# Service destruction also cancels any delayed reconnect runnable.
pattern = re.compile(
    r'(?P<head>(?P<indent>^[ \t]*)public void onDestroy\(\) \{[ \t]*\n)'
    r'(?P<bodyindent>[ \t]*)killVPNThread\(true\);',
    re.MULTILINE,
)
match = pattern.search(s)
if not match:
    raise SystemExit("OpenVpnService onDestroy kill marker not found")
bodyindent = match.group("bodyindent")
replacement = match.group("head") + bodyindent + 'cancelPendingNetworkRestart();\n' + bodyindent + 'killVPNThread(true);'
s = s[:match.start()] + replacement + s[match.end():]

write(p, s)

print("0.3.9 overlay applied: network-change ON waits for old thread then starts a fresh OpenConnect session; OFF remains stopVPN")
