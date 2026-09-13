#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "source"


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text):
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text, old, new, label):
    count = text.count(old)
    if count < 1:
        raise SystemExit(f"{label}: expected a match, found 0")
    # The relay-clear statement intentionally occurs in two branches. Replace
    # its first occurrence here; the second replacement later becomes unique.
    if count > 1 and label != "relay remove on native failure":
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# Version bump for APK2 device testing.
p = "app/build.gradle"
s = read(p)
s = replace_once(s, 'versionCode 2\n        versionName "0.2.0-ui-preview"',
                 'versionCode 3\n        versionName "0.3.0-apk2"', "version bump")
write(p, s)

# Apply the Smart Connect dark visual system to Settings/editor/support screens.
p = "app/src/main/AndroidManifest.xml"
s = read(p)
s = replace_once(s,
                 'android:name="net.openconnect_vpn.android.Application"',
                 'android:name="net.openconnect_vpn.android.Application"\n        android:theme="@style/SmartConnectAppTheme"',
                 "application theme")
write(p, s)

p = "app/src/main/res/values/styles.xml"
s = read(p)
style_block = '''\n    <style name="SmartConnectAppTheme" parent="android:style/Theme.Material">\n        <item name="android:fontFamily">sans</item>\n        <item name="android:windowBackground">@color/app_background</item>\n        <item name="android:colorAccent">@color/smart_purple_light</item>\n        <item name="android:statusBarColor">@color/app_background</item>\n        <item name="android:navigationBarColor">@color/bottom_bar</item>\n        <item name="android:windowLightStatusBar">false</item>\n        <item name="android:windowActionModeOverlay">true</item>\n    </style>\n'''
s = replace_once(s, "\n</resources>", style_block + "\n</resources>", "settings theme style")
write(p, s)

# One-tap authentication. Upstream already persists username/password. Normally
# earlyReturn() only submits the saved form when batch_mode is enabled. Smart
# Connect submits a complete saved form on the first presentation. If the same
# form comes back, it falls back to the normal interactive dialog so a stale or
# wrong password can never cause an automatic retry loop.
p = "app/src/main/java/net/openconnect_vpn/android/AuthFormHandler.java"
s = read(p)
s = replace_once(s,
                 "\tprivate boolean mAllFilled = true;\n",
                 "\tprivate boolean mAllFilled = true;\n\tprivate boolean mRepeatedForm;\n",
                 "auth repeated-form field")
s = replace_once(s,
                 "\t\tformPfx = getFormPrefix(mForm);\n\t\tnoSave = getBooleanPref(\"disable_username_caching\");",
                 "\t\tformPfx = getFormPrefix(mForm);\n\t\tmRepeatedForm = formPfx.equals(lastFormDigest);\n\t\tnoSave = getBooleanPref(\"disable_username_caching\");",
                 "auth repeated-form init")
s = replace_once(s,
                 "\t\tif (batchMode != BATCH_MODE_EMPTY_ONLY && batchMode != BATCH_MODE_ENABLED) {\n\t\t\treturn null;\n\t\t}\n\n\t\t// do a quick pass through all prompts to see if we can fill in the",
                 "\t\tif (batchMode != BATCH_MODE_EMPTY_ONLY && batchMode != BATCH_MODE_ENABLED && mRepeatedForm) {\n\t\t\treturn null;\n\t\t}\n\n\t\t// Smart Connect one-tap: when all answers are already stored locally,\n\t\t// submit them once without showing the auth dialog.\n\n\t\t// do a quick pass through all prompts to see if we can fill in the",
                 "auth one-tap early return")
write(p, s)

# Relay IP persistence. Keep the profile-local value and a UUID-keyed app-level
# fallback. commit() makes the profile value visible before the next UI callback
# and the UUID key prevents another profile's relay from being displayed.
p = "app/src/main/java/net/openconnect_vpn/android/core/OpenConnectManagementThread.java"
s = read(p)
s = replace_once(s,
                 'mPrefs.edit().remove("smart_relay_last_selected_ip").apply();',
                 'mPrefs.edit().remove("smart_relay_last_selected_ip").commit();\n\t\t\t\t\tmAppPrefs.edit().remove("smart_relay_last_selected_ip_" + mProfile.getUUIDString()).apply();',
                 "relay remove on native failure")
s = replace_once(s,
                 'mPrefs.edit().putString("smart_relay_last_selected_ip", relay.selectedIp).apply();',
                 'mPrefs.edit().putString("smart_relay_last_selected_ip", relay.selectedIp).commit();\n\t\t\t\t\tmAppPrefs.edit().putString("smart_relay_last_selected_ip_" + mProfile.getUUIDString(), relay.selectedIp).apply();',
                 "relay persist selected")
s = replace_once(s,
                 'mPrefs.edit().remove("smart_relay_last_selected_ip").apply();',
                 'mPrefs.edit().remove("smart_relay_last_selected_ip").commit();\n\t\t\t\tmAppPrefs.edit().remove("smart_relay_last_selected_ip_" + mProfile.getUUIDString()).apply();',
                 "relay remove no selection")
write(p, s)

# Connect screen: maintain an MRU list of three profiles and expose them as
# one-tap selectors immediately above the Connect button.
p = "app/src/main/java/net/openconnect_vpn/android/fragments/ConnectFragment.java"
s = read(p)
s = replace_once(s,
                 "    public static final String PREF_SELECTED_PROFILE = \"selected_profile_uuid\";\n",
                 "    public static final String PREF_SELECTED_PROFILE = \"selected_profile_uuid\";\n    private static final String PREF_RECENT_PROFILES = \"recent_profile_uuids\";\n",
                 "recent pref constant")
s = replace_once(s,
                 "    private TextView mRelay;\n",
                 "    private TextView mRelay;\n    private TextView mRecent1;\n    private TextView mRecent2;\n    private TextView mRecent3;\n",
                 "recent view fields")
s = replace_once(s,
                 "        mRelay = (TextView)mView.findViewById(R.id.smart_relay_state);\n",
                 "        mRelay = (TextView)mView.findViewById(R.id.smart_relay_state);\n        mRecent1 = (TextView)mView.findViewById(R.id.recent_profile_1);\n        mRecent2 = (TextView)mView.findViewById(R.id.recent_profile_2);\n        mRecent3 = (TextView)mView.findViewById(R.id.recent_profile_3);\n        bindRecentClick(mRecent1);\n        bindRecentClick(mRecent2);\n        bindRecentClick(mRecent3);\n",
                 "recent view binding")
s = replace_once(s,
                 "    private void selectProfile(VpnProfile profile) {\n        if (profile != null)\n            mAppPrefs.edit().putString(PREF_SELECTED_PROFILE, profile.getUUIDString()).apply();\n    }\n",
                 '''    private void selectProfile(VpnProfile profile) {\n        if (profile != null) {\n            mAppPrefs.edit().putString(PREF_SELECTED_PROFILE, profile.getUUIDString()).apply();\n            rememberRecent(profile);\n        }\n    }\n\n    private void rememberRecent(VpnProfile profile) {\n        String uuid = profile.getUUIDString();\n        ArrayList<String> ids = new ArrayList<String>();\n        ids.add(uuid);\n        String old = mAppPrefs.getString(PREF_RECENT_PROFILES, "");\n        for (String id : old.split(",")) {\n            id = id.trim();\n            if (id.length() > 0 && !id.equals(uuid) && ProfileManager.get(id) != null)\n                ids.add(id);\n            if (ids.size() == 3)\n                break;\n        }\n        StringBuilder out = new StringBuilder();\n        for (String id : ids) {\n            if (out.length() > 0) out.append(',');\n            out.append(id);\n        }\n        mAppPrefs.edit().putString(PREF_RECENT_PROFILES, out.toString()).apply();\n    }\n\n    private void bindRecentClick(final TextView view) {\n        view.setOnClickListener(new View.OnClickListener() {\n            @Override public void onClick(View v) {\n                Object tag = view.getTag();\n                if (!(tag instanceof String)) return;\n                VpnProfile profile = ProfileManager.get((String)tag);\n                if (profile == null) return;\n                selectProfile(profile);\n                updateUI(mConn == null ? null : mConn.service);\n            }\n        });\n    }\n\n    private void updateRecentProfiles(VpnProfile selected) {\n        ArrayList<VpnProfile> recent = new ArrayList<VpnProfile>();\n        String raw = mAppPrefs.getString(PREF_RECENT_PROFILES, "");\n        for (String id : raw.split(",")) {\n            VpnProfile profile = ProfileManager.get(id.trim());\n            if (profile != null) recent.add(profile);\n            if (recent.size() == 3) break;\n        }\n        if (selected != null && recent.isEmpty()) {\n            recent.add(selected);\n            rememberRecent(selected);\n        }\n        setRecent(mRecent1, recent.size() > 0 ? recent.get(0) : null, selected);\n        setRecent(mRecent2, recent.size() > 1 ? recent.get(1) : null, selected);\n        setRecent(mRecent3, recent.size() > 2 ? recent.get(2) : null, selected);\n    }\n\n    private void setRecent(TextView view, VpnProfile profile, VpnProfile selected) {\n        if (profile == null) {\n            view.setVisibility(View.GONE);\n            view.setTag(null);\n            return;\n        }\n        view.setVisibility(View.VISIBLE);\n        view.setText(profile.getName());\n        view.setTag(profile.getUUIDString());\n        boolean active = selected != null && selected.getUUIDString().equals(profile.getUUIDString());\n        view.setAlpha(active ? 1.0f : 0.72f);\n    }\n''',
                 "recent selector methods")
s = replace_once(s,
                 "        if (service != null) {\n            mConnectionState = service.getConnectionState();",
                 "        updateRecentProfiles(p);\n\n        if (service != null) {\n            mConnectionState = service.getConnectionState();",
                 "recent UI refresh")
s = replace_once(s,
                 '        String relayIp = p == null ? "" : p.mPrefs.getString("smart_relay_last_selected_ip", "");\n        mRelayIp.setText(relayIp.length() == 0 ? getString(R.string.value_unavailable) : relayIp);',
                 '''        String relayIp = "";\n        if (p != null && p.mPrefs.getBoolean("smart_relay", true)) {\n            relayIp = p.mPrefs.getString("smart_relay_last_selected_ip", "");\n            if (relayIp.length() == 0)\n                relayIp = mAppPrefs.getString("smart_relay_last_selected_ip_" + p.getUUIDString(), "");\n        }\n        mRelayIp.setText(relayIp.length() == 0 ? getString(R.string.value_unavailable) : relayIp);''',
                 "relay UI fallback")
write(p, s)

# Compact recent-profile row in the thumb zone, directly above Connect.
p = "app/src/main/res/layout/connect.xml"
s = read(p)
anchor = '    <FrameLayout android:layout_width="176dp" android:layout_height="176dp" android:layout_gravity="center_horizontal" android:layout_marginTop="4dp">'
recent_xml = '''    <LinearLayout\n        android:id="@+id/recent_profiles_row"\n        android:layout_width="match_parent"\n        android:layout_height="46dp"\n        android:layout_marginTop="6dp"\n        android:gravity="center"\n        android:orientation="horizontal">\n        <TextView android:id="@+id/recent_profile_1" android:layout_width="0dp" android:layout_height="42dp" android:layout_weight="1" android:layout_marginEnd="4dp" android:background="@drawable/server_card" android:ellipsize="end" android:gravity="center" android:maxLines="1" android:paddingStart="8dp" android:paddingEnd="8dp" android:textColor="@color/text_primary" android:textSize="12sp" android:textStyle="bold" />\n        <TextView android:id="@+id/recent_profile_2" android:layout_width="0dp" android:layout_height="42dp" android:layout_weight="1" android:layout_marginStart="2dp" android:layout_marginEnd="2dp" android:background="@drawable/server_card" android:ellipsize="end" android:gravity="center" android:maxLines="1" android:paddingStart="8dp" android:paddingEnd="8dp" android:textColor="@color/text_primary" android:textSize="12sp" android:textStyle="bold" />\n        <TextView android:id="@+id/recent_profile_3" android:layout_width="0dp" android:layout_height="42dp" android:layout_weight="1" android:layout_marginStart="4dp" android:background="@drawable/server_card" android:ellipsize="end" android:gravity="center" android:maxLines="1" android:paddingStart="8dp" android:paddingEnd="8dp" android:textColor="@color/text_primary" android:textSize="12sp" android:textStyle="bold" />\n    </LinearLayout>\n\n'''
s = replace_once(s, anchor, recent_xml + anchor, "recent selector layout")
write(p, s)

print("APK2 overlay applied: relay IP, one-tap saved auth, dark settings, 3 recent profiles")
