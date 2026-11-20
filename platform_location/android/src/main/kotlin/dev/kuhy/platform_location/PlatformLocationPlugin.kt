package dev.kuhy.platform_location

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.location.LocationCompat
import androidx.core.location.LocationManagerCompat
import androidx.core.os.CancellationSignal
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.PluginRegistry

/**
 * Location through AOSP's LocationManager (androidx LocationManagerCompat).
 * No Google Play services. The Dart side is `lib/platform_location.dart`.
 *
 * Only requestPermission needs an Activity; everything else works in a
 * background engine (foreground-service isolate) too.
 */
class PlatformLocationPlugin :
    FlutterPlugin,
    ActivityAware,
    MethodChannel.MethodCallHandler,
    PluginRegistry.RequestPermissionsResultListener {

    private var context: Context? = null
    private var channel: MethodChannel? = null
    private var events: EventChannel? = null
    private var fixStream: FixStream? = null
    private var binding: ActivityPluginBinding? = null
    private var pendingPermission: MethodChannel.Result? = null

    override fun onAttachedToEngine(flutter: FlutterPlugin.FlutterPluginBinding) {
        val ctx = flutter.applicationContext
        context = ctx
        channel = MethodChannel(flutter.binaryMessenger, CHANNEL).also {
            it.setMethodCallHandler(this)
        }
        val stream = FixStream(ctx)
        fixStream = stream
        events = EventChannel(flutter.binaryMessenger, "$CHANNEL/fixes").also {
            it.setStreamHandler(stream)
        }
    }

    override fun onDetachedFromEngine(flutter: FlutterPlugin.FlutterPluginBinding) {
        channel?.setMethodCallHandler(null)
        events?.setStreamHandler(null)
        fixStream?.onCancel(null)
        channel = null
        events = null
        fixStream = null
        context = null
    }

    override fun onAttachedToActivity(activityBinding: ActivityPluginBinding) {
        binding = activityBinding
        activityBinding.addRequestPermissionsResultListener(this)
    }

    override fun onDetachedFromActivityForConfigChanges() = detach()

    override fun onReattachedToActivityForConfigChanges(
        activityBinding: ActivityPluginBinding,
    ) = onAttachedToActivity(activityBinding)

    override fun onDetachedFromActivity() {
        detach()
        pendingPermission?.error("no_activity", "activity went away", null)
        pendingPermission = null
    }

    private fun detach() {
        binding?.removeRequestPermissionsResultListener(this)
        binding = null
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        val ctx = context ?: return result.error("no_context", "detached", null)
        when (call.method) {
            "isLocationEnabled" -> result.success(locationEnabled(ctx))
            "checkPermission" ->
                result.success(if (hasAny(ctx)) GRANTED else DENIED)
            "requestPermission" ->
                request(ctx, call.argument<Boolean>("precise") ?: true, result)
            "currentLocation" -> current(ctx, result)
            else -> result.notImplemented()
        }
    }

    private fun request(ctx: Context, precise: Boolean, result: MethodChannel.Result) {
        if (hasAny(ctx)) return result.success(GRANTED)
        val activity = binding?.activity
            ?: return result.error("no_activity", "no foreground activity", null)
        if (pendingPermission != null) {
            return result.error("busy", "a permission request is in flight", null)
        }
        pendingPermission = result
        val perms = if (precise) {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, COARSE)
        } else {
            arrayOf(COARSE)
        }
        ActivityCompat.requestPermissions(activity, perms, REQUEST_CODE)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ): Boolean {
        if (requestCode != REQUEST_CODE) return false
        val result = pendingPermission ?: return true
        pendingPermission = null
        val granted = grantResults.any { it == PackageManager.PERMISSION_GRANTED }
        result.success(
            when {
                granted -> GRANTED
                // No rationale after a refusal means "don't ask again" (or a
                // policy block): the prompt will not show any more.
                binding?.activity?.let { permanentlyDenied(it) } == true ->
                    DENIED_FOREVER
                else -> DENIED
            },
        )
        return true
    }

    private fun permanentlyDenied(activity: Activity): Boolean =
        !ActivityCompat.shouldShowRequestPermissionRationale(activity, COARSE)

    private fun current(ctx: Context, result: MethodChannel.Result) {
        val lm = locationManager(ctx)
        val provider = pickProvider(ctx, lm)
            ?: return result.error("unavailable", "no permission or provider", null)
        var answered = false
        val reply = { location: Location? ->
            if (!answered) {
                answered = true
                val fix = location ?: lastKnown(lm, ctx)
                if (fix == null) {
                    result.error("no_fix", "no location from $provider", null)
                } else {
                    result.success(toMap(fix))
                }
            }
        }
        try {
            LocationManagerCompat.getCurrentLocation(
                lm,
                provider,
                CancellationSignal(),
                ContextCompat.getMainExecutor(ctx),
            ) { reply(it) }
        } catch (e: SecurityException) {
            result.error("denied", e.message, null)
        }
    }

    // A one-shot request can time out indoors; the newest cached fix from
    // any enabled provider is good enough for a coarse "where am I".
    private fun lastKnown(lm: LocationManager, ctx: Context): Location? {
        if (!hasAny(ctx)) return null
        return try {
            lm.getProviders(true)
                .mapNotNull { lm.getLastKnownLocation(it) }
                .maxByOrNull { it.time }
        } catch (_: SecurityException) {
            null
        }
    }

    companion object {
        const val CHANNEL = "dev.kuhy/platform_location"
        private const val REQUEST_CODE = 0x10c4
        private const val COARSE = Manifest.permission.ACCESS_COARSE_LOCATION
        private const val GRANTED = "granted"
        private const val DENIED = "denied"
        private const val DENIED_FOREVER = "deniedForever"

        fun locationManager(ctx: Context): LocationManager =
            ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager

        fun locationEnabled(ctx: Context): Boolean =
            LocationManagerCompat.isLocationEnabled(locationManager(ctx))

        fun hasFine(ctx: Context): Boolean = ContextCompat.checkSelfPermission(
            ctx,
            Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED

        fun hasAny(ctx: Context): Boolean = hasFine(ctx) ||
            ContextCompat.checkSelfPermission(ctx, COARSE) ==
            PackageManager.PERMISSION_GRANTED

        /**
         * GPS when fine location is granted and GPS is on; otherwise the
         * platform fused provider (AOSP, Android 12+) or the network one.
         * Null when no permission or no enabled provider fits.
         */
        fun pickProvider(ctx: Context, lm: LocationManager): String? {
            if (!hasAny(ctx)) return null
            val enabled = lm.getProviders(true)
            val order = buildList {
                if (hasFine(ctx)) add(LocationManager.GPS_PROVIDER)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    add(LocationManager.FUSED_PROVIDER)
                }
                add(LocationManager.NETWORK_PROVIDER)
                add(LocationManager.GPS_PROVIDER)
            }
            return order.firstOrNull { it in enabled }
        }

        fun toMap(l: Location): Map<String, Any> = mapOf(
            "time" to l.time,
            "latitude" to l.latitude,
            "longitude" to l.longitude,
            "altitude" to if (l.hasAltitude()) l.altitude else 0.0,
            "accuracy" to if (l.hasAccuracy()) l.accuracy.toDouble() else 0.0,
            "isMock" to LocationCompat.isMock(l),
        )
    }
}
