package af.velro.feature.driver

import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.compose.runtime.getValue
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.ErrorState
import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.PhotoAvatar
import af.velro.core.ui.component.StatusChip
import af.velro.core.ui.component.StatusTone
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.VelroScreen
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import af.velro.domain.DriverApprovalStatus
import af.velro.domain.DriverProfile
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign

/**
 * Who the driver is, as the product sees him.
 *
 * The app knew his name, his rating, how many journeys he had finished and
 * which car he drives, and showed him none of it in one place. His name
 * appeared once as a greeting; his rating appeared nowhere at all, although
 * every passenger who has ridden with him has been asked for one.
 *
 * That matters more here than it would elsewhere. A driver's standing is the
 * thing he is building by working, and it is what a passenger sees before
 * choosing him. A screen that collects ratings and never shows the driver his
 * own is asking him to be judged in private.
 *
 * The photograph is the selfie he already sent for approval, not a second one
 * he has to find. It was uploaded, checked by the office, and then only ever
 * looked at by the office.
 *
 * Driven on a device: the avatar decodes, the approval chip carries the amber
 * tone of a pending driver, a driver with no ratings gets the sentence rather
 * than a zero, and both cards navigate. RTL throughout.
 */
@Composable
fun ProfileRoute(
    onBack: () -> Unit,
    onOpenDocuments: () -> Unit,
    onOpenVehicle: () -> Unit,
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val profile = state.profile

    when {
        profile != null -> ProfileScreen(
            profile = profile,
            photo = state.photo,
            onBack = onBack,
            onOpenDocuments = onOpenDocuments,
            onOpenVehicle = onOpenVehicle,
        )
        state.isLoading -> LoadingState()
        // A failure is not an empty profile. Without this the screen would
        // draw a nameless person with no rating and no car, which reads as a
        // driver whose record has been wiped.
        else -> ErrorState(
            errorCode = state.errorCode ?: "INTERNAL_ERROR",
            context = state.errorContext,
            onRetry = { viewModel.onEvent(ProfileEvent.Refresh) },
        )
    }
}

@Composable
fun ProfileScreen(
    profile: DriverProfile,
    photo: ByteArray?,
    onBack: () -> Unit,
    onOpenDocuments: () -> Unit,
    onOpenVehicle: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current

    VelroScreen(
        title = strings["driver.profile.title"],
        onBack = onBack,
        modifier = modifier,
    ) {
        Spacer(Modifier.height(Spacing.lg))

        Column(
            Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            PhotoAvatar(bytes = photo, size = Sizing.profilePhoto)

            Spacer(Modifier.height(Spacing.md))

            Text(
                // A driver may not have given a name -- it is optional, and
                // some will have been registered by someone else. The screen
                // still has to be about somebody.
                profile.fullName?.takeIf { it.isNotBlank() }
                    ?: strings["common.value.unknown"],
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold,
                textAlign = TextAlign.Center,
            )

            Spacer(Modifier.height(Spacing.sm))

            StatusChip(
                statusKey = profile.approvalStatus.messageKey(),
                tone = profile.approvalStatus.tone(),
            )
        }

        Spacer(Modifier.height(Spacing.xl))

        // Two figures, two cards, the number first.
        //
        // These were label-and-value rows, which is the shape for a list of
        // details -- and a driver's rating is not a detail. It is the thing he
        // is building by working and the thing a passenger reads before
        // choosing him, so it gets the size that says so.
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            StatCard(
                value = profile.ratingAverage
                    ?.takeIf { profile.ratingCount > 0 }
                    ?.let {
                        Numerals.localise(
                            String.format(java.util.Locale.US, "%.2f", it), strings.locale,
                        )
                    },
                fallback = strings["driver.profile.no_rating"],
                label = strings["driver.profile.rating"],
                icon = Icons.Filled.Star,
                modifier = Modifier.weight(1f),
            )
            StatCard(
                value = Numerals.localise(profile.completedTrips.toString(), strings.locale),
                fallback = null,
                label = strings["driver.profile.trips"],
                icon = null,
                modifier = Modifier.weight(1f),
            )
        }

        Spacer(Modifier.height(Spacing.lg))

        // The car, and a way into it. A driver checking his own profile is
        // often doing it because something about his papers or his vehicle is
        // wrong, so the two doors he needs are on the screen rather than back
        // through home.
        VelroCard(onClick = onOpenVehicle) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Filled.DirectionsCar,
                    contentDescription = null,
                    modifier = Modifier.size(Sizing.iconMd),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.size(Spacing.md))
                Column {
                    val vehicle = profile.vehicle
                    Text(
                        vehicle?.let { "${it.brand.orEmpty()} ${it.model.orEmpty()}".trim() }
                            ?.takeIf { it.isNotBlank() }
                            ?: strings["driver.vehicle.title"],
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    if (vehicle != null) {
                        Text(
                            vehicle.plateNumber,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(Spacing.sm))

        VelroCard(onClick = onOpenDocuments) {
            Text(
                strings["driver.documents.title"],
                style = MaterialTheme.typography.bodyLarge,
            )
        }

        Spacer(Modifier.height(Spacing.xl))
    }
}

/**
 * One figure, at the size the figure deserves.
 *
 * The number leads and the label follows it, because a driver opening this
 * screen is looking for the number -- he already knows what it is called.
 *
 * A rating with no ratings behind it falls back to a sentence rather than
 * showing 0.00, which would read as a bad score rather than as no score. The
 * count is deliberately not shown beside it here: one five-star trip and forty
 * are different standings, and that distinction belongs in the passenger's
 * view of him, not in the headline of his own.
 */
@Composable
private fun StatCard(
    value: String?,
    fallback: String?,
    label: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector?,
    modifier: Modifier = Modifier,
) {
    VelroCard(modifier = modifier) {
        Column {
            if (value != null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        value,
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    if (icon != null) {
                        Spacer(Modifier.size(Spacing.xs))
                        Icon(
                            icon,
                            contentDescription = null,
                            modifier = Modifier.size(Sizing.iconMd),
                            tint = MaterialTheme.colorScheme.secondary,
                        )
                    }
                }
            } else if (fallback != null) {
                Text(
                    fallback,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.height(Spacing.xs))
            Text(
                label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun DriverApprovalStatus.messageKey(): String =
    "driver.approval." + name.lowercase()

private fun DriverApprovalStatus.tone(): StatusTone = when (this) {
    DriverApprovalStatus.APPROVED -> StatusTone.ACTIVE
    DriverApprovalStatus.PENDING -> StatusTone.ATTENTION
    DriverApprovalStatus.REJECTED, DriverApprovalStatus.SUSPENDED -> StatusTone.FAILED
}
