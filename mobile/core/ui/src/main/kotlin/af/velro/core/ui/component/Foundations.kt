package af.velro.core.ui.component

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import af.velro.core.ui.theme.Elevation
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.LocalVelroDarkTheme
import af.velro.core.ui.theme.VelroColors
import af.velro.core.ui.theme.Spacing
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
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
    /**
     * The corner radius.
     *
     * A pill, now that the whole product has committed to it: sign-in tried
     * the shape first, side by side with the old 16dp corner, and the soft
     * redesign made it the default. The parameter stays for the rare control
     * that has to sit flush with a squarer neighbour.
     */
    radius: Dp = Radius.pill,
) {
    val shape = RoundedCornerShape(radius)
    Button(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .height(Sizing.buttonHeight)
            // A faint glow in the button's own green, under it. Only while it
            // can be pressed: a disabled button that still floats reads as
            // one that is merely slow to respond.
            .then(
                if (enabled) Modifier.softShadow(
                    shape,
                    Elevation.button,
                    color = MaterialTheme.colorScheme.primary,
                    strength = SHADOW_BUTTON,
                ) else Modifier,
            ),
        // A button mid-request is disabled, not merely spinning: a double tap
        // on a slow connection is the most common way to send a request twice.
        enabled = enabled && !loading,
        shape = shape,
        // The shadow above is the lift; Material's own would stack a grey
        // one under the green.
        elevation = flat(),
        // Disabled, but still there.
        //
        // Material's default is onSurface at 38% over onSurface at 12%: a
        // 2.31:1 label on a container 1.23:1 from the page. In a room that is
        // a greyed button; in Ghorband sunlight it is nothing at all, and a
        // person who cannot see the button cannot tell whether the app is
        // broken or their own form is unfinished. Quieter than a live button,
        // never absent.
        colors = ButtonDefaults.buttonColors(
            disabledContainerColor = MaterialTheme.colorScheme.surfaceVariant,
            disabledContentColor = disabledLabel(),
        ),
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

/**
 * The one button on a screen that cannot be taken back.
 *
 * The same shape as [PrimaryAction], so it reads as an action rather than a
 * warning label, and in the error colour, so nobody presses it expecting the
 * green one. For the foot of a screen that has already said what happens --
 * never a screen's first control.
 *
 * Two departures from its sibling, both about who is reading it. It grows
 * rather than clips: a fixed height holds for "Send code" and does not hold
 * for every sentence in Pashto at a large font size. And busy is not
 * unavailable: while the request runs it keeps its colour, spins in the
 * colour of its own label, and still tells a screen reader what it is and
 * that it is working -- a spinner on its own announces nothing at all.
 */
@Composable
fun DestructiveAction(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
) {
    val strings = LocalVelroStrings.current
    val working = strings["common.state.loading"]
    val colours = MaterialTheme.colorScheme
    Button(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = Sizing.buttonHeight)
            .semantics {
                if (loading) {
                    contentDescription = label
                    stateDescription = working
                }
            },
        enabled = enabled && !loading,
        // The same pill as every other button: it is an action, and the error
        // colour is what says it cannot be taken back.
        shape = RoundedCornerShape(Radius.pill),
        colors = ButtonDefaults.buttonColors(
            containerColor = colours.error,
            contentColor = colours.onError,
            disabledContainerColor = if (loading) colours.error else colours.surfaceVariant,
            disabledContentColor = if (loading) colours.onError else disabledLabel(),
        ),
    ) {
        if (loading) {
            CircularProgressIndicator(
                modifier = Modifier.size(Sizing.iconSm),
                strokeWidth = 2.dp,
                color = LocalContentColor.current,
            )
        } else {
            Text(
                label,
                style = MaterialTheme.typography.labelLarge,
                textAlign = TextAlign.Center,
            )
        }
    }
}

/**
 * The second choice on a screen: a white pill with a green label.
 *
 * It used to be an outlined button. The soft redesign takes the line off in
 * light mode and lets a faint shadow lift the pill off the page instead --
 * what identifies it as a button is its label, in the brand green at 7.58:1,
 * and the line was the hard edge the owner asked to lose. After dark a shadow
 * shows nothing, so there the edge comes back, at the 3:1 a control boundary
 * owes.
 *
 * Disabled, it keeps a container and a measured label rather than vanishing,
 * for the same reason the primary does.
 */
@Composable
fun SecondaryAction(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    val shape = RoundedCornerShape(Radius.pill)
    val dark = LocalVelroDarkTheme.current
    Button(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .height(Sizing.buttonHeight)
            .then(if (enabled && !dark) Modifier.softShadow(shape) else Modifier),
        enabled = enabled,
        shape = shape,
        elevation = flat(),
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.primary,
            disabledContainerColor = MaterialTheme.colorScheme.surfaceVariant,
            disabledContentColor = disabledLabel(),
        ),
        border = if (dark) {
            androidx.compose.foundation.BorderStroke(
                1.dp,
                if (enabled) MaterialTheme.colorScheme.outline
                else MaterialTheme.colorScheme.outlineVariant,
            )
        } else null,
    ) {
        Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
    }
}

/** No Material elevation: every lift in the product is a [softShadow]. */
@Composable
private fun flat() = ButtonDefaults.buttonElevation(
    defaultElevation = 0.dp,
    pressedElevation = 0.dp,
    focusedElevation = 0.dp,
    hoveredElevation = 0.dp,
    disabledElevation = 0.dp,
)

/**
 * The label colour of a control that is present but cannot be used.
 *
 * One place, because both button shapes need it and because the number is
 * measured: 4.70:1 in light and 4.82:1 in dark, against Material's own 2.31:1.
 */
@Composable
private fun disabledLabel(): Color =
    if (LocalVelroDarkTheme.current) VelroColors.Neutral350
    else VelroColors.Neutral550

@Composable
fun VelroCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    val shape = RoundedCornerShape(Radius.surface)
    val colors = CardDefaults.cardColors(
        containerColor = MaterialTheme.colorScheme.surface,
        contentColor = MaterialTheme.colorScheme.onSurface,
    )
    val dark = LocalVelroDarkTheme.current
    // One soft shadow, not a stack of them, and no line in light mode.
    //
    // This was a hairline border with a 2dp Material shadow under it. The
    // redesign ("soft, glassy, almost minimal") takes the line away: the card
    // is white on the Neutral50 page and a wide, faint shadow says where it
    // ends. What is read on a card is its content, and every control inside
    // it still carries its own measured edge.
    //
    // After dark the hairline stays. A shadow shows nothing on a black page,
    // and there the card's own lightness and that one line are all that lift
    // it off the ground.
    val border = if (dark) {
        androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)
    } else null
    val lift = if (dark) Modifier else Modifier.softShadow(shape)
    val none = CardDefaults.cardElevation(
        defaultElevation = 0.dp,
        pressedElevation = 0.dp,
    )
    if (onClick != null) {
        Card(
            onClick = onClick,
            modifier = modifier
                .fillMaxWidth()
                .defaultMinSize(minHeight = Sizing.touchTarget)
                .then(lift),
            shape = shape,
            colors = colors,
            border = border,
            elevation = none,
        ) { Box(Modifier.padding(Spacing.lg)) { content() } }
    } else {
        Card(
            modifier = modifier.fillMaxWidth().then(lift),
            shape = shape,
            colors = colors,
            border = border,
            elevation = none,
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
        shape = RoundedCornerShape(Radius.pill),
        elevation = flat(),
        // Constant with the field it sits on. Taken from the scheme these
        // became a near-black button carrying mint text on a mint header
        // after dark -- three brand colours in one control, none of them the
        // brand.
        colors = ButtonDefaults.buttonColors(
            containerColor = VelroColors.OnBrandField,
            contentColor = VelroColors.BrandField,
        ),
    ) {
        if (loading) {
            CircularProgressIndicator(
                modifier = Modifier.size(Sizing.iconSm),
                strokeWidth = 2.dp,
                color = VelroColors.BrandField,
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

/**
 * A text field: a white pill with its label above it.
 *
 * The label moved out of the outline. A floating label notches the border,
 * and on a fully round field that notch lands on the curve and reads as a
 * break in it. Above the field it is also simply bigger and always there --
 * a Material label shrinks into the border the moment somebody starts to
 * type, which is the moment a person unsure of the form looks for it.
 *
 * The edge stays, at `outline`'s 3:1. The redesign took lines off cards and
 * buttons, whose labels say what they are; a field is an empty box until it is
 * filled, and somebody who cannot see where the phone field is in Ghorband
 * sunlight cannot sign in. The soft shadow is added to it, not swapped for it.
 *
 * The label is ordinary text directly before the field, so a screen reader
 * reaches it on the way into the box. It is not also set as the field's
 * description: on an editable node that replaces the typed value in what
 * TalkBack reads back, and somebody checking their own number by ear needs
 * the number.
 *
 * @param leftToRight a phone number or a code: a sequence to be dialled or
 *   compared, laid out left to right in any language. The label above it
 *   stays where the screen's own direction puts it.
 */
@Composable
fun PillField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String?,
    modifier: Modifier = Modifier,
    placeholder: String? = null,
    leadingIcon: ImageVector? = null,
    suffix: String? = null,
    supportingText: String? = null,
    isError: Boolean = false,
    singleLine: Boolean = true,
    textStyle: TextStyle = MaterialTheme.typography.bodyLarge,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
    leftToRight: Boolean = false,
    fieldModifier: Modifier = Modifier,
) {
    // A pill only holds one line. A note that wraps gets a card's corner, so
    // its second line does not run into the curve.
    val shape = RoundedCornerShape(if (singleLine) Radius.pill else Radius.surface)
    val colours = MaterialTheme.colorScheme
    Column(modifier.fillMaxWidth()) {
        if (label != null) {
            Text(
                label,
                style = MaterialTheme.typography.labelLarge,
                color = colours.onSurfaceVariant,
                modifier = Modifier.padding(start = Spacing.lg, end = Spacing.lg, bottom = Spacing.xs),
            )
        }
        val field: @Composable () -> Unit = {
            OutlinedTextField(
                value = value,
                onValueChange = onValueChange,
                modifier = fieldModifier
                    .fillMaxWidth()
                    .heightIn(min = Sizing.fieldHeight)
                    .softShadow(shape),
                textStyle = textStyle,
                // Muted, not the label's tone: with the label outside the box
                // the hint is always showing, and at full strength "0700 123
                // 456" read as a number already typed in. Neutral500 still
                // clears 4.5:1 on white -- ContrastTest's "muted on white".
                placeholder = placeholder?.let {
                    {
                        Text(
                            it,
                            style = textStyle,
                            color = if (LocalVelroDarkTheme.current) VelroColors.Neutral350
                            else VelroColors.Neutral500,
                        )
                    }
                },
                leadingIcon = leadingIcon?.let {
                    { Icon(it, contentDescription = null, modifier = Modifier.size(Sizing.iconMd)) }
                },
                suffix = suffix?.let { { Text(it) } },
                isError = isError,
                keyboardOptions = keyboardOptions,
                keyboardActions = keyboardActions,
                singleLine = singleLine,
                minLines = if (singleLine) 1 else 3,
                shape = shape,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = colours.surface,
                    unfocusedContainerColor = colours.surface,
                    errorContainerColor = colours.surface,
                    focusedBorderColor = colours.primary,
                    unfocusedBorderColor = colours.outline,
                    focusedLeadingIconColor = colours.primary,
                    unfocusedLeadingIconColor = colours.onSurfaceVariant,
                ),
            )
        }
        if (leftToRight) {
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) { field() }
        } else {
            field()
        }
        if (supportingText != null) {
            Text(
                supportingText,
                style = MaterialTheme.typography.bodySmall,
                color = if (isError) colours.error else colours.onSurfaceVariant,
                modifier = Modifier.padding(start = Spacing.lg, end = Spacing.lg, top = Spacing.xs),
            )
        }
    }
}

/**
 * One choice among a few: a day, a seat count, a language.
 *
 * A pill like every other control. Selected is filled with the brand colour
 * rather than Material's secondary container -- which is the amber accent in
 * this palette, and the tokens allow one accent per screen. Selected and not
 * also differ in shape, filled against outlined, so the state never rests on
 * colour alone.
 */
@Composable
fun ChoiceChip(
    selected: Boolean,
    onClick: () -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    val colours = MaterialTheme.colorScheme
    FilterChip(
        selected = selected,
        onClick = onClick,
        label = {
            Text(
                label,
                style = MaterialTheme.typography.labelLarge,
                fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                maxLines = 1,
            )
        },
        modifier = modifier,
        enabled = enabled,
        shape = RoundedCornerShape(Radius.pill),
        colors = FilterChipDefaults.filterChipColors(
            containerColor = colours.surface,
            labelColor = colours.onSurface,
            selectedContainerColor = colours.primary,
            selectedLabelColor = colours.onPrimary,
        ),
        border = FilterChipDefaults.filterChipBorder(
            enabled = enabled,
            selected = selected,
            borderColor = colours.outline,
            selectedBorderColor = colours.primary,
        ),
    )
}

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

/**
 * The "this row goes somewhere" mark.
 *
 * A card carrying a village name and nothing else does not look like a
 * control. It is one -- tapping it is the whole of the booking flow -- but the
 * only thing saying so was the ripple, which a person sees after they have
 * already guessed right. Three steps of the flow were lists of that card.
 *
 * AutoMirrored: the chevron points left in Dari and Pashto. A forward arrow
 * pointing back into the text is worse than no arrow, because it is a
 * statement rather than an absence.
 */
@Composable
fun ChevronForward(modifier: Modifier = Modifier) {
    Icon(
        Icons.AutoMirrored.Filled.KeyboardArrowRight,
        // Decorative: the row's own label already says where it goes, and a
        // screen reader announcing "chevron" after every village is noise.
        contentDescription = null,
        modifier = modifier.size(Sizing.iconMd),
        tint = MaterialTheme.colorScheme.outline,
    )
}
