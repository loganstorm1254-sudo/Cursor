# TikAuto — local TikTok DM auto-reply (Android)

Runs entirely on your phone. Link your TikTok username, allow notification access, set a default reply (and optional keyword rules). When TikTok shows a message notification that supports **Reply**, TikAuto sends your text automatically.

## Install

1. Install [`../releases/TikAuto.apk`](../releases/TikAuto.apk) (Android 8+).
2. Open **TikAuto**.
3. Enter your TikTok username → **Save & link**.
4. Tap **Allow notification access** → enable **TikAuto**.
5. Write your default reply → turn **Auto-reply** ON → **Save reply settings**.

Keep TikTok notifications enabled (including message notifications). The phone can stay locked; TikAuto listens in the background via Android’s notification listener.

## How replies work

TikTok does not offer a public DM API for third-party apps. TikAuto uses Android’s official **NotificationListenerService** + **RemoteInput** (the same path system “quick reply” uses). If a TikTok message notification has no Reply action on your device/version, the activity log shows `no-reply-action` and nothing is sent.

## Keyword rules

If an incoming message contains a keyword you added, that rule’s reply is used instead of the default. Cooldown (seconds per chat) prevents spam replies to the same sender.

## Privacy

Username, rules, and the activity log stay in app storage on this device. No account password is collected. No cloud backend.
