package com.nova.ai

import java.util.Locale

/**
 * Decides when a message should be answered from Wikipedia instead of the
 * local model:
 *  - explicit commands ("search …", "wikipedia …", "look up …") always go
 *    to Wikipedia;
 *  - knowledge questions ("who is …", "what is …", "tell me about …") go to
 *    Wikipedia when the subject contains a word the local model was never
 *    trained on, OR when it is a multi-word subject outside the question
 *    shapes Nova was trained to answer (e.g. "black hole": both words are in
 *    her vocabulary but the concept is not).
 */
object WikiRouter {

    private val EXPLICIT = Regex(
        "^(?:search|wiki|wikipedia|look ?up|google)(?: for| up| about)?\\s+(.+)$")
    private val QUESTION = Regex(
        "^(?:who is|who was|who are|who were|what is|what are|what was|whats|" +
            "tell me about|what do you know about|define|explain)\\s+(.+)$")

    /** Words marking multi-word subjects Nova handles locally
     *  (trained question shapes and multi-word definitions). */
    private val LOCAL_HINTS = setOf(
        "capital", "opposite", "plus", "minus", "times", "divided", "favorite",
        "favourite", "weather", "time", "news", "name", "your", "you", "neural",
        "machine", "artificial", "api", "nova", "seasons", "days", "months",
        "planets", "colors", "colours", "rainbow", "week", "year",
        // trained question shapes: superlatives, word games, translations…
        "largest", "smallest", "biggest", "fastest", "slowest", "tallest",
        "hottest", "closest", "nearest", "longest", "strongest", "king",
        "word", "another", "synonym", "baby", "called", "speed", "made",
        "senses", "shooting", "planet", "double", "half", "twice", "squared",
        "spanish", "french", "german", "italian", "japanese", "oceans",
        "continents", "vowels", "chemical", "symbol", "element", "riddle",
        "moons", "letter")

    fun subjectFor(message: String, knowsWord: (String) -> Boolean): String? {
        val t = message.trim().lowercase(Locale.US).trimEnd('?', '!', '.', ' ')
        if (t.isEmpty()) return null

        EXPLICIT.find(t)?.let { return cleanSubject(it.groupValues[1]) }

        val m = QUESTION.find(t) ?: return null
        val subject = cleanSubject(m.groupValues[1])
        val words = subject.split(Regex("[^a-z0-9]+")).filter { it.isNotEmpty() }
        if (words.isEmpty()) return null
        val hasUnknownWord = words.any { !knowsWord(it) }
        val novelMultiWord = words.size >= 2 &&
            words.none { it in LOCAL_HINTS } &&
            words.none { w -> w.all { it.isDigit() } }
        return if (hasUnknownWord || novelMultiWord) subject else null
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
