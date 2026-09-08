package com.tikautoreply.app.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

class SettingsStore(context: Context) {

    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    var username: String
        get() = prefs.getString(KEY_USERNAME, "") ?: ""
        set(value) = prefs.edit().putString(KEY_USERNAME, value.trim().removePrefix("@")).apply()

    var enabled: Boolean
        get() = prefs.getBoolean(KEY_ENABLED, false)
        set(value) = prefs.edit().putBoolean(KEY_ENABLED, value).apply()

    var defaultReply: String
        get() = prefs.getString(KEY_DEFAULT_REPLY, DEFAULT_REPLY) ?: DEFAULT_REPLY
        set(value) = prefs.edit().putString(KEY_DEFAULT_REPLY, value.trim()).apply()

    var cooldownSeconds: Int
        get() = prefs.getInt(KEY_COOLDOWN, 60).coerceAtLeast(0)
        set(value) = prefs.edit().putInt(KEY_COOLDOWN, value.coerceAtLeast(0)).apply()

    fun getRules(): List<KeywordRule> {
        val raw = prefs.getString(KEY_RULES, "[]") ?: "[]"
        val arr = JSONArray(raw)
        return buildList {
            for (i in 0 until arr.length()) {
                add(KeywordRule.fromJson(arr.getJSONObject(i)))
            }
        }
    }

    fun setRules(rules: List<KeywordRule>) {
        val arr = JSONArray()
        rules.forEach { arr.put(it.toJson()) }
        prefs.edit().putString(KEY_RULES, arr.toString()).apply()
    }

    fun addRule(keyword: String, reply: String): KeywordRule {
        val rule = KeywordRule(
            id = UUID.randomUUID().toString(),
            keyword = keyword.trim(),
            reply = reply.trim()
        )
        setRules(getRules() + rule)
        return rule
    }

    fun removeRule(id: String) {
        setRules(getRules().filterNot { it.id == id })
    }

    fun getEvents(): List<ReplyEvent> {
        val raw = prefs.getString(KEY_EVENTS, "[]") ?: "[]"
        val arr = JSONArray(raw)
        return buildList {
            for (i in 0 until arr.length()) {
                add(ReplyEvent.fromJson(arr.getJSONObject(i)))
            }
        }
    }

    fun addEvent(event: ReplyEvent) {
        val next = (listOf(event) + getEvents()).take(MAX_EVENTS)
        val arr = JSONArray()
        next.forEach { arr.put(it.toJson()) }
        prefs.edit().putString(KEY_EVENTS, arr.toString()).apply()
    }

    fun clearEvents() {
        prefs.edit().putString(KEY_EVENTS, "[]").apply()
    }

    fun lastReplyAt(senderKey: String): Long =
        prefs.getLong(KEY_LAST_PREFIX + senderKey.lowercase(), 0L)

    fun markReplied(senderKey: String, atMs: Long = System.currentTimeMillis()) {
        prefs.edit().putLong(KEY_LAST_PREFIX + senderKey.lowercase(), atMs).apply()
    }

    fun pickReply(message: String): String {
        val lower = message.lowercase()
        getRules().firstOrNull { it.enabled && it.keyword.isNotBlank() && lower.contains(it.keyword.lowercase()) }
            ?.let { return it.reply }
        return defaultReply
    }

    fun exportSnapshot(): JSONObject = JSONObject()
        .put("username", username)
        .put("enabled", enabled)
        .put("defaultReply", defaultReply)
        .put("cooldownSeconds", cooldownSeconds)

    companion object {
        private const val PREFS = "tikauto_settings"
        private const val KEY_USERNAME = "username"
        private const val KEY_ENABLED = "enabled"
        private const val KEY_DEFAULT_REPLY = "default_reply"
        private const val KEY_COOLDOWN = "cooldown_seconds"
        private const val KEY_RULES = "rules_json"
        private const val KEY_EVENTS = "events_json"
        private const val KEY_LAST_PREFIX = "last_reply_"
        private const val MAX_EVENTS = 80
        const val DEFAULT_REPLY = "Thanks for the message — I'll get back soon!"
        const val ACTION_SETTINGS_CHANGED = "com.tikautoreply.app.SETTINGS_CHANGED"
        const val ACTION_EVENT_LOGGED = "com.tikautoreply.app.EVENT_LOGGED"
    }
}
