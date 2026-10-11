package af.velro.core.ui.component

import af.velro.core.ui.theme.LocalAnimationsEnabled
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Sizing
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.DragInteraction
import androidx.compose.foundation.gestures.snapping.SnapPosition
import androidx.compose.foundation.gestures.snapping.rememberSnapFlingBehavior
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.launch
import kotlin.math.abs

/**
 * A wheel: a short column of choices that snaps, with the one in the middle
 * large and green and the rest fading and shrinking away from it.
 *
 * For choosing among a handful of values by thumb -- a day, an hour -- where a
 * row of chips scrolls sideways off the screen and hides the choice already
 * made. The middle row is the answer; there is never a moment when nothing
 * looks chosen.
 *
 * Two ways in, because the wheel shape is not obvious to everyone who will
 * hold this phone: flick it and it settles on a row, or tap a row and it rolls
 * that row to the middle. Either commits through [onSelect] once, when the
 * wheel is at rest -- never on every row it passes, which would send a burst
 * of changes to the form for a single flick.
 *
 * Every row is a full touch target tall, and each is a radio button to a
 * screen reader, so the wheel is also a plain list for somebody who cannot
 * see it turn.
 *
 * @param active false while the wheel's value is not the one in force -- the
 *   departure wheels while "Now" is chosen. Drawn quieter, still usable:
 *   turning it is how somebody says "not now, then".
 */
@Composable
fun <T> WheelPicker(
    items: List<T>,
    selectedIndex: Int,
    onSelect: (Int) -> Unit,
    label: (T) -> String,
    modifier: Modifier = Modifier,
    active: Boolean = true,
) {
    val rowHeight = Sizing.touchTarget
    val rowPx = with(LocalDensity.current) { rowHeight.toPx() }
    val start = selectedIndex.coerceIn(0, (items.size - 1).coerceAtLeast(0))
    val state = rememberLazyListState(initialFirstVisibleItemIndex = start)
    val fling = rememberSnapFlingBehavior(state, SnapPosition.Center)
    val scope = rememberCoroutineScope()
    val animate = LocalAnimationsEnabled.current
    val haptics = LocalHapticFeedback.current
    val currentSelect by rememberUpdatedState(onSelect)
    val currentSelected by rememberUpdatedState(selectedIndex)
    val currentActive by rememberUpdatedState(active)

    // The row nearest the middle of the window, live as the wheel turns.
    val centred by remember(state) {
        derivedStateOf {
            val info = state.layoutInfo
            val middle = (info.viewportStartOffset + info.viewportEndOffset) / 2f
            info.visibleItemsInfo
                .minByOrNull { abs(it.offset + it.size / 2f - middle) }
                ?.index ?: currentSelected
        }
    }

    // Commit when a turn by hand comes to rest, and only then.
    //
    // By hand: the wheel also moves when the form moves it (below), and a
    // settle after that must not be read back as a choice -- at the moment
    // it lands the window can still hold the previous list's rows, and the
    // row in the middle of the old list is a different hour in the new one.
    // A drag is the one thing only a person produces.
    val turn = remember { Turn() }
    LaunchedEffect(state) {
        state.interactionSource.interactions.collect {
            if (it is DragInteraction.Start) turn.byHand = true
        }
    }
    LaunchedEffect(state) {
        snapshotFlow { state.isScrollInProgress }
            .filter { moving -> !moving }
            .collect {
                if (!turn.byHand) return@collect
                turn.byHand = false
                val settled = centred
                // A quiet wheel commits even where it already points: turning
                // it is the choice, whichever row it comes to rest on.
                if (settled in items.indices && (settled != currentSelected || !currentActive)) {
                    currentSelect(settled)
                }
            }
    }

    // A tick under the thumb as each row passes the middle, the way a real
    // wheel clicks. Only while it is moving, so a value changed by the form
    // itself does not buzz.
    LaunchedEffect(state) {
        snapshotFlow { centred }.collect {
            if (state.isScrollInProgress) haptics.performHapticFeedback(HapticFeedbackType.TextHandleMove)
        }
    }

    // The form can move the value itself -- a day change that pulls the hour
    // into range -- and the wheel follows rather than showing the old one.
    LaunchedEffect(selectedIndex, items.size) {
        if (!state.isScrollInProgress && selectedIndex in items.indices && centred != selectedIndex) {
            state.scrollToItem(selectedIndex)
        }
    }

    Box(modifier.height(rowHeight * VISIBLE_ROWS), contentAlignment = Alignment.Center) {
        // The band behind the middle row: where the answer sits.
        Box(
            Modifier
                .fillMaxWidth()
                .height(rowHeight)
                .background(
                    MaterialTheme.colorScheme.primaryContainer.copy(alpha = if (active) 0.7f else 0.35f),
                    RoundedCornerShape(Radius.pill),
                ),
        )
        LazyColumn(
            state = state,
            flingBehavior = fling,
            contentPadding = PaddingValues(vertical = rowHeight * (VISIBLE_ROWS / 2)),
            modifier = Modifier
                .fillMaxWidth()
                .height(rowHeight * VISIBLE_ROWS)
                .selectableGroup(),
        ) {
            itemsIndexed(items) { index, item ->
                val isMiddle = index == centred
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(rowHeight)
                        .graphicsLayer {
                            // Read in the layer, not in composition: the
                            // fade follows the finger frame by frame without
                            // recomposing a row.
                            val info = state.layoutInfo
                            val middle = (info.viewportStartOffset + info.viewportEndOffset) / 2f
                            val me = info.visibleItemsInfo.firstOrNull { it.index == index }
                            val rows = if (me == null) VISIBLE_ROWS / 2f
                            else abs(me.offset + me.size / 2f - middle) / rowPx
                            val t = (rows / (VISIBLE_ROWS / 2f + 0.5f)).coerceIn(0f, 1f)
                            alpha = (1f - 0.78f * t) * (if (active) 1f else 0.6f)
                            scaleX = 1f - 0.28f * t
                            scaleY = 1f - 0.28f * t
                        }
                        .selectable(
                            selected = active && index == selectedIndex,
                            role = Role.RadioButton,
                            onClick = {
                                currentSelect(index)
                                scope.launch {
                                    if (animate) state.animateScrollToItem(index)
                                    else state.scrollToItem(index)
                                }
                            },
                        ),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        label(item),
                        style = if (isMiddle) MaterialTheme.typography.titleLarge
                        else MaterialTheme.typography.titleMedium,
                        fontWeight = if (isMiddle) FontWeight.Bold else FontWeight.Normal,
                        color = if (isMiddle && active) MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                        maxLines = 1,
                    )
                }
            }
        }
    }
}

/** Whether the wheel's current movement was started by a finger. */
private class Turn { var byHand = false }

/** Two rows either side of the answer: enough to read as a wheel, no more. */
private const val VISIBLE_ROWS = 5
