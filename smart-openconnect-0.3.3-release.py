#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent / "source"


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# 1) Clean semantic version for the public release.
p = "app/build.gradle"
s = read(p)
old = 'versionCode 5\n        versionName "0.3.2-stable-signing"'
new = 'versionCode 6\n        versionName "0.3.3"'
if s.count(old) != 1:
    raise SystemExit(f"0.3.3 version bump: expected exactly one match, found {s.count(old)}")
write(p, s.replace(old, new, 1))

# 2) Public-facing product label. Version is kept in Android package metadata,
# not embedded into the launcher label, so future upgrades remain clean.
p = "app/src/main/res/values/strings.xml"
s = read(p)
pattern = r'(<string\s+name="app"[^>]*>)(.*?)(</string>)'
m = re.search(pattern, s, flags=re.DOTALL)
if not m:
    raise SystemExit('0.3.3 label: <string name="app"> not found')
s = s[:m.start()] + m.group(1) + "Smart Open Connect" + m.group(3) + s[m.end():]
write(p, s)

# 3) Proper Android adaptive launcher icon. Previous builds referenced a legacy
# vector drawable directly; Samsung/One UI therefore placed it on a white icon
# tray. Keep the existing relay-path artwork as foreground, but provide a dark
# adaptive background so the launcher mask itself is the icon boundary.
write("app/src/main/res/values/smartconnect_icon.xml", '''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="smartconnect_icon_background">#111A3E</color>
</resources>
''')

write("app/src/main/res/mipmap-anydpi-v26/ic_smartconnect_launcher.xml", '''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/smartconnect_icon_background" />
    <foreground android:drawable="@drawable/ic_smartconnect_launcher" />
</adaptive-icon>
''')

# API 23-25 fallback keeps the same artwork without changing its visual design.
write("app/src/main/res/mipmap-anydpi/ic_smartconnect_launcher.xml", '''<?xml version="1.0" encoding="utf-8"?>
<inset xmlns:android="http://schemas.android.com/apk/res/android"
    android:drawable="@drawable/ic_smartconnect_launcher"
    android:inset="0dp" />
''')

p = "app/src/main/AndroidManifest.xml"
s = read(p)
old = ('android:icon="@drawable/ic_smartconnect_launcher"\n'
       '        android:roundIcon="@drawable/ic_smartconnect_launcher"')
new = ('android:icon="@mipmap/ic_smartconnect_launcher"\n'
       '        android:roundIcon="@mipmap/ic_smartconnect_launcher"')
if s.count(old) != 1:
    raise SystemExit(f"0.3.3 adaptive icon manifest: expected one application icon pair, found {s.count(old)}")
write(p, s.replace(old, new, 1))

# 4) Normalize two benign native OpenConnect messages in the Android-visible
# log. Do not suppress security-relevant TLS/certificate messages. The original
# connection behaviour is untouched; only the log wording/level is normalized.
p = "app/src/main/java/net/openconnect_vpn/android/core/VPNLog.java"
s = read(p)
needle = "\tpublic void add(int level, String msg) {\n"
if s.count(needle) != 1:
    # Maintained source may use spaces instead of tabs. Fall back to a strict
    # regex matching only the method declaration.
    matches = list(re.finditer(r'(?m)^(\s*)public void add\(int level, String msg\) \{\s*$', s))
    if len(matches) != 1:
        raise SystemExit(f"0.3.3 VPNLog.add: expected exactly one method, found {len(matches)}")
    m = matches[0]
    indent = m.group(1) + "    "
    insert_at = m.end()
    block = ("\n" + indent + 'if (msg != null && msg.contains("Failed to open /dev/vhost-net")) {\n'
             + indent + '    level = LEVEL_INFO;\n'
             + indent + '    msg = "INFO: vhost-net unavailable on Android; using standard TUN";\n'
             + indent + '} else if (msg != null && msg.contains("No DTLS address")) {\n'
             + indent + '    level = LEVEL_INFO;\n'
             + indent + '    msg = "INFO: DTLS address not provided; using CSTP/TCP";\n'
             + indent + '}\n')
    s = s[:insert_at] + block + s[insert_at:]
else:
    block = (needle
             + '\t\tif (msg != null && msg.contains("Failed to open /dev/vhost-net")) {\n'
             + '\t\t\tlevel = LEVEL_INFO;\n'
             + '\t\t\tmsg = "INFO: vhost-net unavailable on Android; using standard TUN";\n'
             + '\t\t} else if (msg != null && msg.contains("No DTLS address")) {\n'
             + '\t\t\tlevel = LEVEL_INFO;\n'
             + '\t\t\tmsg = "INFO: DTLS address not provided; using CSTP/TCP";\n'
             + '\t\t}\n')
    s = s.replace(needle, block, 1)
write(p, s)

print("0.3.3 release overlay applied:")
print("- versionCode 6 / versionName 0.3.3")
print("- app label Smart Open Connect")
print("- adaptive launcher icon with dark background")
print("- benign Android vhost-net/DTLS log messages normalized")
