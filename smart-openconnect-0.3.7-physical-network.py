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


def regex_replace_once(text, pattern, replacement, label):
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text


# Version bump.
p = "app/build.gradle"
s = read(p)
s = replace_once(
    s,
    'versionCode 9\n        versionName "0.3.6"',
    'versionCode 10\n        versionName "0.3.7"',
    "0.3.7 version bump",
)
write(p, s)

# Modern Android physical-network monitor. CONNECTIVITY_ACTION/getActiveNetworkInfo
# is retained as a fallback for pre-Lollipop or callback-registration failure.
p = "app/src/main/java/net/openconnect_vpn/android/core/DeviceStateReceiver.java"
s = read(p)

s = replace_once(
    s,
    'import android.net.NetworkInfo.State;\nimport android.util.Log;\n',
    'import android.net.NetworkInfo.State;\n'
    'import android.annotation.TargetApi;\n'
    'import android.net.Network;\n'
    'import android.net.NetworkCapabilities;\n'
    'import android.net.NetworkRequest;\n'
    'import android.os.Build;\n'
    'import android.os.Handler;\n'
    'import android.os.Looper;\n'
    'import android.util.Log;\n\n'
    'import java.util.HashMap;\n'
    'import java.util.Map;\n',
    "DeviceStateReceiver modern-network imports",
)

s = replace_once(
    s,
    '    private boolean mPaused;\n',
    '    private boolean mPaused;\n'
    '    private boolean mModernNetworkCallbackActive;\n'
    '    private Object mPhysicalNetworkMonitor;\n',
    "DeviceStateReceiver modern-network fields",
)

# Serialize pause-state changes between BroadcastReceiver and NetworkCallback threads.
s = replace_once(
    s,
    '    private void updatePauseState() {\n',
    '    private synchronized void updatePauseState() {\n',
    "synchronized pause state",
)

# Ignore legacy CONNECTIVITY_ACTION when the modern callback is active.
s = replace_once(
    s,
    '    \t} else if (ConnectivityManager.CONNECTIVITY_ACTION.equals(s)) {\n            networkStateChange(context);\n',
    '    \t} else if (ConnectivityManager.CONNECTIVITY_ACTION.equals(s)) {\n'
    '            if (!mModernNetworkCallbackActive) {\n'
    '                networkStateChange(context);\n'
    '            }\n',
    "CONNECTIVITY_ACTION fallback gate",
)

marker = '    public void setKeepalive(boolean active) {\n'
if marker not in s:
    raise SystemExit("DeviceStateReceiver setKeepalive marker not found")

modern = r'''    public boolean registerModernNetworkCallback(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) {
            return false;
        }
        try {
            mPhysicalNetworkMonitor = PhysicalNetworkMonitor.register(this, context);
            mModernNetworkCallbackActive = mPhysicalNetworkMonitor != null;
            if (mModernNetworkCallbackActive) {
                Log.i(TAG, "NETWORK: using physical NOT_VPN NetworkCallback monitor");
            }
            return mModernNetworkCallbackActive;
        } catch (Exception e) {
            Log.w(TAG, "NETWORK: modern callback unavailable; using CONNECTIVITY_ACTION fallback", e);
            mPhysicalNetworkMonitor = null;
            mModernNetworkCallbackActive = false;
            return false;
        }
    }

    public void unregisterModernNetworkCallback(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP && mPhysicalNetworkMonitor != null) {
            try {
                PhysicalNetworkMonitor.unregister(context, mPhysicalNetworkMonitor);
            } catch (Exception e) {
                Log.w(TAG, "NETWORK: error unregistering physical monitor", e);
            }
        }
        mPhysicalNetworkMonitor = null;
        mModernNetworkCallbackActive = false;
    }

    private synchronized void onModernNetworkSeed(boolean available, String label) {
        Log.i(TAG, "NETWORK: physical monitor seed=" + label);
        mNetworkOff = !available;
        updatePauseState();
    }

    private synchronized void onModernNetworkChanged(boolean available, String oldLabel, String newLabel) {
        Log.i(TAG, "NETWORK: physical preferred changed " + oldLabel + " -> " + newLabel);

        if (!available) {
            mNetworkOff = true;
            updatePauseState();
            return;
        }

        mNetworkOff = false;
        boolean reconnectOnChange = mPrefs.getBoolean("netchangereconnect", true);
        if (reconnectOnChange) {
            if (mPaused) {
                Log.i(TAG, "NETWORK: clearing transient pause before reconnect");
                mManagement.resume();
                mPaused = false;
            }
            Log.i(TAG, "NETWORK: reconnecting VPN on new physical network");
            mManagement.reconnect();
        } else {
            Log.i(TAG, "NETWORK: reconnect disabled; disconnecting VPN");
            mManagement.stopVPN();
            mPaused = false;
        }
        updatePauseState();
    }

    @TargetApi(Build.VERSION_CODES.LOLLIPOP)
    private static final class PhysicalNetworkMonitor extends ConnectivityManager.NetworkCallback {
        private static final long EVALUATE_DELAY_MS = 350;

        private final DeviceStateReceiver mOwner;
        private final ConnectivityManager mConnectivityManager;
        private final Handler mHandler = new Handler(Looper.getMainLooper());
        private final HashMap<Network, NetworkCapabilities> mNetworks = new HashMap<Network, NetworkCapabilities>();

        private Network mSelected;
        private String mSelectedLabel = "none";
        private boolean mInitialized;

        private final Runnable mEvaluateRunnable = new Runnable() {
            @Override
            public void run() {
                evaluate();
            }
        };

        private PhysicalNetworkMonitor(DeviceStateReceiver owner, ConnectivityManager connectivityManager) {
            mOwner = owner;
            mConnectivityManager = connectivityManager;
        }

        static Object register(DeviceStateReceiver owner, Context context) {
            ConnectivityManager cm = (ConnectivityManager)
                    context.getSystemService(Context.CONNECTIVITY_SERVICE);
            if (cm == null) {
                return null;
            }

            PhysicalNetworkMonitor monitor = new PhysicalNetworkMonitor(owner, cm);
            NetworkRequest request = new NetworkRequest.Builder()
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)
                    .build();
            cm.registerNetworkCallback(request, monitor);
            return monitor;
        }

        static void unregister(Context context, Object object) {
            PhysicalNetworkMonitor monitor = (PhysicalNetworkMonitor)object;
            synchronized (monitor) {
                monitor.mHandler.removeCallbacks(monitor.mEvaluateRunnable);
            }
            monitor.mConnectivityManager.unregisterNetworkCallback(monitor);
        }

        @Override
        public void onAvailable(Network network) {
            synchronized (this) {
                if (!mNetworks.containsKey(network)) {
                    mNetworks.put(network, null);
                }
                scheduleLocked();
            }
        }

        @Override
        public void onCapabilitiesChanged(Network network, NetworkCapabilities capabilities) {
            synchronized (this) {
                if (capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                        capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)) {
                    mNetworks.put(network, capabilities);
                } else {
                    mNetworks.remove(network);
                }
                scheduleLocked();
            }
        }

        @Override
        public void onLost(Network network) {
            synchronized (this) {
                mNetworks.remove(network);
                scheduleLocked();
            }
        }

        private void scheduleLocked() {
            mHandler.removeCallbacks(mEvaluateRunnable);
            mHandler.postDelayed(mEvaluateRunnable, EVALUATE_DELAY_MS);
        }

        private int score(NetworkCapabilities capabilities) {
            if (capabilities == null ||
                    !capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) ||
                    !capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)) {
                return -1;
            }

            int score = capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) ? 1000 : 0;
            if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) {
                score += 400;
            } else if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) {
                score += 300;
            } else if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) {
                score += 200;
            } else {
                score += 100;
            }
            return score;
        }

        private String label(Network network, NetworkCapabilities capabilities) {
            if (network == null || capabilities == null) {
                return "none";
            }
            String transport;
            if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) {
                transport = "ethernet";
            } else if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) {
                transport = "wifi";
            } else if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) {
                transport = "cellular";
            } else {
                transport = "other";
            }
            String validation = capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
                    ? "validated" : "unvalidated";
            return transport + "/" + validation + "/" + network.toString();
        }

        private synchronized void evaluate() {
            Network best = null;
            NetworkCapabilities bestCapabilities = null;
            int bestScore = -1;

            // Keep the current choice on ties to avoid reconnect churn.
            if (mSelected != null) {
                NetworkCapabilities current = mNetworks.get(mSelected);
                int currentScore = score(current);
                if (currentScore >= 0) {
                    best = mSelected;
                    bestCapabilities = current;
                    bestScore = currentScore;
                }
            }

            for (Map.Entry<Network, NetworkCapabilities> entry : mNetworks.entrySet()) {
                int candidateScore = score(entry.getValue());
                if (candidateScore > bestScore) {
                    best = entry.getKey();
                    bestCapabilities = entry.getValue();
                    bestScore = candidateScore;
                }
            }

            String newLabel = label(best, bestCapabilities);
            boolean same = (mSelected == null && best == null) ||
                    (mSelected != null && mSelected.equals(best));

            if (!mInitialized) {
                mInitialized = true;
                mSelected = best;
                mSelectedLabel = newLabel;
                mOwner.onModernNetworkSeed(best != null, newLabel);
                return;
            }

            if (same) {
                return;
            }

            String oldLabel = mSelectedLabel;
            mSelected = best;
            mSelectedLabel = newLabel;
            mOwner.onModernNetworkChanged(best != null, oldLabel, newLabel);
        }
    }

'''
s = s.replace(marker, modern + marker, 1)
write(p, s)

# Register/unregister the modern monitor with the service lifecycle while keeping
# the legacy BroadcastReceiver registered as a fallback only. These use regexes
# deliberately because the maintained 1.12 source and our base patch do not use
# identical tab/space indentation in OpenVpnService.java.
p = "app/src/main/java/net/openconnect_vpn/android/core/OpenVpnService.java"
s = read(p)

register_pattern = (
    r'(?P<indent>^[ \t]*)mDeviceStateReceiver\s*=\s*new DeviceStateReceiver\(management,\s*mPrefs\);\s*\n'
    r'(?P=indent)registerReceiver\(mDeviceStateReceiver,\s*filter\);'
)
register_match = re.search(register_pattern, s, flags=re.MULTILINE)
if not register_match:
    raise SystemExit("register modern physical network callback: expected exactly one match, found 0")
indent = register_match.group('indent')
register_replacement = (
    f'{indent}mDeviceStateReceiver = new DeviceStateReceiver(management, mPrefs);\n'
    f'{indent}mDeviceStateReceiver.registerModernNetworkCallback(this);\n'
    f'{indent}registerReceiver(mDeviceStateReceiver, filter);'
)
s, count = re.subn(register_pattern, register_replacement, s, count=1, flags=re.MULTILINE)
if count != 1:
    raise SystemExit(f"register modern physical network callback: expected exactly one replacement, found {count}")

unregister_pattern = (
    r'(?P<indent>^[ \t]*)if\s*\(mDeviceStateReceiver\s*!=\s*null\)\s*\{\s*\n'
    r'(?P<bodyindent>[ \t]+)unregisterReceiver\(mDeviceStateReceiver\);\s*\n'
    r'(?P=indent)\}'
)
unregister_match = re.search(unregister_pattern, s, flags=re.MULTILINE)
if not unregister_match:
    raise SystemExit("unregister modern physical network callback: expected exactly one match, found 0")
indent = unregister_match.group('indent')
bodyindent = unregister_match.group('bodyindent')
unregister_replacement = (
    f'{indent}if (mDeviceStateReceiver != null) {{\n'
    f'{bodyindent}mDeviceStateReceiver.unregisterModernNetworkCallback(this);\n'
    f'{bodyindent}unregisterReceiver(mDeviceStateReceiver);\n'
    f'{indent}}}'
)
s, count = re.subn(unregister_pattern, unregister_replacement, s, count=1, flags=re.MULTILINE)
if count != 1:
    raise SystemExit(f"unregister modern physical network callback: expected exactly one replacement, found {count}")

write(p, s)

print("0.3.7 overlay applied: debounced NOT_VPN NetworkCallback monitor with legacy connectivity fallback")
