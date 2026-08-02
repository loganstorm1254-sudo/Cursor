package com.nova.ai

import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** Minimal Wikipedia REST client — no dependencies, dead simple. */
object WikiClient {

    data class Result(val title: String, val extract: String)

    private const val UA = "NovaAI-Android/1.1 (personal offline AI companion app)"

    fun lookup(query: String): Result? {
        return try {
            val key = searchTitleKey(query) ?: return null
            val json = get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/" +
                    URLEncoder.encode(key, "UTF-8").replace("+", "%20")
            ) ?: return null
            val title = extractJsonString(json, "title") ?: key.replace('_', ' ')
            var extract = extractJsonString(json, "extract") ?: return null
            if (extract.isBlank()) return null
            if (extract.length > 700) {
                val cut = extract.lastIndexOf(". ", 700)
                extract = if (cut > 200) extract.substring(0, cut + 1)
                else extract.substring(0, 700) + "…"
            }
            Result(title, extract)
        } catch (e: Exception) {
            null
        }
    }

    private fun searchTitleKey(query: String): String? {
        val json = get(
            "https://en.wikipedia.org/w/rest.php/v1/search/title?q=" +
                URLEncoder.encode(query, "UTF-8") + "&limit=1"
        ) ?: return null
        if ("\"pages\":[]" in json.replace(" ", "")) return null
        return extractJsonString(json, "key")
    }

    private fun get(url: String): String? {
        val conn = URL(url).openConnection() as HttpURLConnection
        return try {
            conn.connectTimeout = 8000
            conn.readTimeout = 8000
            conn.setRequestProperty("User-Agent", UA)
            conn.setRequestProperty("Accept", "application/json")
            if (conn.responseCode != 200) null
            else conn.inputStream.readBytes().toString(Charsets.UTF_8)
        } finally {
            conn.disconnect()
        }
    }

    /** Pull the first string value of a JSON field, unescaping it. */
    fun extractJsonString(json: String, field: String): String? {
        val m = Regex("\"$field\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"").find(json)
            ?: return null
        val raw = m.groupValues[1]
        val sb = StringBuilder(raw.length)
        var i = 0
        while (i < raw.length) {
            val c = raw[i]
            if (c == '\\' && i + 1 < raw.length) {
                when (val n = raw[i + 1]) {
                    'n' -> { sb.append('\n'); i += 2 }
                    't' -> { sb.append('\t'); i += 2 }
                    'r' -> { i += 2 }
                    'u' -> {
                        if (i + 5 < raw.length) {
                            sb.append(raw.substring(i + 2, i + 6).toInt(16).toChar())
                            i += 6
                        } else i += 2
                    }
                    else -> { sb.append(n); i += 2 }
                }
            } else {
                sb.append(c); i++
            }
        }
        return sb.toString()
    }
}
