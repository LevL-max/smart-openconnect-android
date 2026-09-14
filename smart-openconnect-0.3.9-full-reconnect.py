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
# interval; stopVPN() in the service-side full restart clears mRequestPause.
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
# fresh thread using the same profile. This reruns Smart Relay + authentication on
# the new uplink. A pending restart is cancelled by manual stop/service destroy.
p = "app/src/main/java/net/openconnect_vpn/android/core/OpenVpnService.java"
s = read(p)

s = replace_once(
    s,
    '    private OpenConnectManagementThread mVPN;\n',
    '    private OpenConnectManagementThread mVPN;\n'
    '    private boolean mNetworkRestartPending;\n'
    '    private Runnable mNetworkRestartRunnable;\n',
    "OpenVpnService restart fields",
)

# Add helpers before the existing main-activity PendingIntent helper.
marker = '    private PendingIntent getMainActivityIntent() {\n'
if marker not in s:
    raise SystemExit("OpenVpnService getMainActivityIntent marker not found")
helper = r'''    private synchronized void cancelPendingNetworkRestart() {
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
            @Override
            public void run() {
                // Ensure the old management thread has completely exited before
                // replacing service fields with a new session.
                killVPNThread(true);

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
        // The CONNECTED broadcast means a new uplink exists, but a short delay
        // lets Android finish route/interface handoff before Smart Relay probes.
        mHandler.postDelayed(restart, 600);
    }

'''
s = s.replace(marker, helper + marker, 1)

# When the old thread terminates as part of the controlled restart, do not stop
# the service. The scheduled restart owns the service lifecycle at that point.
thread_done = '    public synchronized void threadDone() {\n'
if thread_done not in s:
    raise SystemExit("OpenVpnService threadDone marker not found")
s = s.replace(
    thread_done,
    thread_done +
    '        if (mNetworkRestartPending) {\n'
    '            Log.i(TAG, "NETWORK: old VPN thread terminated; keeping service for restart");\n'
    '            mVPN = null;\n'
    '            return;\n'
    '        }\n',
    1,
)

# Manual user stop must never be followed by a delayed automatic restart.
old_stop = '''    public void stopVPN() {\n        killVPNThread(false);\n        ProfileManager.setConnectedVpnProfileDisconnected();\n    }'''
new_stop = '''    public void stopVPN() {\n        cancelPendingNetworkRestart();\n        killVPNThread(false);\n        ProfileManager.setConnectedVpnProfileDisconnected();\n    }'''
s = replace_once(s, old_stop, new_stop, "OpenVpnService manual stop cancels restart")

# Service destruction also cancels any delayed reconnect runnable.
pattern = re.compile(r'(public void onDestroy\(\) \{\s*\n)(\s*)killVPNThread\(true\);')
match = pattern.search(s)
if not match:
    raise SystemExit("OpenVpnService onDestroy kill marker not found")
indent = match.group(2)
s = s[:match.start()] + match.group(1) + indent + 'cancelPendingNetworkRestart();\n' + indent + 'killVPNThread(true);' + s[match.end():]

write(p, s)

print("0.3.9 overlay applied: network-change ON uses a fresh OpenConnect session; OFF remains stopVPN")
