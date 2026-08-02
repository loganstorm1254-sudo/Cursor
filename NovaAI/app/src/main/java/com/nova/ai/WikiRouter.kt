package com.nova.ai

import java.util.Locale

/**
 * Decides when a message should be answered from Wikipedia instead of the
 * local model:
 *  - explicit commands ("search …", "wikipedia …", "look up …") always go
 *    to Wikipedia;
 *  - knowledge questions ("who is …", "what is …", "tell me about …") go to
 *    Wikipedia only when the subject contains a word the local model was
 *    never trained on — everything Nova knows stays on-device.
 */
object WikiRouter {

    private val EXPLICIT = Regex(
        "^(?:search|wiki|wikipedia|look ?up|google)(?: for| up| about)?\\s+(.+)$")
    private val QUESTION = Regex(
        "^(?:who is|who was|who are|who were|what is|what are|what was|whats|" +
            "tell me about|what do you know about|define|explain)\\s+(.+)$")

    fun subjectFor(message: String, knowsWord: (String) -> Boolean): String? {
        val t = message.trim().lowercase(Locale.US).trimEnd('?', '!', '.', ' ')
        if (t.isEmpty()) return null

        EXPLICIT.find(t)?.let { return cleanSubject(it.groupValues[1]) }

        val m = QUESTION.find(t) ?: return null
        val subject = cleanSubject(m.groupValues[1])
        val words = subject.split(Regex("[^a-z0-9]+")).filter { it.isNotEmpty() }
        if (words.isEmpty()) return null
        return if (words.any { !knowsWord(it) }) subject else null
    }

    private fun cleanSubject(s: String): String {
        var out = s.trim().trimEnd('?', '!', '.', ' ')
        for (article in listOf("a ", "an ", "the ")) {
            if (out.startsWith(article)) {
                out = out.removePrefix(article)
                break
            }
        }
        return out.trim()
    }
}
