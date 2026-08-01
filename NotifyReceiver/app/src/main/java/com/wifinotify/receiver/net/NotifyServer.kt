package com.wifinotify.receiver.net

import com.wifinotify.receiver.Protocol
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.ServerSocket
import java.net.SocketException
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

class NotifyServer(
    private val deviceNameProvider: () -> String,
    private val onNotify: (IncomingNotify, String) -> Unit,
    private val onStatus: (String) -> Unit
) {
    private val running = AtomicBoolean(false)
    private var discoverySocket: DatagramSocket? = null
    private var serverSocket: ServerSocket? = null

    fun start() {
        if (!running.compareAndSet(false, true)) return
        startDiscovery()
        startTcp()
        onStatus("Listening on Wi‑Fi (port ${Protocol.NOTIFY_PORT})")
    }

    fun stop() {
        running.set(false)
        try {
            discoverySocket?.close()
        } catch (_: Exception) {
        }
        try {
            serverSocket?.close()
        } catch (_: Exception) {
        }
        discoverySocket = null
        serverSocket = null
        onStatus("Stopped")
    }

    private fun startDiscovery() {
        thread(name = "wifi-notify-discovery", isDaemon = true) {
            try {
                val socket = DatagramSocket(Protocol.DISCOVERY_PORT).also {
                    it.broadcast = true
                    it.reuseAddress = true
                    discoverySocket = it
                }
                val buf = ByteArray(1024)
                while (running.get()) {
                    try {
                        val packet = DatagramPacket(buf, buf.size)
                        socket.receive(packet)
                        val text = String(packet.data, 0, packet.length, Charsets.UTF_8).trim()
                        if (text == Protocol.DISCOVER) {
                            val reply = (Protocol.HERE_PREFIX + deviceNameProvider())
                                .toByteArray(Charsets.UTF_8)
                            val response = DatagramPacket(
                                reply,
                                reply.size,
                                packet.address,
                                packet.port
                            )
                            socket.send(response)
                        }
                    } catch (_: SocketException) {
                        if (!running.get()) break
                    } catch (e: Exception) {
                        if (running.get()) onStatus("Discovery error: ${e.message}")
                    }
                }
            } catch (e: Exception) {
                onStatus("Could not bind discovery port: ${e.message}")
            }
        }
    }

    private fun startTcp() {
        thread(name = "wifi-notify-tcp", isDaemon = true) {
            try {
                val server = ServerSocket(Protocol.NOTIFY_PORT).also { serverSocket = it }
                while (running.get()) {
                    try {
                        val client = server.accept()
                        thread(name = "wifi-notify-client", isDaemon = true) {
                            handleClient(client)
                        }
                    } catch (_: SocketException) {
                        if (!running.get()) break
                    } catch (e: Exception) {
                        if (running.get()) onStatus("Accept error: ${e.message}")
                    }
                }
            } catch (e: Exception) {
                onStatus("Could not bind notify port: ${e.message}")
            }
        }
    }

    private fun handleClient(client: java.net.Socket) {
        client.use { socket ->
            socket.soTimeout = 10_000
            val remote = socket.inetAddress.hostAddress ?: "unknown"
            val line = socket.getInputStream().bufferedReader(Charsets.UTF_8).readLine()
                ?: return
            val notify = IncomingNotify.parse(line)
            if (notify != null) {
                onNotify(notify, remote)
            } else {
                onStatus("Ignored invalid payload from $remote")
            }
        }
    }
}

fun localIpv4Addresses(): List<String> {
    val result = mutableListOf<String>()
    try {
        val interfaces = java.net.NetworkInterface.getNetworkInterfaces() ?: return result
        for (iface in interfaces) {
            if (!iface.isUp || iface.isLoopback) continue
            for (addr in iface.inetAddresses) {
                if (addr is java.net.Inet4Address && !addr.isLoopbackAddress) {
                    result += addr.hostAddress ?: continue
                }
            }
        }
    } catch (_: Exception) {
    }
    return result
}

fun broadcastAddress(): InetAddress? {
    return try {
        InetAddress.getByName("255.255.255.255")
    } catch (_: Exception) {
        null
    }
}
