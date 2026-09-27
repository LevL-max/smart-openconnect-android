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


# 0.3.10 is a focused stale-session / native TLS recovery build on top of 0.3.9.
p = "app/build.gradle"
s = read(p)
s = replace_once(
    s,
    'versionCode 12\n        versionName "0.3.9"',
    'versionCode 13\n        versionName "0.3.10"',
    "0.3.10 version bump",
)
write(p, s)

# Manual Connect must never start a replacement OpenConnect thread while an older
# management thread is still alive. Reuse the proven 0.3.9 full-session restart
# path if the normal 1-second stop/join is not enough.
p = "app/src/main/java/net/openconnect_vpn/android/core/OpenVpnService.java"
s = read(p)
old = '''		killVPNThread(true);

		// stopSelfResult(most_recent_startId) will kill the service
		// stopSelfResult(previous_startId) will not
		mStartId = startId;

        mVPN = new OpenConnectManagementThread(getApplicationContext(), profile, this);
        mVPNThread = new Thread(mVPN, "OpenVPNManagementThread");
        mVPNThread.start();

		unregisterReceivers();
		registerDeviceStateReceiver(mVPN);

		ProfileManager.setConnectedVpnProfile(profile);

        return START_NOT_STICKY;'''
new = '''		// A manual Connect supersedes any delayed automatic network-change restart.
		cancelPendingNetworkRestart();
		killVPNThread(true);

		// If the previous native/OpenConnect thread survived the normal stop/join,
		// do not create a second session in the same process. That overlap can leave
		// the new attempt stuck after TCP connect at "SSL negotiation with ...".
		if (mVPNThread != null && mVPNThread.isAlive()) {
			Log.w(TAG, "CONNECT: stale VPN thread survived stop; resetting before new session");
			restartVPNOnNetworkChange();
			// restartVPNOnNetworkChange() marks the controlled restart pending before
			// the old thread can call threadDone(), so it cannot stop the replacement.
			mStartId = startId;
			return START_NOT_STICKY;
		}

		// stopSelfResult(most_recent_startId) will kill the service
		// stopSelfResult(previous_startId) will not
		mStartId = startId;

        mVPN = new OpenConnectManagementThread(getApplicationContext(), profile, this);
        mVPNThread = new Thread(mVPN, "OpenVPNManagementThread");
        mVPNThread.start();

		unregisterReceivers();
		registerDeviceStateReceiver(mVPN);

		ProfileManager.setConnectedVpnProfile(profile);

        return START_NOT_STICKY;'''
s = replace_once(s, old, new, "manual stale-session reset")
write(p, s)

# Add a narrow native TLS watchdog. It is armed only after libopenconnect reports
# "SSL negotiation with ...". If the handshake makes no progress for 10 seconds,
# cancel that native attempt, destroy the OpenConnect object, and retry once with
# a fresh session. When Smart Relay is enabled, the timed-out relay is skipped in
# favor of the next healthy probed candidate when one exists.
p = "app/src/main/java/net/openconnect_vpn/android/core/OpenConnectManagementThread.java"
s = read(p)

s = replace_once(
    s,
    '''	private boolean mRequestPause;
	private boolean mRequestDisconnect;
	private Object mMainloopLock = new Object();
''',
    '''	private boolean mRequestPause;
	private boolean mRequestDisconnect;
	private Object mMainloopLock = new Object();

	private static final int TLS_HANDSHAKE_TIMEOUT_MS = 10000;
	private volatile boolean mTlsHandshakeActive;
	private volatile boolean mTlsHandshakeTimedOut;
	private volatile int mTlsWatchdogGeneration;
	private volatile String mActiveRelayIp;
	private volatile String mRetrySkipRelayIp;
''',
    "TLS watchdog fields",
)

s = replace_once(
    s,
    '''		public int onValidatePeerCert(String reason) {
			log("CALLBACK: onValidatePeerCert");
''',
    '''		public int onValidatePeerCert(String reason) {
			log("CALLBACK: onValidatePeerCert");
			finishTlsHandshakeWatchdog();
''',
    "finish TLS watchdog on peer cert",
)

s = replace_once(
    s,
    '''		public int onProcessAuthForm(LibOpenConnect.AuthForm authForm) {
			log("CALLBACK: onProcessAuthForm");
''',
    '''		public int onProcessAuthForm(LibOpenConnect.AuthForm authForm) {
			log("CALLBACK: onProcessAuthForm");
			finishTlsHandshakeWatchdog();
''',
    "finish TLS watchdog on auth form",
)

s = replace_once(
    s,
    '''		public void onProgress(int level, String msg) {
			mOpenVPNService.log(level, "LIB: " + msg.trim());
		}
''',
    '''		public void onProgress(int level, String msg) {
			String line = msg.trim();
			mOpenVPNService.log(level, "LIB: " + line);
			if (line.startsWith("SSL negotiation with "))
				startTlsHandshakeWatchdog();
		}
''',
    "arm TLS watchdog from native progress",
)

# Keep the relay selected for this native attempt so a timed-out real TLS
# connection can avoid the same relay on the single automatic retry.
s = replace_once(
    s,
    '''			if (relay != null) {
				if (relay.poolCsv != null && relay.poolCsv.length() > 0)
					mAppPrefs.edit().putString(cacheKey, relay.poolCsv).apply();
				if (relay.selectedIp != null) {''',
    '''			if (relay != null) {
				if (relay.poolCsv != null && relay.poolCsv.length() > 0)
					mAppPrefs.edit().putString(cacheKey, relay.poolCsv).apply();

				String selectedIp = relay.selectedIp;
				if (selectedIp != null && mRetrySkipRelayIp != null &&
						mRetrySkipRelayIp.equals(selectedIp)) {
					String alternate = null;
					for (SmartRelaySelector.Candidate c : relay.candidates) {
						if (!mRetrySkipRelayIp.equals(c.ip) && c.tlsOk) {
							alternate = c.ip;
							break;
						}
					}
					if (alternate == null) {
						for (SmartRelaySelector.Candidate c : relay.candidates) {
							if (!mRetrySkipRelayIp.equals(c.ip) && c.tcpOk) {
								alternate = c.ip;
								break;
							}
						}
					}
					if (alternate != null) {
						log("SMART RELAY: retry skipping timed-out " + mRetrySkipRelayIp +
								"; using " + alternate);
						selectedIp = alternate;
					} else {
						log("SMART RELAY: no alternate healthy relay after TLS timeout; retrying selected relay");
					}
				}
				mActiveRelayIp = selectedIp;

				if (selectedIp != null) {''',
    "Smart Relay alternate selection",
)

s = replace_once(
    s,
    'int resolveRet = mOC.setResolve(dnsName, relay.selectedIp);',
    'int resolveRet = mOC.setResolve(dnsName, selectedIp);',
    "resolver uses retry-selected relay",
)
s = replace_once(
    s,
    'mPrefs.edit().putString("smart_relay_last_selected_ip", relay.selectedIp).commit();',
    'mPrefs.edit().putString("smart_relay_last_selected_ip", selectedIp).commit();',
    "profile relay persistence uses retry-selected relay",
)
s = replace_once(
    s,
    'mAppPrefs.edit().putString("smart_relay_last_selected_ip_" + mProfile.getUUIDString(), relay.selectedIp).apply();',
    'mAppPrefs.edit().putString("smart_relay_last_selected_ip_" + mProfile.getUUIDString(), selectedIp).apply();',
    "app relay persistence uses retry-selected relay",
)

s = replace_once(
    s,
    '''		int ret = mOC.obtainCookie();
		if (ret < 0) {
			// don't pop up an alert if the user rejected the server cert
			if (mRejectedCerts.isEmpty() && !mRequestDisconnect) {
				log("Error obtaining cookie");
				errorAlert();
			} else {
				updateStatPref("cancel");
			}
			return false;
''',
    '''		int ret = mOC.obtainCookie();
		finishTlsHandshakeWatchdog();
		if (ret < 0) {
			if (mTlsHandshakeTimedOut) {
				log("TLS: native handshake timed out; fresh-session retry requested");
				return false;
			}
			// don't pop up an alert if the user rejected the server cert
			if (mRejectedCerts.isEmpty() && !mRequestDisconnect) {
				log("Error obtaining cookie");
				errorAlert();
			} else {
				updateStatPref("cancel");
			}
			return false;
''',
    "TLS timeout obtainCookie handling",
)

old_run = '''	@Override
	public void run() {
		logStats();

		if (!runVPN()) {
			log("VPN terminated with errors");
		}
		setState(STATE_DISCONNECTED);

		synchronized (mMainloopLock) {
			mOC.destroy();
			mOC = null;
		}
		UserDialog.clearDeferredPrefs();

		mOpenVPNService.threadDone();
	}
'''
new_run = '''	@Override
	public void run() {
		logStats();

		boolean ok = false;
		int tlsRetries = 0;
		while (!mRequestDisconnect) {
			mTlsHandshakeTimedOut = false;
			mTlsHandshakeActive = false;
			mActiveRelayIp = null;

			ok = runVPN();
			finishTlsHandshakeWatchdog();

			if (ok || !mTlsHandshakeTimedOut || mRequestDisconnect || tlsRetries >= 1)
				break;

			tlsRetries++;
			log("TLS: handshake timeout - resetting OpenConnect session for retry " + tlsRetries + "/1");
			synchronized (mMainloopLock) {
				if (mOC != null) {
					mOC.destroy();
					mOC = null;
				}
			}
			mAuthDone = false;
			mLastFormDigest = null;
		}

		if (!ok && !mRequestDisconnect) {
			log("VPN terminated with errors");
		}
		setState(STATE_DISCONNECTED);

		synchronized (mMainloopLock) {
			if (mOC != null) {
				mOC.destroy();
				mOC = null;
			}
		}
		UserDialog.clearDeferredPrefs();

		mOpenVPNService.threadDone();
	}
'''
s = replace_once(s, old_run, new_run, "single fresh-session TLS retry")

marker = '''	private synchronized void setState(int state) {
		mOpenVPNService.setConnectionState(state);
	}
'''
watchdog_methods = '''	private void startTlsHandshakeWatchdog() {
		final int generation = ++mTlsWatchdogGeneration;
		final String relayIp = mActiveRelayIp;
		mTlsHandshakeActive = true;
		log("TLS: handshake watchdog armed for " + TLS_HANDSHAKE_TIMEOUT_MS + "ms" +
				(relayIp == null ? "" : " on " + relayIp));

		Thread watchdog = new Thread(new Runnable() {
			@Override
			public void run() {
				try {
					Thread.sleep(TLS_HANDSHAKE_TIMEOUT_MS);
				} catch (InterruptedException ignored) {
					return;
				}

				synchronized (mMainloopLock) {
					if (generation != mTlsWatchdogGeneration || !mTlsHandshakeActive ||
							mRequestDisconnect || mOC == null)
						return;

					mTlsHandshakeActive = false;
					mTlsHandshakeTimedOut = true;
					mRetrySkipRelayIp = relayIp;
					log("TLS: handshake timeout after " + TLS_HANDSHAKE_TIMEOUT_MS +
							"ms; canceling native attempt" +
							(relayIp == null ? "" : " on " + relayIp));
					mOC.cancel();
				}
			}
		}, "OpenConnectTlsWatchdog");
		watchdog.setDaemon(true);
		watchdog.start();
	}

	private void finishTlsHandshakeWatchdog() {
		mTlsHandshakeActive = false;
		mTlsWatchdogGeneration++;
	}

'''
s = replace_once(s, marker, watchdog_methods + marker, "TLS watchdog methods")

write(p, s)

print("0.3.10 overlay applied: manual stale-session reset, 10s native TLS watchdog, one fresh-session retry with alternate Smart Relay candidate")
