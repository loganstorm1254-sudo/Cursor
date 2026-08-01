# Notify Sender

Android app that **finds Notify Receiver phones on the same Wi‑Fi** and sends them a notification.

## How to use

1. Install **Notify Receiver** on the phone that should get alerts; tap **Start**.
2. Install this app on the sending phone.
3. Both phones on the **same Wi‑Fi**.
4. Tap **Find receivers**, select the other phone, enter title + message, tap **Send notification**.

## Build in Android Studio

1. Open the `NotifySender` folder in Android Studio.
2. Let Gradle sync.
3. Run on a physical device.

```bash
./gradlew assembleDebug
```

APK: `app/build/outputs/apk/debug/app-debug.apk`

## Requirements

- Android 8.0+ (API 26)
- Same Wi‑Fi as the receiver
