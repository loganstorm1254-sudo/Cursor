package com.nova.ai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class WikiRouterTest {

    // pretend the model only knows these words
    private val known = setOf(
        "what", "is", "the", "a", "an", "who", "gravity", "sun", "capital",
        "of", "france", "tell", "me", "joke", "about", "3", "plus", "colors",
        "name", "define", "love")

    private fun route(msg: String) = WikiRouter.subjectFor(msg) { it in known }

    @Test
    fun explicitSearchAlwaysGoesToWiki() {
        assertEquals("gravity", route("search gravity"))
        assertEquals("black holes", route("wikipedia black holes"))
        assertEquals("albert einstein", route("look up albert einstein"))
        assertEquals("eiffel tower", route("search for the eiffel tower"))
    }

    @Test
    fun unknownSubjectsGoToWiki() {
        assertEquals("quantum physics", route("what is quantum physics?"))
        assertEquals("albert einstein", route("who is albert einstein"))
        assertEquals("black hole", route("what is a black hole?"))
        assertEquals("photosynthesis", route("tell me about photosynthesis"))
    }

    @Test
    fun knownSubjectsStayLocal() {
        assertNull(route("what is gravity"))
        assertNull(route("what is the capital of france"))
        assertNull(route("define love"))
    }

    @Test
    fun chatMessagesStayLocal() {
        assertNull(route("tell me a joke"))
        assertNull(route("hello"))
        assertNull(route("name 3 colors"))
        assertNull(route("what is 3 plus 3"))
    }
}

class WikiClientJsonTest {

    @Test
    fun extractsAndUnescapesJsonStrings() {
        val json = """{"title":"Black hole","extract":"A black hole is a region.\nIt \"warps\" space \u2014 a lot."}"""
        assertEquals("Black hole", WikiClient.extractJsonString(json, "title"))
        assertEquals(
            "A black hole is a region.\nIt \"warps\" space \u2014 a lot.",
            WikiClient.extractJsonString(json, "extract"))
    }

    @Test
    fun missingFieldReturnsNull() {
        assertNull(WikiClient.extractJsonString("""{"a":"b"}""", "extract"))
    }
}
