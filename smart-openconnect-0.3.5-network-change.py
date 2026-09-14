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
    'versionCode 7\n        versionName "0.3.4"',
    'versionCode 8\n        versionName "0.3.5"',
    "0.3.5 version bump",
)
write(p, s)

# Network-change semantics.
# Upstream caches netchangereconnect and only does something when it is true.
# Smart Open Connect semantics are explicit:
#   ON  -> reconnect on the new network
#   OFF -> disconnect the VPN on network change
# Read the preference at the actual network-change event so Settings does not
# need to push a runtime PREF_CHANGED broadcast for this option.
p = "app/src/main/java/net/openconnect_vpn/android/core/DeviceStateReceiver.java"
s = read(p)

# Remove cached copy of this preference if present in the v1.12 source.
s, n = re.subn(r'^\s*private boolean mNetchangeReconnect;\s*\n', '', s,
               count=1, flags=re.MULTILINE)
if n != 1:
    raise SystemExit(f"DeviceStateReceiver cached preference field: expected 1 match, found {n}")

s, n = re.subn(
    r'^\s*mNetchangeReconnect\s*=\s*mPrefs\.getBoolean\("netchangereconnect",\s*true\);\s*\n',
    '', s, count=1, flags=re.MULTILINE)
if n != 1:
    raise SystemExit(f"DeviceStateReceiver cached preference read: expected 1 match, found {n}")

pattern = re.compile(
    r'(?P<indent>\s*)int networkType = networkInfo\.getType\(\);\n'
    r'(?P=indent)if \(mNetworkType != -1 && mNetworkType != networkType\) \{\n'
    r'(?P=indent)\s*if \(!mPaused && mNetchangeReconnect\) \{\n'
    r'(?P=indent)\s*Log\.i\(TAG, "reconnecting due to network type change"\);\n'
    r'(?P=indent)\s*mManagement\.reconnect\(\);\n'
    r'(?P=indent)\s*\}\n'
    r'(?P=indent)\}',
    flags=re.MULTILINE,
)

match = pattern.search(s)
if not match:
    raise SystemExit("DeviceStateReceiver network-change block not found")
indent = match.group('indent')
replacement = (
    f'{indent}int networkType = networkInfo.getType();\n'
    f'{indent}if (mNetworkType != -1 && mNetworkType != networkType) {{\n'
    f'{indent}\tif (!mPaused) {{\n'
    f'{indent}\t\tboolean reconnectOnChange = mPrefs.getBoolean("netchangereconnect", true);\n'
    f'{indent}\t\tif (reconnectOnChange) {{\n'
    f'{indent}\t\t\tLog.i(TAG, "network changed: reconnecting VPN on new network");\n'
    f'{indent}\t\t\tmManagement.reconnect();\n'
    f'{indent}\t\t}} else {{\n'
    f'{indent}\t\t\tLog.i(TAG, "network changed: reconnect disabled; disconnecting VPN");\n'
    f'{indent}\t\t\tmManagement.stopVPN();\n'
    f'{indent}\t\t}}\n'
    f'{indent}\t}}\n'
    f'{indent}}}'
)
s = s[:match.start()] + replacement + s[match.end():]
write(p, s)

# Settings responsiveness.
# netchangereconnect only affects a future network-change event, so do not send
# PREF_CHANGED into the active VPN management thread when the checkbox toggles.
# screenoff and trace_log retain their existing live-update behavior.
p = "app/src/main/java/net/openconnect_vpn/android/fragments/GeneralSettings.java"
s = read(p)
s = replace_once(
    s,
    'for (String s : new String[] { "netchangereconnect", "screenoff", "trace_log" }) {',
    'for (String s : new String[] { "screenoff", "trace_log" }) {',
    "Settings runtime preference broadcast list",
)
write(p, s)

# Make the checkbox behavior explicit in the UI.
p = "app/src/main/res/values/strings.xml"
s = read(p)
pattern = re.compile(r'<string name="netchange_summary">.*?</string>')
replacement = ('<string name="netchange_summary">When enabled, changing networks reconnects the VPN on the new network. '
               'When disabled, changing networks disconnects the VPN.</string>')
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit(f"netchange_summary: expected 1 match, found {n}")
write(p, s)

print("0.3.5 overlay applied: reconnect-or-disconnect network change semantics and responsive Settings toggle")
