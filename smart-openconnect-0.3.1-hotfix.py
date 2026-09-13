#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "source"


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text):
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# Bump test version for the relay probe hotfix.
p = "app/build.gradle"
s = read(p)
s = replace_once(
    s,
    'versionCode 3\n        versionName "0.3.0-apk2"',
    'versionCode 4\n        versionName "0.3.1-relay-protect-hotfix"',
    "version bump",
)
write(p, s)

# Android's VpnService.protect(Socket) needs a real socket file descriptor.
# A freshly constructed java.net.Socket can still be uncreated/unbound, which
# causes protect() to return false on some devices. Binding to an ephemeral
# local port forces creation of the underlying FD before protect(), while still
# keeping the socket unconnected so the subsequent connect is routed outside
# the VPN as intended.
p = "app/src/main/java/net/openconnect_vpn/android/core/SmartRelaySelector.java"
s = read(p)
s = replace_once(
    s,
    '''            raw = new Socket();\n            if (protector != null && !protector.protect(raw))\n                throw new java.io.IOException("VpnService.protect() failed");\n            raw.connect(new InetSocketAddress(ip, port), TCP_TIMEOUT_MS);''',
    '''            raw = new Socket();\n            raw.bind(new InetSocketAddress(0));\n            if (protector != null && !protector.protect(raw))\n                throw new java.io.IOException("VpnService.protect() failed");\n            raw.connect(new InetSocketAddress(ip, port), TCP_TIMEOUT_MS);''',
    "force socket FD before VpnService.protect",
)
write(p, s)

print("0.3.1 hotfix applied: create/bind socket FD before VpnService.protect()")
