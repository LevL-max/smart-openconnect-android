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


# Version bump.
p = "app/build.gradle"
s = read(p)
s = replace_once(
    s,
    'versionCode 8\n        versionName "0.3.5"',
    'versionCode 9\n        versionName "0.3.6"',
    "0.3.6 version bump",
)
write(p, s)

# 0.3.5 correctly made ON=reconnect and OFF=disconnect, but retained the old
# !mPaused gate. Android commonly reports a short no-network interval while
# switching cellular <-> Wi-Fi. That interval calls pause(), so when the new
# network arrives mPaused is true and the reconnect branch is skipped.
#
# When a different network type becomes active:
#   ON  -> clear the transient pause, then force reconnect on the new network.
#   OFF -> stop the VPN, preserving the already validated 0.3.5 behavior.
p = "app/src/main/java/net/openconnect_vpn/android/core/DeviceStateReceiver.java"
s = read(p)

pattern = re.compile(
    r'(?P<indent>^[ \t]*)if \(mNetworkType != -1 && mNetworkType != networkType\) \{[ \t]*\n'
    r'[ \t]*if \(!mPaused\) \{[ \t]*\n'
    r'[ \t]*boolean reconnectOnChange = mPrefs\.getBoolean\("netchangereconnect", true\);[ \t]*\n'
    r'[ \t]*if \(reconnectOnChange\) \{[ \t]*\n'
    r'[ \t]*Log\.i\(TAG, "network changed: reconnecting VPN on new network"\);[ \t]*\n'
    r'[ \t]*mManagement\.reconnect\(\);[ \t]*\n'
    r'[ \t]*\} else \{[ \t]*\n'
    r'[ \t]*Log\.i\(TAG, "network changed: reconnect disabled; disconnecting VPN"\);[ \t]*\n'
    r'[ \t]*mManagement\.stopVPN\(\);[ \t]*\n'
    r'[ \t]*\}[ \t]*\n'
    r'[ \t]*\}[ \t]*\n'
    r'[ \t]*\}',
    flags=re.MULTILINE,
)

match = pattern.search(s)
if not match:
    raise SystemExit("paused network-change reconnect block not found")
indent = match.group("indent")
replacement = (
    f'{indent}if (mNetworkType != -1 && mNetworkType != networkType) {{\n'
    f'{indent}\tboolean reconnectOnChange = mPrefs.getBoolean("netchangereconnect", true);\n'
    f'{indent}\tif (reconnectOnChange) {{\n'
    f'{indent}\t\tif (mPaused) {{\n'
    f'{indent}\t\t\tLog.i(TAG, "network changed after transient loss: clearing pause before reconnect");\n'
    f'{indent}\t\t\tmManagement.resume();\n'
    f'{indent}\t\t\tmPaused = false;\n'
    f'{indent}\t\t}}\n'
    f'{indent}\t\tLog.i(TAG, "network changed: reconnecting VPN on new network");\n'
    f'{indent}\t\tmManagement.reconnect();\n'
    f'{indent}\t}} else {{\n'
    f'{indent}\t\tLog.i(TAG, "network changed: reconnect disabled; disconnecting VPN");\n'
    f'{indent}\t\tmManagement.stopVPN();\n'
    f'{indent}\t\tmPaused = false;\n'
    f'{indent}\t}}\n'
    f'{indent}}}'
)
s = s[:match.start()] + replacement + s[match.end():]
write(p, s)

print("0.3.6 overlay applied: reconnect survives transient no-network pause during cellular/Wi-Fi handoff")
