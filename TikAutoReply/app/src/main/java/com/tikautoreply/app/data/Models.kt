package com.tikautoreply.app.data

import org.json.JSONObject

data class KeywordRule(
    val id: String,
    val keyword: String,
    val reply: String,
    val enabled: Boolean = true
) {
    fun toJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("keyword", keyword)
        .put("reply", reply)
        .put("enabled", enabled)

    companion object {
        fun fromJson(obj: JSONObject): KeywordRule = KeywordRule(
            id = obj.getString("id"),
            keyword = obj.getString("keyword"),
            reply = obj.getString("reply"),
            enabled = obj.optBoolean("enabled", true)
        )
    }
}

data class ReplyEvent(
    val timeMs: Long,
    val sender: String,
    val message: String,
    val reply: String?,
    val status: String
) {
    fun toJson(): JSONObject = JSONObject()
        .put("timeMs", timeMs)
        .put("sender", sender)
        .put("message", message)
        .put("reply", reply)
        .put("status", status)

    companion object {
        fun fromJson(obj: JSONObject): ReplyEvent = ReplyEvent(
            timeMs = obj.getLong("timeMs"),
            sender = obj.getString("sender"),
            message = obj.getString("message"),
            reply = if (obj.isNull("reply")) null else obj.getString("reply"),
            status = obj.getString("status")
        )
    }
}
