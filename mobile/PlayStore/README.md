# VELRO on Google Play

Everything Play Console shows for the two Android apps, kept in git beside
`ios/AppStore/` so the store pages change with the code that makes them true.

| File | What it is |
|---|---|
| `listing.json` | Titles, short and full descriptions, contact, category, privacy and delete-account URLs. Pasted into Play Console by hand: there is no Play API key yet. |
| `<app>/icon-512.png` | The launcher mark over the launcher background, at the iOS icon's scale. |
| `<app>/feature-1024x500.png` | Feature graphic. |
| `<app>/screenshots/*.jpg` | 1080 × 1920 (Play accepts 9:16 only). Taken on an Android 17 emulator against the local API, then cropped of the status bar and gesture handle. |

Play app ids: VELRO Ride `4973510654313421221`, VELRO Driver `4976278839836441736`.

`build/` (not in git) holds what the uploads need: the signed AABs and
`velro-driver-fgs-demo.mp4`, the foreground-service demo. Rebuild the AABs
with `VELRO_KEYSTORE=… ./gradlew :app-passenger:bundleRelease
:app-driver:bundleRelease -Pvelro.apiUrl=https://api.velro.linumic.com/api/v1/`.

## Declarations (App content), passenger

Same facts as the App Store label and `api.velro.linumic.com/privacy`:

- Data collected, none shared; all encrypted in transit; users can delete
  their account (in the app, or by email — `privacy#delete-en`).
- Name (optional), phone number, user ID, device ID: app functionality and
  account management. Crash logs (both Android apps post them to
  `/telemetry/crash`: version, device model, stack trace): required,
  analytics. Precise location: app functionality (the service-area
  check on a ride request). Other user-generated content (notes, reports):
  optional, app functionality.
- No ads, no advertising ID, not a government, financial or health app.
  Target audience 18+. IARC: users can interact (notes) and report, no
  location shared with other users → Everyone / 3+.
- Sign-in details: `+12025550142`, no password — the code fills in by itself
  for this number, which is on the server's `OTP_TEST_NUMBERS` and
  `GEOFENCE_EXEMPT_PHONES`. Google's partner-device testing with these
  credentials is off: it would act on production.
- Automatic protection (Play's installer check) is off: the same app is also
  installed from api.velro.linumic.com/app and passed between phones.

The driver app differs where it must: its location **is** shared with the
passengers it is driving (IARC "shares location"), it collects photos
(documents, selfie — images only, the Android picker offers no PDFs, fraud
prevention as well as app functionality), other financial info (earnings,
commission, settlements), and location is optional (only on duty). Its
sign-in details say `+12025550142` is an **approved test driver**: make that
true on production before sending the driver app for review.

### Foreground-service declaration (driver, appears after the first AAB)

`DriverDutyService`, types `location|specialUse`, runs only while the driver
is online or carrying a trip, under a persistent notification, and stops
when he goes offline or signs out. Paste:

> VELRO Driver is used by drivers of intercity shared taxis between Kabul,
> Parwan and Ghorband. When a driver turns the "Online" switch on, a
> foreground service keeps running with a visible notification until they go
> offline or sign out. **Location:** during a trip it sends the driver's
> position every 30 seconds so the passengers being driven can see the car
> on their map, and it checks that position against known dangerous road
> stretches to warn the driver on mountain roads — both must continue while
> the phone is in the driver's pocket. **Special use:** while online and
> waiting, it checks for new ride requests and dispatcher offers and alerts
> the driver with a notification and vibration; the app uses no push-message
> service, so it has to listen itself. Turning
> the switch off stops the service and the notification immediately.

Video: `build/velro-driver-fgs-demo.mp4` (43 s: offline → online, the "on
duty" notification appears, the ride board, offline again, the notification
is gone). Play wants a link: upload it to YouTube as *unlisted*.

## Not done by a script

1. **App signing.** Play must sign with the existing key (cert
   `33:23:D0:63…90:AC`) or Play updates will not install over the APKs
   people already have. Play Console → Test and release → App integrity →
   App signing → *Use a different key* → *Export and upload a key from Java
   keystore* → download `pepk.jar` and the encryption key, then run the
   command it shows against
   `~/Library/Mobile Documents/com~apple~CloudDocs/importand/velro-release.jks`,
   alias `velro`, and upload the zip. Do this **before** the first AAB: the
   first upload fixes the signing key for good.
   Both apps, one PEPK zip each.
2. **Testers**, then a closed-testing release with the AAB, then 14 days
   with 12 opted-in testers before production can be requested.
   Closed-testing countries are set to all 177 Play offers; Afghanistan is
   not in Play's list, so testers inside Afghanistan may not get the app from
   Play at all; the APK link stays their way in.
