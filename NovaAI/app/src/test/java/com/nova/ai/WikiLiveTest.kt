package com.nova.ai

import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * Hits the real Wikipedia API. Runs only when -DrunLiveTests=true is set so
 * normal builds stay offline-friendly.
 */
class WikiLiveTest {

    @Test
    fun looksUpRealArticles() {
        assumeTrue(System.getProperty("runLiveTests") == "true")
        val res = WikiClient.lookup("albert einstein")
        println("TITLE: ${res?.title}\nEXTRACT: ${res?.extract}")
        assertTrue(res != null && res.title.contains("Einstein") &&
                res.extract.length > 50)

        val res2 = WikiClient.lookup("quantum physics")
        println("TITLE: ${res2?.title}\nEXTRACT: ${res2?.extract}")
        assertTrue(res2 != null && res2.extract.length > 50)
    }
}
