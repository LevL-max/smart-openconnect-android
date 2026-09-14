#!/usr/bin/env python3
from pathlib import Path

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
old = '''        if (mNetworkType != -1 && mNetworkType != networkType) {
        \tif (!mPaused) {
        \t\tboolean reconnectOnChange = mPrefs.getBoolean("netchangereconnect", true);
        \t\tif (reconnectOnChange) {
        \t\t\tLog.i(TAG, "network changed: reconnecting VPN on new network");
        \t\t\tmManagement.reconnect();
        \t\t} else {
        \t\t\tLog.i(TAG, "network changed: reconnect disabled; disconnecting VPN");
        \t\t\tmManagement.stopVPN();
        \t\t}
        \t}
        }'''
new = '''        if (mNetworkType != -1 && mNetworkType != networkType) {
        \tboolean reconnectOnChange = mPrefs.getBoolean("netchangereconnect", true);
        \tif (reconnectOnChange) {
        \t\tif (mPaused) {
        \t\t\tLog.i(TAG, "network changed after transient loss: clearing pause before reconnect");
        \t\t\tmManagement.resume();
        \t\t\tmPaused = false;
        \t\t}
        \t\tLog.i(TAG, "network changed: reconnecting VPN on new network");
        \t\tmManagement.reconnect();
        \t} else {
        \t\tLog.i(TAG, "network changed: reconnect disabled; disconnecting VPN");
        \t\tmManagement.stopVPN();
        \t\tmPaused = false;
        \t}
        }'''
s = replace_once(s, old, new, "paused network-change reconnect block")
write(p, s)

print("0.3.6 overlay applied: reconnect survives transient no-network pause during cellular/Wi-Fi handoff")
