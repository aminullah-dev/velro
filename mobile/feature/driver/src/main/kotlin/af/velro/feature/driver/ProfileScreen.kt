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

        VelroCard {
            Column {
                Rating(profile)
                Spacer(Modifier.height(Spacing.md))
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                Spacer(Modifier.height(Spacing.md))
                Figure(
                    label = strings["driver.profile.trips"],
                    value = Numerals.localise(profile.completedTrips.toString(), strings.locale),
                )
            }
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
 * The rating, and what it is out of.
 *
 * The count is shown beside the average because one five-star trip and forty
 * of them are not the same standing, and a bare "5.0" on a driver's first week
 * would be flattering him with a number that means nothing yet.
 */
@Composable
private fun Rating(profile: DriverProfile) {
    val strings = LocalVelroStrings.current
    val average = profile.ratingAverage

    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            strings["driver.profile.rating"],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (average == null || profile.ratingCount == 0) {
            Text(
                strings["driver.profile.no_rating"],
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Filled.Star,
                    contentDescription = null,
                    modifier = Modifier.size(Sizing.iconSm),
                    tint = MaterialTheme.colorScheme.secondary,
                )
                Spacer(Modifier.size(Spacing.xs))
                Text(
                    Numerals.localise(
                        String.format(java.util.Locale.US, "%.1f", average),
                        strings.locale,
                    ),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.size(Spacing.xs))
                Text(
                    "(" + Numerals.localise(
                        profile.ratingCount.toString(), strings.locale,
                    ) + ")",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun Figure(label: String, value: String) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            value,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

private fun DriverApprovalStatus.messageKey(): String =
    "driver.approval." + name.lowercase()

private fun DriverApprovalStatus.tone(): StatusTone = when (this) {
    DriverApprovalStatus.APPROVED -> StatusTone.ACTIVE
    DriverApprovalStatus.PENDING -> StatusTone.ATTENTION
    DriverApprovalStatus.REJECTED, DriverApprovalStatus.SUSPENDED -> StatusTone.FAILED
}
