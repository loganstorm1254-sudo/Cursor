package com.tikautoreply.app.service

import android.app.Notification
import android.app.PendingIntent
import android.app.RemoteInput
import android.content.Intent
import android.os.Bundle
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import com.tikautoreply.app.data.ReplyEvent
import com.tikautoreply.app.data.SettingsStore

class TikTokReplyService : NotificationListenerService() {

    private lateinit var store: SettingsStore
    private val handledKeys = LinkedHashSet<String>()

    override fun onCreate() {
        super.onCreate()
        store = SettingsStore(this)
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        Log.i(TAG, "Notification listener connected")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        if (sbn == null) return
        if (sbn.packageName !in TIKTOK_PACKAGES) return
        if (sbn.isOngoing) return

        val extras = sbn.notification.extras ?: return
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim().orEmpty()
        val text = extractText(extras)
        if (text.isBlank() && title.isBlank()) return

        // Ignore our own / system-ish noise
        val combined = "$title $text".lowercase()
        if (combined.contains("tikauto")) return

        val dedupeKey = "${sbn.packageName}|${sbn.id}|${sbn.postTime}|$title|$text"
        synchronized(handledKeys) {
            if (!handledKeys.add(dedupeKey)) return
            while (handledKeys.size > 200) {
                val first = handledKeys.firstOrNull() ?: break
                handledKeys.remove(first)
            }
        }

        if (!store.enabled) {
            logEvent(title.ifBlank { "TikTok" }, text, null, "paused")
            return
        }

        val sender = title.ifBlank { "TikTok" }
        val cooldownMs = store.cooldownSeconds * 1000L
        val last = store.lastReplyAt(sender)
        val now = System.currentTimeMillis()
        if (cooldownMs > 0 && now - last < cooldownMs) {
            logEvent(sender, text, null, "cooldown")
            return
        }

        val replyText = store.pickReply(text.ifBlank { title })
        if (replyText.isBlank()) {
            logEvent(sender, text, null, "no-reply-text")
            return
        }

        val sent = tryReply(sbn.notification, replyText)
        if (sent) {
            store.markReplied(sender, now)
            logEvent(sender, text, replyText, "sent")
        } else {
            logEvent(sender, text, replyText, "no-reply-action")
        }
    }

    private fun extractText(extras: Bundle): String {
        val candidates = listOf(
            extras.getCharSequence(Notification.EXTRA_BIG_TEXT),
            extras.getCharSequence(Notification.EXTRA_TEXT),
            extras.getCharSequence(Notification.EXTRA_SUB_TEXT),
            extras.getCharSequence(Notification.EXTRA_INFO_TEXT)
        )
        val first = candidates.firstOrNull { !it.isNullOrBlank() }?.toString()?.trim().orEmpty()
        if (first.isNotBlank()) return first

        val lines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)
        if (lines != null && lines.isNotEmpty()) {
            return lines.joinToString("\n") { it?.toString().orEmpty() }.trim()
        }
        return ""
    }

    private fun tryReply(notification: Notification, replyText: String): Boolean {
        val actions = notification.actions ?: return false
        for (action in actions) {
            val remoteInputs = action.remoteInputs
            if (remoteInputs.isNullOrEmpty()) continue
            val fillIn = Intent()
            val results = Bundle()
            for (input in remoteInputs) {
                results.putCharSequence(input.resultKey, replyText)
            }
            RemoteInput.addResultsToIntent(remoteInputs, fillIn, results)
            return try {
                action.actionIntent.send(this, 0, fillIn)
                true
            } catch (e: PendingIntent.CanceledException) {
                Log.w(TAG, "Reply PendingIntent canceled", e)
                false
            } catch (e: Exception) {
                Log.w(TAG, "Failed to send reply", e)
                false
            }
        }
        return false
    }

    private fun logEvent(sender: String, message: String, reply: String?, status: String) {
        store.addEvent(
            ReplyEvent(
                timeMs = System.currentTimeMillis(),
                sender = sender,
                message = message,
                reply = reply,
                status = status
            )
        )
        sendBroadcast(Intent(SettingsStore.ACTION_EVENT_LOGGED).setPackage(packageName))
    }

    companion object {
        private const val TAG = "TikAutoReply"
        val TIKTOK_PACKAGES = setOf(
            "com.zhiliaoapp.musically",
            "com.ss.android.ugc.trill"
        )
    }
}
