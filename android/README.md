# IRIS Android App

The phone-side counterpart to IRIS. The app is a thin client — state
lives on the laptop; the phone is a sensor collector, an entry writer,
and a reader of insights.

## Build prerequisites

This directory is a standard Android Gradle project. Building it
requires:

- JDK 17
- Android SDK 35 (platforms;android-35)
- Android Build Tools 35.0.0
- A `local.properties` file pointing at your SDK, e.g.:

  ```
  sdk.dir=/home/noodis/Android/Sdk
  ```

  or the `ANDROID_HOME` env var.

## Build & test

The project ships with a Gradle wrapper, so the only prerequisite is a
JDK 17 and the Android SDK. The wrapper uses Gradle 8.9.

```bash
./gradlew :app:assembleDebug   # builds the APK
./gradlew :app:test            # 5 JVM unit tests for SensorPayloadBuilder
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
        SensorPayloadBuilder.kt    JVM-testable cross-seam contract
        SensorCollectorService.kt  foreground service
        Settings.kt                SharedPreferences storage (temp)
    src/test/kotlin/...            5 JVM unit tests for the builder
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
