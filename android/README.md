# IRIS native Android app

The phone is a native Kotlin/Jetpack Compose IRIS app: Chat, Today, Journal,
Habits, and a More hub for Insights, Noticed, Review, Import, Sensors, Settings
and the Phone collector. The laptop remains the only database and pairing
authority. The collector continues delivering Pixel and Health Connect
measurements independently of the app's locked UI.

## Build

- JDK 17, Android SDK platform 36 and Build Tools 35.0.0.
- Set `ANDROID_HOME` to the SDK path, or put `sdk.dir=...` in `local.properties`.

```bash
./gradlew :app:lintDebug :app:assembleDebug :app:testDebugUnitTest
./gradlew :app:installDebug
```

Connect the Pixel by USB first, enable Developer options and USB debugging,
and accept its authorization dialog. `~/Android/Sdk/platform-tools/adb devices`
must show a serial in the `device` state. Keep the same debug signing key for
updates so the Keystore-encrypted pairing token stays available. The app
targets Android 15 and supports Android 10+; Health Connect availability
depends on the device.

## Pair and start

1. On the laptop, set `LAN_BIND_HOST` to its private Wi-Fi IPv4 address, then
   launch `uv run python scripts/serve_iris.py` from the repository root. The
   web UI remains on `127.0.0.1:8000`; the phone listener uses pinned HTTPS on
   port 8765. Allow inbound TCP 8765 only from the home Wi-Fi in the laptop's
   firewall. Settings shows whether this listener started successfully.
2. In laptop **Settings → Android live sensors**, generate a pairing token.
   On the Pixel, unlock IRIS with your fingerprint or screen lock, then open
   **More → Phone collector → Scan pairing QR** and **Test connection**.
   The token appears once on the laptop and is encrypted with Android Keystore
   on the phone. If the laptop IP changes, restart its listener and scan the
   token-free **address QR**; the server public-key pin and bearer stay valid.
   **Enter details manually** is available if the scanner cannot run.
3. Grant location, activity recognition and notifications, plus Usage access
   in Android Settings. If Usage access is greyed out, open App info → ⋮ →
   Allow restricted settings. To include heart rate, sleep and SpO2 from
   Health Connect, grant IRIS those read permissions (and background read when
   available). IRIS reads any app's permitted Health Connect records; it does
   not need a Fitbit. When Fitbit later writes to Health Connect, its records
   use the same connection and permissions.
4. In **More → Phone collector**, tap **Start live collection**. Its notification
   opens Phone collector after unlocking (when due) and has a Stop action. Tap
   **Sync now** to deliver on home Wi-Fi; the screen shows separate Pixel/Health
   Connect times, pending payloads and actionable connection errors. A reboot
   or app update stops collection and posts a tap-to-resume notification
   instead of silently restarting location tracking.

The service records Pixel location, observed step-counter increments and app
foreground intervals. Step counts are **not full-day totals**: it never
interprets the sensor's cumulative since-boot value as daily steps. Health
Connect heart-rate, sleep and oxygen-saturation records are read from any
permitted writer, including Fitbit once it syncs there. Health Connect is a
shared store, not a direct live watch feed: if no app writes a measurement,
there is nothing for IRIS to collect. A changes token catches later writes
with older measurement times; an expired token triggers bounded replay of
available data since the latest opt-in (at most 29 days). The optional Health
Connect tier is absent if permission or provider data is absent, not inferred.

Every 15 minutes (including Doze), and after home Wi-Fi reconnects, the
service tries to drain its durable outbox. Each immutable delivery is retried
until accepted; an invalid batch is quarantined and surfaced on the phone
instead of blocking the queue. IRIS groups deliveries into one pending review
batch per source per day. The Sensors screen requires explicit owner confirmation
before any reading becomes theme evidence; a batch that grew during review must
be rechecked. Disconnecting the phone in laptop Settings revokes its bearer.

## Use on the phone

On launch and after five minutes in the background, the app requires Android
fingerprint or screen-lock authentication. The phone's recent-apps thumbnail is
disabled on Android 13+. Chat, Today, Journal and Habits are bottom tabs.
Opening Chat starts an empty session; earlier messages stay on the laptop and
are still analysed. Insights and the other IRIS screens are in More, alongside
Phone collector.
The collector can queue measurements while the UI is locked, and syncs only
over the laptop's home Wi-Fi subnet. Away from home, reconnect to Wi-Fi instead
of disabling TLS or the server-key pin. Journal offers three-line writing and a
voice recording button. A voice entry is sent for transcription and opens
Import for transcript and date review; it appears in Journal only after you
confirm the import. Import also accepts files and voice recordings directly.

The bundled Instrument Serif, Geist and Geist Mono fonts are licensed under
the SIL Open Font License; their license texts are in `app/src/main/assets/licenses/`.
