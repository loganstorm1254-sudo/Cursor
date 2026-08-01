package com.wifinotify.sender.net

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
        timeoutMs: Int = 2500,
        onFound: (DiscoveredReceiver) -> Unit,
        onDone: (List<DiscoveredReceiver>) -> Unit,
        onError: (String) -> Unit
    ) {
        thread(name = "wifi-notify-discover", isDaemon = true) {
            val found = linkedMapOf<String, DiscoveredReceiver>()
            try {
                DatagramSocket().use { socket ->
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
                onDone(found.values.toList())
            } catch (e: Exception) {
                onError(e.message ?: "Discovery failed")
                onDone(found.values.toList())
            }
        }
    }

    fun send(
        host: String,
        title: String,
        message: String,
        from: String,
        onSuccess: () -> Unit,
        onError: (String) -> Unit
    ) {
        thread(name = "wifi-notify-send", isDaemon = true) {
            try {
                Socket().use { socket ->
                    socket.connect(InetSocketAddress(host, Protocol.NOTIFY_PORT), 5000)
                    socket.soTimeout = 5000
                    val json = buildJson(title, message, from)
                    PrintWriter(socket.getOutputStream(), true, StandardCharsets.UTF_8).use { out ->
                        out.println(json)
                    }
                }
                onSuccess()
            } catch (e: Exception) {
                onError(e.message ?: "Send failed")
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
