package com.tapshare.app.transfer

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import kotlin.math.sqrt

/**
 * Detects a firm phone-to-phone knock (tops tapping). Tuned to ignore walking /
 * putting the phone down — only sharp spikes count.
 */
class BumpDetector(
    context: Context,
    private val onBump: () -> Unit
) : SensorEventListener {

    private val sensorManager = context.getSystemService(SensorManager::class.java)
    private val accelerometer = sensorManager?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private var lastBumpAt = 0L
    private var lastMagnitude = SensorManager.GRAVITY_EARTH
    private var armedAt = 0L

    fun start() {
        val sensor = accelerometer ?: return
        lastMagnitude = SensorManager.GRAVITY_EARTH
        armedAt = System.currentTimeMillis() + 800L // ignore spikes right as we start
        sensorManager?.registerListener(this, sensor, SensorManager.SENSOR_DELAY_GAME)
    }

    fun stop() {
        try {
            sensorManager?.unregisterListener(this)
        } catch (_: Exception) {
        }
    }

    override fun onSensorChanged(event: SensorEvent?) {
        if (event?.sensor?.type != Sensor.TYPE_ACCELEROMETER) return
        val now = System.currentTimeMillis()
        if (now < armedAt) {
            lastMagnitude = magnitude(event)
            return
        }
        val mag = magnitude(event)
        val delta = kotlin.math.abs(mag - lastMagnitude)
        lastMagnitude = mag
        // Require a hard knock: big delta AND absolute jerk above gravity band.
        if (delta < 18f) return
        if (mag < 16f && mag > 4f && delta < 22f) return
        if (now - lastBumpAt < 2200L) return
        lastBumpAt = now
        onBump()
    }

    private fun magnitude(event: SensorEvent): Float {
        val x = event.values[0]
        val y = event.values[1]
        val z = event.values[2]
        return sqrt(x * x + y * y + z * z)
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
}
