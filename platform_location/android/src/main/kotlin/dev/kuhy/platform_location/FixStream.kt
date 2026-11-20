package dev.kuhy.platform_location

import android.content.Context
import android.location.Location
import androidx.core.content.ContextCompat
import androidx.core.location.LocationListenerCompat
import androidx.core.location.LocationManagerCompat
import androidx.core.location.LocationRequestCompat
import io.flutter.plugin.common.EventChannel

/**
 * The `dev.kuhy/platform_location/fixes` stream: LocationManager updates on
 * the main looper, removed on cancel. Errors end the Dart stream's listen
 * with a PlatformException ("unavailable", "denied", "provider_disabled").
 */
internal class FixStream(private val ctx: Context) : EventChannel.StreamHandler {

    private var listener: LocationListenerCompat? = null

    override fun onListen(arguments: Any?, sink: EventChannel.EventSink) {
        stop()
        val intervalMs = ((arguments as? Map<*, *>)?.get("intervalMs") as? Number)
            ?.toLong() ?: DEFAULT_INTERVAL_MS
        val lm = PlatformLocationPlugin.locationManager(ctx)
        val provider = PlatformLocationPlugin.pickProvider(ctx, lm)
            ?: return sink.error("unavailable", "no permission or provider", null)
        val request = LocationRequestCompat.Builder(intervalMs)
            .setQuality(LocationRequestCompat.QUALITY_HIGH_ACCURACY)
            .setMinUpdateIntervalMillis(intervalMs / 2)
            .build()
        val l = object : LocationListenerCompat {
            override fun onLocationChanged(location: Location) {
                sink.success(PlatformLocationPlugin.toMap(location))
            }

            override fun onProviderDisabled(disabled: String) {
                if (disabled == provider) {
                    sink.error("provider_disabled", "$provider was switched off", null)
                }
            }
        }
        try {
            LocationManagerCompat.requestLocationUpdates(
                lm,
                provider,
                request,
                ContextCompat.getMainExecutor(ctx),
                l,
            )
            listener = l
        } catch (e: SecurityException) {
            sink.error("denied", e.message, null)
        }
    }

    override fun onCancel(arguments: Any?) = stop()

    private fun stop() {
        val l = listener ?: return
        listener = null
        LocationManagerCompat.removeUpdates(PlatformLocationPlugin.locationManager(ctx), l)
    }

    private companion object {
        const val DEFAULT_INTERVAL_MS = 2000L
    }
}
