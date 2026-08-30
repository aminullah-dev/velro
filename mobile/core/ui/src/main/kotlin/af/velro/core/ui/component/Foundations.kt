package af.velro.core.ui.component

import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

/**
 * The shared component set.
 *
 * Every one takes state and a lambda; none reaches for a ViewModel. Padding is
 * expressed with `start`/`end`, never `left`/`right`, so a screen mirrors
 * correctly in Dari and Pashto without a second layout.
 */

@Composable
fun PrimaryAction(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    icon: ImageVector? = null,
) {
    Button(
        onClick = onClick,
        modifier = modifier.fillMaxWidth().height(Sizing.buttonHeight),
        // A button mid-request is disabled, not merely spinning: a double tap
        // on a slow connection is the most common way to send a request twice.
        enabled = enabled && !loading,
        shape = RoundedCornerShape(Radius.lg),
        colors = ButtonDefaults.buttonColors(),
    ) {
        if (loading) {
            CircularProgressIndicator(
                modifier = Modifier.size(Sizing.iconSm),
                strokeWidth = 2.dp,
                color = MaterialTheme.colorScheme.onPrimary,
            )
        } else {
            if (icon != null) {
                Icon(icon, contentDescription = null, modifier = Modifier.size(Sizing.iconMd))
                androidx.compose.foundation.layout.Spacer(Modifier.size(Spacing.sm))
            }
            Text(label, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
fun SecondaryAction(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    OutlinedButton(
        onClick = onClick,
        modifier = modifier.fillMaxWidth().height(Sizing.buttonHeight),
        enabled = enabled,
        shape = RoundedCornerShape(Radius.md),
    ) {
        Text(label, style = MaterialTheme.typography.labelLarge)
    }
}

@Composable
fun VelroCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    val shape = RoundedCornerShape(Radius.card)
    val colors = CardDefaults.cardColors(
        containerColor = MaterialTheme.colorScheme.surface,
        contentColor = MaterialTheme.colorScheme.onSurface,
    )
    // One soft shadow, not a stack of them.
    //
    // This used to be a hairline border and nothing else, on the reasoning
    // that stacked elevation reads as clutter on a small screen. That is true
    // of stacked elevation; it was not true of the alternative actually
    // shipped, which was a white card on a white page separated by one pixel
    // of grey. The card now lies on a slightly darker ground and casts a
    // shadow you would not name if asked -- which is the point.
    //
    // The border stays, faintly. A shadow is invisible in bright sunlight and
    // invisible again in dark mode, and the edge of a card should not depend
    // on either.
    val border = androidx.compose.foundation.BorderStroke(
        1.dp, MaterialTheme.colorScheme.outlineVariant
    )
    val elevation = CardDefaults.cardElevation(defaultElevation = CARD_LIFT)
    if (onClick != null) {
        Card(
            onClick = onClick,
            modifier = modifier.fillMaxWidth().defaultMinSize(minHeight = Sizing.touchTarget),
            shape = shape,
            colors = colors,
            border = border,
            elevation = CardDefaults.cardElevation(
                defaultElevation = CARD_LIFT,
                pressedElevation = CARD_LIFT,
            ),
        ) { Box(Modifier.padding(Spacing.lg)) { content() } }
    } else {
        Card(
            modifier = modifier.fillMaxWidth(),
            shape = shape,
            colors = colors,
            border = border,
            elevation = elevation,
        ) {
            Box(Modifier.padding(Spacing.lg)) { content() }
        }
    }
}

/**
 * The primary action, for use inside [BrandHeader].
 *
 * Same shape and same height as [PrimaryAction] -- it is the same button, and
 * a person moving between screens should not have to notice that. Only the
 * colours invert, because the ground it sits on has: a green button on a green
 * field is a rectangle you can barely find, and tinting it darker green makes
 * the one control on the screen the least visible thing on it.
 */
@Composable
fun OnBrandAction(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    icon: ImageVector? = null,
) {
    Button(
        onClick = onClick,
        modifier = modifier.fillMaxWidth().height(Sizing.buttonHeight),
        enabled = enabled && !loading,
        shape = RoundedCornerShape(Radius.lg),
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.primary,
        ),
    ) {
        if (loading) {
            CircularProgressIndicator(
                modifier = Modifier.size(Sizing.iconSm),
                strokeWidth = 2.dp,
                color = MaterialTheme.colorScheme.primary,
            )
        } else {
            if (icon != null) {
                Icon(icon, contentDescription = null, modifier = Modifier.size(Sizing.iconMd))
                androidx.compose.foundation.layout.Spacer(Modifier.size(Spacing.sm))
            }
            Text(label, style = MaterialTheme.typography.labelLarge)
        }
    }
}

/** Barely there, and deliberately so: enough to separate, not enough to notice. */
private val CARD_LIFT = 2.dp

/**
 * The three states every screen must have.
 *
 * Section 79 and 80: no screen ends at "something went wrong", and every empty
 * list explains itself and offers the action that would fill it.
 */
@Composable
fun LoadingState(modifier: Modifier = Modifier) {
    val strings = LocalVelroStrings.current
    Column(
        modifier = modifier.fillMaxSize().padding(Spacing.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        CircularProgressIndicator()
        androidx.compose.foundation.layout.Spacer(Modifier.size(Spacing.lg))
        Text(
            strings["common.state.loading"],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
fun EmptyState(
    messageKey: String,
    modifier: Modifier = Modifier,
    actionKey: String? = null,
    onAction: (() -> Unit)? = null,
    icon: ImageVector? = null,
) {
    val strings = LocalVelroStrings.current
    Column(
        modifier = modifier.fillMaxSize().padding(Spacing.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        if (icon != null) {
            Icon(
                icon,
                contentDescription = null,
                modifier = Modifier.size(Sizing.iconLg),
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            androidx.compose.foundation.layout.Spacer(Modifier.size(Spacing.lg))
        }
        Text(
            strings[messageKey],
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        if (actionKey != null && onAction != null) {
            androidx.compose.foundation.layout.Spacer(Modifier.size(Spacing.lg))
            TextButton(onClick = onAction) { Text(strings[actionKey]) }
        }
    }
}

/**
 * A failure the person can act on.
 *
 * Takes an error *code* and its context, never a rendered sentence: the message
 * is resolved here, in the locale actually being read. A weak connection says
 * so; it does not say "something went wrong".
 */
@Composable
fun ErrorState(
    errorCode: String,
    modifier: Modifier = Modifier,
    context: Map<String, Any?> = emptyMap(),
    onRetry: (() -> Unit)? = null,
) {
    val strings = LocalVelroStrings.current
    Column(
        modifier = modifier.fillMaxSize().padding(Spacing.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            strings.forErrorCode(errorCode, context),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurface,
            textAlign = TextAlign.Center,
        )
        if (onRetry != null) {
            androidx.compose.foundation.layout.Spacer(Modifier.size(Spacing.lg))
            SecondaryAction(strings["common.action.retry"], onRetry)
        }
    }
}

/** An inline banner for a failure that does not empty the screen. */
@Composable
fun InlineError(
    errorCode: String,
    modifier: Modifier = Modifier,
    context: Map<String, Any?> = emptyMap(),
) {
    val strings = LocalVelroStrings.current
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = Spacing.sm),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            strings.forErrorCode(errorCode, context),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.error,
        )
    }
}

@Composable
fun ScreenPadding(content: @Composable () -> Unit) {
    Box(Modifier.padding(PaddingValues(horizontal = Spacing.gutter))) { content() }
}

/**
 * Ask before something that cannot be undone.
 *
 * Takes message keys rather than strings so a caller cannot slip an untranslated
 * sentence into a dialog — which is the one place people read carefully.
 */
@Composable
fun ConfirmDialog(
    titleKey: String,
    bodyKey: String,
    confirmKey: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    destructive: Boolean = false,
) {
    val strings = LocalVelroStrings.current
    androidx.compose.material3.AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(strings[titleKey]) },
        text = { Text(strings[bodyKey]) },
        confirmButton = {
            androidx.compose.material3.TextButton(onClick = onConfirm) {
                Text(
                    strings[confirmKey],
                    color = if (destructive) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.primary,
                )
            }
        },
        dismissButton = {
            androidx.compose.material3.TextButton(onClick = onDismiss) {
                Text(strings["common.action.cancel"])
            }
        },
    )
}

/**
 * A problem the client found, said in the client's own words.
 *
 * `InlineError` resolves a *server* error code through `error.<code>`. Something
 * the app decided by itself — a photograph too large to send — has no server
 * code, and forcing one would invent an error the backend never raises. This
 * takes a message key directly.
 */
@Composable
fun InlineMessage(
    messageKey: String,
    modifier: Modifier = Modifier,
    params: Map<String, Any?> = emptyMap(),
) {
    val strings = LocalVelroStrings.current
    Row(
        modifier = modifier.fillMaxWidth().padding(vertical = Spacing.sm),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            strings[messageKey, params],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.error,
        )
    }
}
