package af.velro.core.ui.component

import af.velro.core.ui.theme.LocalVelroDarkTheme
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * A row that goes somewhere: a soft round icon, a title, a line under it, and
 * the chevron.
 *
 * The lists in the product were a card per row -- a station, a village, a
 * booking -- each with its own border and shadow, so a list of twelve was
 * twelve boxes. This is the shape the redesign uses instead: one row, and
 * the icon in a pale circle is what gives the eye a column to run down.
 *
 * Two grounds. [contained] rows lie on the page, so each is its own white
 * rounded surface with the soft shadow; uncontained rows already sit on
 * something white -- the home sheet, the drawer -- and are drawn flat, with
 * the caller putting a hairline between them.
 *
 * The whole row is the button, read once: title and subtitle together, then
 * "button", rather than a screen reader stopping at each piece of text.
 */
@Composable
fun IconRow(
    title: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    subtitle: String? = null,
    contained: Boolean = true,
    /** Bold for the one row that is already chosen. */
    emphasised: Boolean = false,
    enabled: Boolean = true,
    /** What sits before the chevron: a fare, a status, a count. */
    trailing: (@Composable RowScope.() -> Unit)? = null,
    /** The chevron says "this row opens something". Off for a row that acts in place. */
    chevron: Boolean = true,
) {
    val body: @Composable () -> Unit = {
        Row(
            Modifier
                .fillMaxWidth()
                .heightIn(min = ROW_MIN_HEIGHT)
                .padding(horizontal = Spacing.lg, vertical = Spacing.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (icon != null) {
                IconBadge(icon)
                Spacer(Modifier.width(Spacing.md))
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Spacing.xxs)) {
                Text(
                    title,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = if (emphasised) FontWeight.Bold else FontWeight.Medium,
                )
                if (subtitle != null) {
                    Text(
                        subtitle,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (trailing != null) {
                Spacer(Modifier.width(Spacing.sm))
                trailing()
            }
            if (chevron) {
                Spacer(Modifier.width(Spacing.xs))
                ChevronForward()
            }
        }
    }

    if (contained) {
        val shape = RoundedCornerShape(Radius.surface)
        val dark = LocalVelroDarkTheme.current
        Surface(
            onClick = onClick,
            enabled = enabled,
            shape = shape,
            color = MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.onSurface,
            border = if (dark) BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant) else null,
            modifier = modifier
                .fillMaxWidth()
                .then(if (dark) Modifier else Modifier.softShadow(shape)),
        ) { body() }
    } else {
        Box(
            modifier
                .fillMaxWidth()
                .clickable(enabled = enabled, role = Role.Button, onClick = onClick),
        ) { body() }
    }
}

/**
 * The icon in its pale circle.
 *
 * The primary green on its own container: Green700 on Green50 by day and
 * Green200 on Green800 after dark, the same two pairs the "active" status
 * chip uses and ContrastTest already measures.
 */
@Composable
fun IconBadge(icon: ImageVector, modifier: Modifier = Modifier) {
    Box(
        modifier
            .size(BADGE)
            .background(MaterialTheme.colorScheme.primaryContainer, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(Sizing.iconSm + 2.dp),
        )
    }
}

private val BADGE = 40.dp
