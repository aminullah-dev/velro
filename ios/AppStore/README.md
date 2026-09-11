# VELRO Ride on the App Store

Everything App Store Connect shows or asks about the passenger app, kept in
git so the next version is one command and not an afternoon of forms.

| File | What it is |
|---|---|
| `listing.json` | Name, subtitle, description, keywords, URLs, category, age rating, review notes. Pushed by `ios/scripts/appstore.py`. |
| `screenshots/iphone69-*.jpg` | 1320 × 2868, the 6.9" set; App Store Connect scales it for every smaller iPhone. |
| `velro-review-demo.mp4` | Not in git (12 MB). The whole ride, recorded in the simulator, attached for App Review. |

## One command

```sh
ios/scripts/appstore.py                    # what would change; sends nothing
ios/scripts/appstore.py --apply            # text, category, age rating, price (free), countries
ios/scripts/appstore.py --apply --screenshots
ios/scripts/appstore.py --apply --build 2  # the build this version submits
ios/scripts/appstore.py --apply --review --contact-phone "+1 …"   # review notes, demo account, the video
```

It never presses "Submit for Review".

## What only a person can do in App Store Connect

1. **App Privacy** (the "nutrition label"). The API has no endpoint for it.
   Answer exactly as `VelroPassenger/Resources/PrivacyInfo.xcprivacy` says
   and as `api.velro.linumic.com/privacy` says — the three must agree:
   - Do you collect data? **Yes.** Is any of it used for tracking? **No.**
   - Contact Info → **Name**, **Phone Number**
   - Location → **Precise Location** (sent with six decimals when a ride is asked for)
   - User Content → **Customer Support** (reports), **Other User Content** (the note on a request)
   - Identifiers → **User ID**, **Device ID** (the per-install id sessions are labelled with)
   - For every one: purpose **App Functionality** only; **linked to the user**; **not** used for tracking.
   - Not collected on iOS: diagnostics, usage data, purchases, contacts, photos.
2. **App Review contact phone.** Given to `--contact-phone` once, or typed
   in App Store Connect; it is not kept in git.
3. **Submit for Review.**

## Before `--review`

The demo account is `+1 202 555 0142`: a number from the range reserved for
fiction, so no handset on earth owns it. It must be on the server's
`OTP_TEST_NUMBERS` (the code comes back in the answer and the app fills it in)
and `GEOFENCE_EXEMPT_PHONES` (App Review asks from California) **before** the
review details go up. Its requests are shown only to test drivers and never
to a real one — see `_board_scope` in `backend/ui/api/routers/negotiation.py`.

Never check that by requesting a code: if the number were not listed yet,
that request would be a real, paid SMS.

## Regenerating the screenshots and the video

```sh
cd ios && make api    # in another terminal
xcrun simctl status_bar "iPhone 17 Pro Max" override --time 9:41 --batteryState charged --batteryLevel 100
make ui-test SIM="iPhone 17 Pro Max"
xcrun xcresulttool export attachments --path build/ui-test.xcresult --output-path /tmp/shots
```

The snapshots are named after the step (`7-offer`, `17-ride-map`, …). The
video is `xcrun simctl io "iPhone 17 Pro Max" recordVideo` running while
`RideFlowTests` and `AccountFlowTests/testDeletingTheAccount` play, trimmed
past the home screen with `avconvert --start`.
