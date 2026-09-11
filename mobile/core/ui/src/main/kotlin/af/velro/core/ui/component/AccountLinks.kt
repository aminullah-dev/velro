package af.velro.core.ui.component

import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign

/*
 * The two doors every account screen owes, in both apps.
 *
 * Here rather than written twice because they are the same promise made
 * twice: neither store lists an app that lets somebody open an account and
 * gives them no way to close it from the same place, or that keeps what it
 * holds about them out of sight. Two copies are how one app ends up keeping
 * that promise a little differently from the other.
 */

/**
 * What VELRO keeps, on the page the server publishes.
 *
 * The browser rather than a screen of this app's own: the page is the policy,
 * and a copy compiled into an APK is a copy that falls behind it.
 */
@Composable
fun PrivacyPolicyLink(url: String, modifier: Modifier = Modifier) {
    val strings = LocalVelroStrings.current
    val context = LocalContext.current
    VelroCard(
        modifier = modifier,
        onClick = {
            // A handset with no browser at all is rare, not impossible, and a
            // tap that throws takes the whole app down with it.
            runCatching {
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
            }
        },
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                strings["account.privacy"],
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.size(Spacing.sm))
            // Tells the eye that this leaves the app. Decorative to a screen
            // reader, which already has the row's own label to read.
            Icon(
                Icons.AutoMirrored.Filled.OpenInNew,
                contentDescription = null,
                modifier = Modifier.size(Sizing.iconMd),
                tint = MaterialTheme.colorScheme.outline,
            )
        }
    }
}

/**
 * The way in to deleting the account.
 *
 * Red, so anybody looking for it finds it; a text button under sign-out, so
 * nobody mistakes it for the next thing to press. It deletes nothing by
 * itself: it opens the screen that says what goes and what stays, and that
 * screen asks again before anything is sent.
 */
@Composable
fun DeleteAccountLink(onClick: () -> Unit, modifier: Modifier = Modifier) {
    val strings = LocalVelroStrings.current
    TextButton(
        onClick = onClick,
        // A minimum, not a height: the label wraps rather than being cut off
        // at a large font size.
        modifier = modifier.fillMaxWidth().heightIn(min = Sizing.touchTarget),
        colors = ButtonDefaults.textButtonColors(
            contentColor = MaterialTheme.colorScheme.error,
        ),
    ) {
        Text(
            strings["account.delete.action"],
            style = MaterialTheme.typography.labelLarge,
            textAlign = TextAlign.Center,
        )
    }
}
