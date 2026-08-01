package com.wifinotify.receiver.net

data class IncomingNotify(
    val title: String,
    val message: String,
    val from: String?
) {
    companion object {
        fun parse(line: String): IncomingNotify? {
            val trimmed = line.trim()
            if (trimmed.isEmpty()) return null
            return try {
                fun field(name: String): String? {
                    val key = "\"$name\""
                    val keyIndex = trimmed.indexOf(key)
                    if (keyIndex < 0) return null
                    val colon = trimmed.indexOf(':', keyIndex + key.length)
                    if (colon < 0) return null
                    var i = colon + 1
                    while (i < trimmed.length && trimmed[i].isWhitespace()) i++
                    if (i >= trimmed.length || trimmed[i] != '"') return null
                    i++
                    val sb = StringBuilder()
                    while (i < trimmed.length) {
                        val c = trimmed[i]
                        when {
                            c == '\\' && i + 1 < trimmed.length -> {
                                when (val next = trimmed[i + 1]) {
                                    '"', '\\', '/' -> {
                                        sb.append(next); i += 2
                                    }
                                    'n' -> {
                                        sb.append('\n'); i += 2
                                    }
                                    't' -> {
                                        sb.append('\t'); i += 2
                                    }
                                    else -> {
                                        sb.append(next); i += 2
                                    }
                                }
                            }
                            c == '"' -> return sb.toString()
                            else -> {
                                sb.append(c); i++
                            }
                        }
                    }
                    return null
                }
                val title = field("title")?.ifBlank { null } ?: return null
                val message = field("message")?.ifBlank { null } ?: return null
                IncomingNotify(title = title, message = message, from = field("from"))
            } catch (_: Exception) {
                null
            }
        }
    }
}
