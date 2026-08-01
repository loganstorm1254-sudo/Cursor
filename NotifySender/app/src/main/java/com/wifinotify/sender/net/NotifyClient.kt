package com.wifinotify.sender.net

import android.content.Context
import com.wifinotify.sender.Protocol
import java.io.PrintWriter
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.Socket
import java.nio.charset.StandardCharsets
import kotlin.concurrent.thread

data class DiscoveredReceiver(
    val name: String,
    val host: String,
    val port: Int = Protocol.NOTIFY_PORT
)

object NotifyClient {

    fun discover(
        context: Context,
        timeoutMs: Int = 3500,
        onFound: (DiscoveredReceiver) -> Unit,
        onDone: (List<DiscoveredReceiver>) -> Unit,
        onError: (String) -> Unit
    ) {
        val appContext = context.applicationContext
        thread(name = "wifi-notify-discover", isDaemon = true) {
            val found = linkedMapOf<String, DiscoveredReceiver>()
            val cm = WifiLan.bindProcessToWifi(appContext)
            try {
                DatagramSocket().use { socket ->
                    WifiLan.bindSocket(appContext, socket)
                    socket.broadcast = true
                    socket.soTimeout = 400
                    val payload = Protocol.DISCOVER.toByteArray(StandardCharsets.UTF_8)
                    val targets = discoveryTargets()
                    val deadline = System.currentTimeMillis() + timeoutMs

                    while (System.currentTimeMillis() < deadline) {
                        for (target in targets) {
                            try {
                                val packet = DatagramPacket(
                                    payload,
                                    payload.size,
                                    target,
                                    Protocol.DISCOVERY_PORT
                                )
                                socket.send(packet)
                            } catch (_: Exception) {
                            }
                        }

                        val endBurst = System.currentTimeMillis() + 500
                        while (System.currentTimeMillis() < endBurst &&
                            System.currentTimeMillis() < deadline
                        ) {
                            try {
                                val buf = ByteArray(1024)
                                val response = DatagramPacket(buf, buf.size)
                                socket.receive(response)
                                val text = String(
                                    response.data,
                                    0,
                                    response.length,
                                    StandardCharsets.UTF_8
                                ).trim()
                                if (text.startsWith(Protocol.HERE_PREFIX)) {
                                    val name = text.removePrefix(Protocol.HERE_PREFIX)
                                        .ifBlank { "Receiver" }
                                    val host = response.address.hostAddress ?: continue
                                    val item = DiscoveredReceiver(name = name, host = host)
                                    if (found.put(host, item) == null) {
                                        onFound(item)
                                    }
                                }
                            } catch (_: Exception) {
                                // timeout between polls is expected
                            }
                        }
                    }
                }

                // Fallback: quick unicast probe of the local subnet when broadcast is blocked
                if (found.isEmpty()) {
                    probeSubnet(appContext, found, onFound)
                }

                onDone(found.values.toList())
            } catch (e: Exception) {
                onError(e.message ?: "Discovery failed")
                onDone(found.values.toList())
            } finally {
                WifiLan.clearProcessBind(cm)
            }
        }
    }

    fun send(
        context: Context,
        host: String,
        title: String,
        message: String,
        from: String,
        onSuccess: () -> Unit,
        onError: (String) -> Unit
    ) {
        val appContext = context.applicationContext
        val cleanHost = WifiLan.sanitizeIp(host)
        thread(name = "wifi-notify-send", isDaemon = true) {
            val cm = WifiLan.bindProcessToWifi(appContext)
            try {
                Socket().use { socket ->
                    WifiLan.bindSocket(appContext, socket)
                    socket.tcpNoDelay = true
                    socket.connect(InetSocketAddress(cleanHost, Protocol.NOTIFY_PORT), 8000)
                    socket.soTimeout = 8000
                    val json = buildJson(title, message, from)
                    PrintWriter(socket.getOutputStream(), true, StandardCharsets.UTF_8).use { out ->
                        out.println(json)
                        out.flush()
                    }
                }
                onSuccess()
            } catch (e: Exception) {
                onError(WifiLan.friendlyConnectError(e.message, cleanHost))
            } finally {
                WifiLan.clearProcessBind(cm)
            }
        }
    }

    fun testReachable(
        context: Context,
        host: String,
        onResult: (Boolean, String) -> Unit
    ) {
        val appContext = context.applicationContext
        val cleanHost = WifiLan.sanitizeIp(host)
        thread(name = "wifi-notify-test", isDaemon = true) {
            val cm = WifiLan.bindProcessToWifi(appContext)
            try {
                Socket().use { socket ->
                    WifiLan.bindSocket(appContext, socket)
                    socket.connect(InetSocketAddress(cleanHost, Protocol.NOTIFY_PORT), 5000)
                }
                onResult(true, "Connected to $cleanHost:${Protocol.NOTIFY_PORT}")
            } catch (e: Exception) {
                onResult(false, WifiLan.friendlyConnectError(e.message, cleanHost))
            } finally {
                WifiLan.clearProcessBind(cm)
            }
        }
    }

    private fun probeSubnet(
        context: Context,
        found: MutableMap<String, DiscoveredReceiver>,
        onFound: (DiscoveredReceiver) -> Unit
    ) {
        val local = WifiLan.wifiIpv4Addresses().firstOrNull { it.startsWith("192.168.") }
            ?: WifiLan.wifiIpv4Addresses().firstOrNull()
            ?: return
        val hosts = WifiLan.subnetHosts(local)
        // Probe a limited window around our IP first for speed, then wider
        val localLast = local.substringAfterLast('.').toIntOrNull() ?: return
        val ordered = hosts.sortedBy { ip ->
            val n = ip.substringAfterLast('.').toIntOrNull() ?: 999
            kotlin.math.abs(n - localLast)
        }.take(40)

        for (ip in ordered) {
            if (found.isNotEmpty()) break
            try {
                Socket().use { socket ->
                    WifiLan.bindSocket(context, socket)
                    socket.soTimeout = 250
                    socket.connect(InetSocketAddress(ip, Protocol.NOTIFY_PORT), 250)
                    val item = DiscoveredReceiver(name = "Receiver", host = ip)
                    if (found.put(ip, item) == null) onFound(item)
                }
            } catch (_: Exception) {
            }
        }
    }

    private fun buildJson(title: String, message: String, from: String): String {
        fun esc(s: String): String = buildString {
            for (c in s) {
                when (c) {
                    '\\' -> append("\\\\")
                    '"' -> append("\\\"")
                    '\n' -> append("\\n")
                    '\r' -> append("\\r")
                    '\t' -> append("\\t")
                    else -> append(c)
                }
            }
        }
        return """{"title":"${esc(title)}","message":"${esc(message)}","from":"${esc(from)}"}"""
    }

    private fun discoveryTargets(): List<InetAddress> {
        val targets = linkedSetOf<InetAddress>()
        try {
            targets += InetAddress.getByName("255.255.255.255")
        } catch (_: Exception) {
        }
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces() ?: return targets.toList()
            for (iface in interfaces) {
                if (!iface.isUp || iface.isLoopback) continue
                for (addr in iface.interfaceAddresses) {
                    val broadcast = addr.broadcast ?: continue
                    targets += broadcast
                }
            }
        } catch (_: Exception) {
        }
        return targets.toList()
    }
}
