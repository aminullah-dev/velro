package af.velro.core.ui.component

import af.velro.core.ui.theme.Radius
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.Dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Decode bytes to a bitmap, bounded, off the composition.
 *
 * Every image in this product is a photograph taken on the driver's own phone,
 * and a modern camera produces something far larger than any view that shows
 * it. Decoding one at full resolution on the main thread is how a cheap
 * handset runs out of memory -- so the size is measured first and the decode
 * is asked for a sample of it, which means the large bitmap never exists at
 * all rather than existing briefly.
 *
 * Shared because the two callers -- the document thumbnail and the profile
 * photograph -- were about to hold two copies of the same careful arithmetic,
 * and the second copy is where the bound gets forgotten.
 *
 * A null result is a placeholder, never an error: these arrive after the
 * screen and may not arrive at all, and nothing here is load-bearing enough
 * to interrupt somebody over.
 */
@Composable
fun rememberDecodedPhoto(bytes: ByteArray?, maxPx: Int = DEFAULT_MAX_PX): State<Bitmap?> =
    produceState<Bitmap?>(initialValue = null, bytes, maxPx) {
        val data = bytes
        value = if (data == null) null else withContext(Dispatchers.Default) {
            runCatching {
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(data, 0, data.size, bounds)
                var sample = 1
                // inSampleSize halves in powers of two; anything else is
                // rounded down to one by the decoder, so counting up in
                // doublings is the only thing it actually honours.
                while (bounds.outHeight / sample > maxPx || bounds.outWidth / sample > maxPx) {
                    sample *= 2
                }
                BitmapFactory.decodeByteArray(
                    data, 0, data.size,
                    BitmapFactory.Options().apply { inSampleSize = sample },
                )
            }.getOrNull()
        }
    }

/**
 * The driver's own face, round.
 *
 * The bytes are the selfie he already sent for approval rather than a second
 * photograph he has to go and find. It was uploaded, checked by the office,
 * and until now only ever looked at by the office.
 *
 * Falls back to a silhouette rather than to emptiness: a driver who has not
 * sent one yet should see a space shaped like a person, which says what is
 * missing, instead of a grey circle that says nothing.
 */
@Composable
fun PhotoAvatar(
    bytes: ByteArray?,
    size: Dp,
    modifier: Modifier = Modifier,
) {
    val bitmap by rememberDecodedPhoto(bytes, maxPx = AVATAR_MAX_PX)
    Box(
        modifier
            .size(size)
            .clip(CircleShape)
            .background(MaterialTheme.colorScheme.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) {
        val image = bitmap
        if (image != null) {
            Image(
                bitmap = image.asImageBitmap(),
                // The name is directly beneath it, so announcing the picture
                // as well would have a screen reader say the same person twice.
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        } else {
            Icon(
                Icons.Filled.Person,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(size / 2),
            )
        }
    }
}

/** A document as sent, in a card. Rectangular, because papers are. */
@Composable
fun PhotoThumbnail(
    bytes: ByteArray?,
    modifier: Modifier = Modifier,
) {
    val bitmap by rememberDecodedPhoto(bytes)
    Box(
        modifier
            .clip(RoundedCornerShape(Radius.md))
            .background(MaterialTheme.colorScheme.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) {
        val image = bitmap
        if (image != null) {
            Image(
                bitmap = image.asImageBitmap(),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}

/**
 * A bound on memory, not a layout size.
 *
 * The views are under 100dp; decoding past a few hundred pixels buys nothing
 * anyone can see, at a cost a cheap phone does not have to spare.
 */
private const val DEFAULT_MAX_PX = 512

/** Smaller again: the avatar is the smallest of them. */
private const val AVATAR_MAX_PX = 256
