# TapShare

Tap the **tops of two phones** together to share the photo on screen — connects over **Bluetooth** (no NFC required).

## What it does

- **Always active** foreground service (survives closing the app)
- **Starts on boot**
- Open a photo → tap tops together (accelerometer) **or** press **Share over Bluetooth**
- Finds the other TapShare phone via BLE, sends the file over Bluetooth RFCOMM
- Receiver gets the ripple animation and the photo opens full screen

## Install

1. Install `releases/TapShare.apk` on **both** phones.
2. Open TapShare → allow photos, nearby devices / Bluetooth, location (for BLE), notifications.
3. Turn **Bluetooth ON**. Tap **Allow background**.
4. Phone A: Open Gallery → pick a photo.
5. Hold tops together (or press Share) while phone B has TapShare running.
