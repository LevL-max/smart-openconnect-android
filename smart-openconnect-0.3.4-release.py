#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "source"


def replace_once(path, old, new, label):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# Version bump.
p = ROOT / "app/build.gradle"
replace_once(
    p,
    'versionCode 6\n        versionName "0.3.3"',
    'versionCode 7\n        versionName "0.3.4"',
    "0.3.4 version bump",
)

# Public build must not contain provider-specific cross-profile relay matching.
selector = ROOT / "app/src/main/java/net/openconnect_vpn/android/core/SmartRelaySelector.java"
text = selector.read_text(encoding="utf-8")
expected = '''    /** Cross-profile relay sharing is disabled in the public build. */\n    public static boolean isKeeneticCloudHost(String host) {\n        return false;\n    }'''
if expected not in text:
    raise SystemExit("0.3.4 public selector guard not found")

# GUI hotfix 1: selecting a profile must not reorder the recent-profile strip.
# MRU is updated only when Connect is pressed and the profile is actually used.
connect = ROOT / "app/src/main/java/net/openconnect_vpn/android/fragments/ConnectFragment.java"
replace_once(
    connect,
    '''    private void selectProfile(VpnProfile profile) {\n        if (profile != null) {\n            mAppPrefs.edit().putString(PREF_SELECTED_PROFILE, profile.getUUIDString()).apply();\n            rememberRecent(profile);\n        }\n    }\n''',
    '''    private void selectProfile(VpnProfile profile) {\n        if (profile != null)\n            mAppPrefs.edit().putString(PREF_SELECTED_PROFILE, profile.getUUIDString()).commit();\n    }\n''',
    "stable profile selection",
)

replace_once(
    connect,
    '''                selectProfile(profile);\n                Intent intent = new Intent(getActivity(), GrantPermissionsActivity.class);''',
    '''                selectProfile(profile);\n                rememberRecent(profile);\n                updateRecentProfiles(profile);\n                Intent intent = new Intent(getActivity(), GrantPermissionsActivity.class);''',
    "remember profile on connect",
)

replace_once(
    connect,
    '''        if (selected != null && recent.isEmpty()) {\n            recent.add(selected);\n            rememberRecent(selected);\n        }''',
    '''        if (selected != null && recent.isEmpty())\n            recent.add(selected);''',
    "render without mutating MRU",
)

# GUI hotfix 2: selecting from Servers must be committed synchronously before
# returning to Connect, so the newly created ConnectFragment sees the new UUID.
servers = ROOT / "app/src/main/java/net/openconnect_vpn/android/fragments/VPNProfileList.java"
replace_once(
    servers,
    '''\t\t\t\t\tPreferenceManager.getDefaultSharedPreferences(getActivity()).edit()\n\t\t\t\t\t\t.putString(ConnectFragment.PREF_SELECTED_PROFILE, profile.getUUIDString()).apply();\n\t\t\t\t\t((MainActivity)getActivity()).showConnectTab();''',
    '''\t\t\t\t\tPreferenceManager.getDefaultSharedPreferences(getActivity()).edit()\n\t\t\t\t\t\t.putString(ConnectFragment.PREF_SELECTED_PROFILE, profile.getUUIDString()).commit();\n\t\t\t\t\t((MainActivity)getActivity()).showConnectTab();''',
    "server-list synchronous selection",
)

# GUI hotfix 3: exactly three fixed-width recent-profile slots. Zero min width
# prevents long profile names/background minimums from pushing a chip off-screen.
layout = ROOT / "app/src/main/res/layout/connect.xml"
replace_once(
    layout,
    '''        android:layout_width="match_parent"\n        android:layout_height="46dp"\n        android:layout_marginTop="6dp"\n        android:gravity="center"\n        android:orientation="horizontal">''',
    '''        android:layout_width="match_parent"\n        android:layout_height="46dp"\n        android:layout_marginTop="6dp"\n        android:gravity="center"\n        android:orientation="horizontal"\n        android:weightSum="3">''',
    "recent row fixed weight sum",
)

text = layout.read_text(encoding="utf-8")
for idx in (1, 2, 3):
    old = f'<TextView android:id="@+id/recent_profile_{idx}" android:layout_width="0dp"'
    new = f'<TextView android:id="@+id/recent_profile_{idx}" android:layout_width="0dp" android:minWidth="0dp"'
    if text.count(old) != 1:
        raise SystemExit(f"recent profile {idx} width guard: expected exactly one match, found {text.count(old)}")
    text = text.replace(old, new, 1)
if text.count('android:id="@+id/recent_profile_') != 3:
    raise SystemExit("recent profile strip must contain exactly three slots")
layout.write_text(text, encoding="utf-8")

print("0.3.4 release overlay applied: stable server selection, stable MRU strip, provider-neutral relay discovery")
