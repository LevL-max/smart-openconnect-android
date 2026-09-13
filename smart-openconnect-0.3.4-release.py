#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "source"

p = ROOT / "app/build.gradle"
s = p.read_text(encoding="utf-8")
old = 'versionCode 6\n        versionName "0.3.3"'
new = 'versionCode 7\n        versionName "0.3.4"'
if s.count(old) != 1:
    raise SystemExit(f"0.3.4 version bump: expected exactly one match, found {s.count(old)}")
p.write_text(s.replace(old, new, 1), encoding="utf-8")

selector = ROOT / "app/src/main/java/net/openconnect_vpn/android/core/SmartRelaySelector.java"
text = selector.read_text(encoding="utf-8")
expected = '''    /** Cross-profile relay sharing is disabled in the public build. */\n    public static boolean isKeeneticCloudHost(String host) {\n        return false;\n    }'''
if expected not in text:
    raise SystemExit("0.3.4 public selector guard not found")

print("0.3.4 release overlay applied: versionCode 7, provider-neutral public relay discovery")
