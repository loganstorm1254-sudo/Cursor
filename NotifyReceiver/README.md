# Notify Receiver

Android app that **listens on your Wi‑Fi** and shows system notifications sent by **Notify Sender**.

## How to use

1. Install this app on phone A.
2. Install **Notify Sender** on phone B.
3. Connect both phones to the **same Wi‑Fi**.
4. Open Notify Receiver → set a device name → tap **Start**.
5. Allow notification permission when asked.
6. On the sender phone, tap **Find receivers**, pick this phone, type a message, and send.

Keep the receiver listening (a quiet ongoing notification means it’s active).

## Build in Android Studio

1. Open the `NotifyReceiver` folder in Android Studio (Ladybug / Koala or newer).
2. Let Gradle sync.
3. Run on a physical device (Wi‑Fi discovery needs a real network).

```bash
./gradlew assembleDebug
```

APK: `app/build/outputs/apk/debug/app-debug.apk`

## Requirements

- Android 8.0+ (API 26)
- Same Wi‑Fi as the sender (client isolation / AP isolation on guest networks can block phone-to-phone traffic)
