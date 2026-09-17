package com.shortsblocker.app.service

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.shortsblocker.app.Prefs
import com.shortsblocker.app.ui.BlockOverlayActivity

/**
 * Watches YouTube + TikTok and only interrupts short-form feeds.
 * Regular YouTube watch pages and TikTok inbox/profile/search/live stay usable.
 */
class ShortsAccessibilityService : AccessibilityService() {

    private val handler = Handler(Looper.getMainLooper())
    private var lastActionAt = 0L
    private var lastPackage: String? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        serviceInfo = serviceInfo?.apply {
            packageNames = arrayOf(
                "com.google.android.youtube",
                "app.revanced.android.youtube",
                "com.zhiliaoapp.musically",
                "com.ss.android.ugc.trill"
            )
        }
        startForegroundGuard()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        if (!Prefs.isEnabled(this)) return

        val pkg = event.packageName?.toString() ?: return
        lastPackage = pkg

        when {
            isYoutube(pkg) && Prefs.blockYoutube(this) -> maybeBlockYoutube()
            isTiktok(pkg) && Prefs.blockTiktok(this) -> maybeBlockTiktok()
        }
    }

    override fun onInterrupt() = Unit

    private fun maybeBlockYoutube() {
        val root = rootInActiveWindow ?: return
        try {
            if (looksLikeYoutubeShorts(root)) {
                bounceOut(reason = "youtube_shorts")
            }
        } finally {
            root.recycle()
        }
    }

    private fun maybeBlockTiktok() {
        val root = rootInActiveWindow ?: return
        try {
            // Allow non-feed surfaces: inbox, profile, friends list, search, live, settings, camera.
            if (isTiktokAllowedSurface(root)) return
            if (looksLikeTiktokShortFeed(root)) {
                bounceOut(reason = "tiktok_shorts")
            }
        } finally {
            root.recycle()
        }
    }

    private fun bounceOut(reason: String) {
        val now = SystemClock.elapsedRealtime()
        if (now - lastActionAt < COOLDOWN_MS) return
        lastActionAt = now

        Prefs.incrementBlocks(this)

        // Back out of the short player first; if still trapped, leave to our overlay.
        performGlobalAction(GLOBAL_ACTION_BACK)
        handler.postDelayed({
            val pkg = lastPackage ?: return@postDelayed
            if ((isYoutube(pkg) && Prefs.blockYoutube(this)) ||
                (isTiktok(pkg) && Prefs.blockTiktok(this))
            ) {
                val still = rootInActiveWindow
                try {
                    val trapped = when {
                        isYoutube(pkg) -> still != null && looksLikeYoutubeShorts(still)
                        else -> still != null &&
                            !isTiktokAllowedSurface(still) &&
                            looksLikeTiktokShortFeed(still)
                    }
                    if (trapped) {
                        val intent = Intent(this, BlockOverlayActivity::class.java).apply {
                            addFlags(
                                Intent.FLAG_ACTIVITY_NEW_TASK or
                                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                                    Intent.FLAG_ACTIVITY_SINGLE_TOP
                            )
                            putExtra(BlockOverlayActivity.EXTRA_REASON, reason)
                        }
                        startActivity(intent)
                    }
                } finally {
                    still?.recycle()
                }
            }
        }, 350)
    }

    private fun looksLikeYoutubeShorts(root: AccessibilityNodeInfo): Boolean {
        // Strong signals for the Shorts player / Shorts tab.
        val idHits = listOf(
            "com.google.android.youtube:id/reel_recycler",
            "com.google.android.youtube:id/reel_player_page_container",
            "com.google.android.youtube:id/reel_player_underlay",
            "com.google.android.youtube:id/shorts_player",
            "com.google.android.youtube:id/reel_watch_fragment_root",
            "app.revanced.android.youtube:id/reel_recycler",
            "app.revanced.android.youtube:id/reel_player_page_container"
        )
        if (idHits.any { root.findAccessibilityNodeInfosByViewId(it).isNotEmpty() }) {
            return true
        }

        // Content-description / text fallbacks used across YouTube versions.
        if (hasTextOrDesc(root, "shorts", exactWord = true)) {
            // Avoid false positives on search results mentioning "shorts" in titles:
            // only treat as Shorts UI when a Shorts chrome cue is also present.
            val chrome = hasTextOrDesc(root, "subscribe") ||
                hasTextOrDesc(root, "like this video") ||
                hasTextOrDesc(root, "dislike this video") ||
                (hasTextOrDesc(root, "share") && hasTextOrDesc(root, "remix"))
            if (chrome) return true
        }

        // Selected Shorts tab in bottom nav.
        if (hasSelectedTab(root, "Shorts")) return true

        return false
    }

    private fun looksLikeTiktokShortFeed(root: AccessibilityNodeInfo): Boolean {
        // Vertical short feed / For You surface.
        val feedIds = listOf(
            "com.zhiliaoapp.musically:id/viewpager",
            "com.zhiliaoapp.musically:id/feed_video",
            "com.ss.android.ugc.trill:id/viewpager",
            "com.ss.android.ugc.trill:id/feed_video"
        )
        val feedHit = feedIds.any { root.findAccessibilityNodeInfosByViewId(it).isNotEmpty() }

        val forYouSelected = hasSelectedTab(root, "For You") ||
            hasSelectedTab(root, "Home") ||
            hasSelectedTab(root, "Following")

        // Following is also a short feed — block it too. Friends/Inbox/Profile are allowed elsewhere.
        if (forYouSelected) return true
        if (feedHit && !isTiktokAllowedSurface(root)) return true

        // Like / comment / share column typical of vertical short UI with no long-form chrome.
        val shortChrome = hasTextOrDesc(root, "Like") &&
            hasTextOrDesc(root, "Comment") &&
            hasTextOrDesc(root, "Share") &&
            (hasTextOrDesc(root, "For You") || hasTextOrDesc(root, "Following"))
        return shortChrome
    }

    private fun isTiktokAllowedSurface(root: AccessibilityNodeInfo): Boolean {
        // Keep messaging, profile, friends hub, search, live, create, settings usable.
        if (hasSelectedTab(root, "Inbox") ||
            hasSelectedTab(root, "Profile") ||
            hasSelectedTab(root, "Friends") ||
            hasSelectedTab(root, "Shop")
        ) {
            return true
        }

        val allowHints = listOf(
            "Messages", "Activity", "Notifications", "Settings", "Edit profile",
            "Add friends", "Search", "LIVE", "Go LIVE", "Create", "Drafts",
            "Balance", "Creator tools", "Privacy", "Security"
        )
        if (allowHints.any { hasTextOrDesc(root, it) } &&
            !hasSelectedTab(root, "For You") &&
            !hasSelectedTab(root, "Home")
        ) {
            return true
        }
        return false
    }

    private fun hasSelectedTab(root: AccessibilityNodeInfo, label: String): Boolean {
        val nodes = mutableListOf<AccessibilityNodeInfo>()
        collectByTextOrDesc(root, label, nodes)
        return nodes.any { it.isSelected || it.isChecked || it.isAccessibilityFocused }
    }

    private fun hasTextOrDesc(
        node: AccessibilityNodeInfo,
        needle: String,
        exactWord: Boolean = false
    ): Boolean {
        val n = needle.lowercase()
        val text = sequenceOf(node.text, node.contentDescription)
            .mapNotNull { it?.toString()?.lowercase() }
        val hit = text.any { t ->
            if (exactWord) Regex("""\b${Regex.escape(n)}\b""").containsMatchIn(t)
            else t.contains(n)
        }
        if (hit) return true
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            try {
                if (hasTextOrDesc(child, needle, exactWord)) return true
            } finally {
                child.recycle()
            }
        }
        return false
    }

    private fun collectByTextOrDesc(
        node: AccessibilityNodeInfo,
        needle: String,
        out: MutableList<AccessibilityNodeInfo>
    ) {
        val n = needle.lowercase()
        val text = node.text?.toString()?.lowercase().orEmpty()
        val desc = node.contentDescription?.toString()?.lowercase().orEmpty()
        if (text == n || desc == n || text.contains(n) || desc.contains(n)) {
            out.add(AccessibilityNodeInfo.obtain(node))
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            try {
                collectByTextOrDesc(child, needle, out)
            } finally {
                child.recycle()
            }
        }
    }

    private fun startForegroundGuard() {
        val intent = Intent(this, ShortsGuardService::class.java)
        try {
            startForegroundService(intent)
        } catch (_: Exception) {
            startService(intent)
        }
    }

    companion object {
        private const val COOLDOWN_MS = 900L

        fun isYoutube(pkg: String) =
            pkg == "com.google.android.youtube" || pkg == "app.revanced.android.youtube"

        fun isTiktok(pkg: String) =
            pkg == "com.zhiliaoapp.musically" || pkg == "com.ss.android.ugc.trill"
    }
}
