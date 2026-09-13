#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "source"

p = ROOT / "app/build.gradle"
s = p.read_text(encoding="utf-8")
old = 'versionCode 4\n        versionName "0.3.1-relay-protect-hotfix"'
new = 'versionCode 5\n        versionName "0.3.2-stable-signing"'
count = s.count(old)
if count != 1:
    raise SystemExit(f"0.3.2 version bump: expected exactly one match, found {count}")
p.write_text(s.replace(old, new, 1), encoding="utf-8")

print("0.3.2 signing overlay applied: stable versionCode/versionName")
