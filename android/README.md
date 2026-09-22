# IRIS Android App

The phone-side counterpart to IRIS. The app is a thin client — state
lives on the laptop; the phone is a sensor collector, an entry writer,
and a reader of insights.

## Build prerequisites

This directory is a standard Android Gradle project. Building it
requires:

- JDK 17
- Android SDK 34 (platforms;android-34)
- Android Build Tools 34.0.0
- A `local.properties` file pointing at your SDK, e.g.:

  ```
  sdk.dir=/opt/android-sdk
  ```

  or the `ANDROID_HOME` env var.

## Build & test

```bash
./gradlew :app:assembleDebug   # builds the APK
./gradlew :app:test            # unit tests (MockWebServer)
```

The first build downloads Compose, OkHttp, WorkManager, and the
Play Services Location library. No further configuration is needed.

## Project layout

```
android/
  build.gradle.kts                 root project
  settings.gradle.kts              module list + repos
  app/
    build.gradle.kts               single-module app config
    src/main/
      AndroidManifest.xml          permissions + service declaration
      kotlin/com/iris/android/
        MainActivity.kt            placeholder UI
        IrisApiClient.kt           the only HTTP client to IRIS
        SensorCollectorService.kt  foreground service stub
    src/test/kotlin/...            unit tests (added in next task)
```

## What this branch has

- A buildable Android project.
- The `IrisApiClient` that targets the two mobile routes — pairing and
  sensor intake — that already exist on IRIS.
- A foreground-service stub. The real collection logic lands with the
  sensor-collection commit on this branch.

## What lives on a different branch

- The four Compose screens (chat, journal, settings, insights).
- Android Keystore token storage.
- Auto-update of the laptop's LAN IP via mDNS.
- Polish, accessibility, error UX.

These are deliberately *not* on this branch so the architectural work
(seams, schema, bearer auth) can land and be reviewed without the
churn of UI iteration.
