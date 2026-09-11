#!/usr/bin/env python3
"""Push ios/AppStore/listing.json to App Store Connect.

  ios/scripts/appstore.py              show what would change, change nothing
  ios/scripts/appstore.py --app driver ...the same for VELRO Driver
                                       (ios/AppStore/driver/listing.json)
  ios/scripts/appstore.py --apply      text, category, age rating, rights
  ios/scripts/appstore.py --apply --screenshots   ...and replace the screenshots
  ios/scripts/appstore.py --apply --review --contact-phone "+1 555 ..."
                                                  ...and the App Review details
  ios/scripts/appstore.py --apply --build 2       ...and pick the build to submit

It never submits for review: that button stays a person's. It reads the same
git-ignored scripts/.env as upload.sh (ASC_ISSUER_ID, ASC_KEY_ID, ASC_KEY_PATH)
and never prints the key. Standard library plus the openssl on every Mac, so
it runs without the backend's virtualenv.

--review is for after the review number in listing.json is on the server's
OTP_TEST_NUMBERS and GEOFENCE_EXEMPT_PHONES: App Review signing in to a number
whose code went to nobody is a rejection under 2.1, and a slow one. Nothing
here checks that by asking the server for a code -- if the number were not
listed yet, that question would be a real, paid SMS.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPS = {
    "passenger": ("VELRO Ride", "af.velro.passenger", HERE.parent / "AppStore" / "listing.json"),
    "driver": ("VELRO Driver", "af.velro.driver", HERE.parent / "AppStore" / "driver" / "listing.json"),
}
NAME, BUNDLE_ID, LISTING = APPS["passenger"]
ENV = HERE / ".env"
API = "https://api.appstoreconnect.apple.com"
EDITABLE = {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED", "INVALID_BINARY"}


# -- auth -----------------------------------------------------------------

def _env() -> dict[str, str]:
    out = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip("\"'")
    return out


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _der_to_raw(der: bytes) -> bytes:
    """openssl signs ECDSA as DER; a JWT wants r||s, 32 bytes each."""
    assert der[0] == 0x30
    i = 2 if der[1] < 0x80 else 2 + (der[1] & 0x7F)
    parts = []
    for _ in range(2):
        assert der[i] == 0x02
        length = der[i + 1]
        parts.append(der[i + 2 : i + 2 + length].lstrip(b"\x00").rjust(32, b"\x00"))
        i += 2 + length
    return b"".join(parts)


_token: tuple[float, str] | None = None


def token() -> str:
    global _token
    if _token and _token[0] > time.time() + 60:
        return _token[1]
    env = _env()
    key_path = Path(env["ASC_KEY_PATH"]).expanduser()
    now = int(time.time())
    header = _b64(json.dumps({"alg": "ES256", "kid": env["ASC_KEY_ID"], "typ": "JWT"}).encode())
    claims = _b64(json.dumps({
        "iss": env["ASC_ISSUER_ID"], "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1",
    }).encode())
    signing_input = f"{header}.{claims}".encode()
    der = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
        input=signing_input, capture_output=True, check=True,
    ).stdout
    _token = (now + 1200, f"{header}.{claims}.{_b64(_der_to_raw(der))}")
    return _token[1]


def call(method: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        path if path.startswith("http") else API + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
    )
    request.add_header("Authorization", "Bearer " + token())
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")
        raise SystemExit(f"✗ {method} {path}: HTTP {err.code}\n{detail}") from None


# -- what is there --------------------------------------------------------

def find_state() -> dict:
    found = call("GET", f"/v1/apps?filter[bundleId]={BUNDLE_ID}")["data"]
    if not found:
        raise SystemExit(f"✗ no App Store Connect record for {BUNDLE_ID} yet: create it (My Apps → +) first")
    app = found[0]
    versions = call("GET", f"/v1/apps/{app['id']}/appStoreVersions?filter[platform]=IOS")["data"]
    editable = [v for v in versions if v["attributes"]["appStoreState"] in EDITABLE]
    if not editable:
        raise SystemExit("✗ no App Store version is open for editing")
    infos = call("GET", f"/v1/apps/{app['id']}/appInfos")["data"]
    info = next(i for i in infos if i["attributes"]["appStoreState"] in EDITABLE | {"PREPARE_FOR_SUBMISSION"})
    return {"app": app, "version": editable[0], "info": info}


def plan(state: dict, listing: dict) -> list[tuple[str, str, dict]]:
    """(label, path, body) for every PATCH that would change something."""
    out = []
    app, version, info = state["app"], state["version"], state["info"]

    wanted = {"versionString": listing["version"], "copyright": listing["copyright"]}
    have = version["attributes"]
    delta = {k: v for k, v in wanted.items() if have.get(k) != v}
    if delta:
        out.append(("version", f"/v1/appStoreVersions/{version['id']}",
                    {"data": {"type": "appStoreVersions", "id": version["id"], "attributes": delta}}))

    if app["attributes"].get("contentRightsDeclaration") != listing["content_rights"]:
        out.append(("content rights", f"/v1/apps/{app['id']}",
                    {"data": {"type": "apps", "id": app["id"],
                              "attributes": {"contentRightsDeclaration": listing["content_rights"]}}}))

    category = call("GET", f"/v1/appInfos/{info['id']}/relationships/primaryCategory").get("data")
    if (category or {}).get("id") != listing["primary_category"]:
        out.append(("category", f"/v1/appInfos/{info['id']}",
                    {"data": {"type": "appInfos", "id": info["id"], "relationships": {
                        "primaryCategory": {"data": {"type": "appCategories", "id": listing["primary_category"]}}}}}))

    for locale, text in listing["localizations"].items():
        info_loc = next(
            loc for loc in call("GET", f"/v1/appInfos/{info['id']}/appInfoLocalizations")["data"]
            if loc["attributes"]["locale"] == locale
        )
        wanted = {"subtitle": text["subtitle"], "privacyPolicyUrl": text["privacy_policy_url"]}
        delta = {k: v for k, v in wanted.items() if info_loc["attributes"].get(k) != v}
        if delta:
            out.append((f"{locale} name/subtitle/privacy", f"/v1/appInfoLocalizations/{info_loc['id']}",
                        {"data": {"type": "appInfoLocalizations", "id": info_loc["id"], "attributes": delta}}))

        version_loc = next(
            loc for loc in call("GET", f"/v1/appStoreVersions/{version['id']}/appStoreVersionLocalizations")["data"]
            if loc["attributes"]["locale"] == locale
        )
        wanted = {
            "description": text["description"], "keywords": text["keywords"],
            "promotionalText": text["promotional_text"],
            "supportUrl": text["support_url"], "marketingUrl": text["marketing_url"],
        }
        delta = {k: v for k, v in wanted.items() if version_loc["attributes"].get(k) != v}
        if delta:
            out.append((f"{locale} description/keywords/urls", f"/v1/appStoreVersionLocalizations/{version_loc['id']}",
                        {"data": {"type": "appStoreVersionLocalizations", "id": version_loc["id"], "attributes": delta}}))

    rating = call("GET", f"/v1/appInfos/{info['id']}/ageRatingDeclaration")["data"]
    delta = {k: v for k, v in listing["age_rating"].items() if rating["attributes"].get(k) != v}
    if delta:
        out.append(("age rating", f"/v1/ageRatingDeclarations/{rating['id']}",
                    {"data": {"type": "ageRatingDeclarations", "id": rating["id"], "attributes": delta}}))
    return out


def check_limits(listing: dict) -> None:
    """App Store Connect's own limits, checked before it refuses them."""
    for locale, text in listing["localizations"].items():
        for field, limit in (("subtitle", 30), ("keywords", 100), ("promotional_text", 170), ("description", 4000)):
            size = len(text[field].encode()) if field == "keywords" else len(text[field])
            if size > limit:
                raise SystemExit(f"✗ {locale} {field} is {size}, the limit is {limit}")


# -- screenshots ------------------------------------------------------------

def replace_screenshots(version_loc_id: str, display_type: str, files: list[Path]) -> None:
    sets = call("GET", f"/v1/appStoreVersionLocalizations/{version_loc_id}/appScreenshotSets")["data"]
    target = next((s for s in sets if s["attributes"]["screenshotDisplayType"] == display_type), None)
    if target is None:
        target = call("POST", "/v1/appScreenshotSets", {"data": {
            "type": "appScreenshotSets", "attributes": {"screenshotDisplayType": display_type},
            "relationships": {"appStoreVersionLocalization": {
                "data": {"type": "appStoreVersionLocalizations", "id": version_loc_id}}}}})["data"]
    for old in call("GET", f"/v1/appScreenshotSets/{target['id']}/appScreenshots")["data"]:
        call("DELETE", f"/v1/appScreenshots/{old['id']}")
    for path in files:
        content = path.read_bytes()
        reserved = call("POST", "/v1/appScreenshots", {"data": {
            "type": "appScreenshots",
            "attributes": {"fileName": path.name, "fileSize": len(content)},
            "relationships": {"appScreenshotSet": {"data": {"type": "appScreenshotSets", "id": target["id"]}}}}})["data"]
        for op in reserved["attributes"]["uploadOperations"]:
            chunk = content[op["offset"] : op["offset"] + op["length"]]
            put = urllib.request.Request(op["url"], data=chunk, method=op["method"])
            for header in op.get("requestHeaders", []):
                put.add_header(header["name"], header["value"])
            urllib.request.urlopen(put).read()
        call("PATCH", f"/v1/appScreenshots/{reserved['id']}", {"data": {
            "type": "appScreenshots", "id": reserved["id"],
            "attributes": {"uploaded": True, "sourceFileChecksum": hashlib.md5(content).hexdigest()}}})
        print(f"  ↑ {path.name}")


# -- price, countries, build ---------------------------------------------------

def ensure_free(app_id: str) -> None:
    """Free, everywhere Apple sells, once: a fare is paid to the driver in
    cash, and never through the App Store."""
    # The schedule answers for every app, priced or not; only its prices
    # say whether one was ever chosen.
    if call("GET", f"/v1/appPriceSchedules/{app_id}/manualPrices")["data"]:
        print("  · price already set")
    else:
        points = call("GET", f"/v1/apps/{app_id}/appPricePoints?filter[territory]=USA&limit=200")["data"]
        free = next(p for p in points if float(p["attributes"]["customerPrice"]) == 0)
        call("POST", "/v1/appPriceSchedules", {
            "data": {"type": "appPriceSchedules", "relationships": {
                "app": {"data": {"type": "apps", "id": app_id}},
                "baseTerritory": {"data": {"type": "territories", "id": "USA"}},
                "manualPrices": {"data": [{"type": "appPrices", "id": "${free}"}]}}},
            "included": [{"type": "appPrices", "id": "${free}", "attributes": {"startDate": None},
                          "relationships": {"appPricePoint": {"data": {"type": "appPricePoints", "id": free["id"]}}}}],
        })
        print("  ✓ price: free")


def ensure_available_everywhere(app_id: str) -> None:
    """Every storefront, not only Afghanistan's: a great many iPhones in
    Kabul are signed in to an Apple ID from somewhere else, and an app
    missing from that store is an app they cannot install."""
    try:
        call("GET", f"/v1/apps/{app_id}/appAvailabilityV2")
        print("  · countries already set")
        return
    except SystemExit:
        pass
    territories = [t["id"] for t in call("GET", "/v1/territories?limit=200")["data"]]
    call("POST", "/v2/appAvailabilities", {
        "data": {"type": "appAvailabilities", "attributes": {"availableInNewTerritories": True},
                 "relationships": {
                     "app": {"data": {"type": "apps", "id": app_id}},
                     "territoryAvailabilities": {"data": [
                         {"type": "territoryAvailabilities", "id": f"${{{t}}}"} for t in territories]}}},
        "included": [
            {"type": "territoryAvailabilities", "id": f"${{{t}}}", "attributes": {"available": True},
             "relationships": {"territory": {"data": {"type": "territories", "id": t}}}}
            for t in territories
        ],
    })
    print(f"  ✓ available in {len(territories)} countries and regions")


def attach_build(app_id: str, version_id: str, number: str) -> None:
    builds = call("GET", f"/v1/builds?filter[app]={app_id}&filter[version]={number}")["data"]
    if not builds:
        raise SystemExit(f"✗ no build {number} on App Store Connect")
    state = builds[0]["attributes"]["processingState"]
    if state != "VALID":
        raise SystemExit(f"✗ build {number} is {state}, not VALID yet")
    call("PATCH", f"/v1/appStoreVersions/{version_id}/relationships/build",
         {"data": {"type": "builds", "id": builds[0]["id"]}})
    print(f"  ✓ build {number} is the one to submit")


# -- App Review ----------------------------------------------------------------

def push_review(version_id: str, review: dict, attachment: Path | None, contact_phone: str | None) -> None:
    attributes = {
        "contactFirstName": review["contact_first_name"],
        "contactLastName": review["contact_last_name"],
        "contactEmail": review["contact_email"],
        "demoAccountRequired": True,
        "demoAccountName": review["demo_account_name"],
        "demoAccountPassword": review["demo_account_password"],
        "notes": review["notes"],
    }
    # Given on the command line and never written down: the owner's phone
    # does not belong in git. App Store Connect refuses a new review detail
    # without one, and keeps the one it has when this is omitted later.
    if contact_phone:
        attributes["contactPhone"] = contact_phone
    existing = call("GET", f"/v1/appStoreVersions/{version_id}/appStoreReviewDetail").get("data")
    if not existing and not contact_phone:
        raise SystemExit("✗ the first --review needs --contact-phone \"+<country code> <number>\"")
    if existing:
        detail = call("PATCH", f"/v1/appStoreReviewDetails/{existing['id']}", {"data": {
            "type": "appStoreReviewDetails", "id": existing["id"], "attributes": attributes}})["data"]
    else:
        detail = call("POST", "/v1/appStoreReviewDetails", {"data": {
            "type": "appStoreReviewDetails", "attributes": attributes,
            "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": version_id}}}}})["data"]
    print("  ✓ review notes and demo account")
    if attachment is None:
        return
    for old in call("GET", f"/v1/appStoreReviewDetails/{detail['id']}/appStoreReviewAttachments")["data"]:
        call("DELETE", f"/v1/appStoreReviewAttachments/{old['id']}")
    content = attachment.read_bytes()
    reserved = call("POST", "/v1/appStoreReviewAttachments", {"data": {
        "type": "appStoreReviewAttachments",
        "attributes": {"fileName": attachment.name, "fileSize": len(content)},
        "relationships": {"appStoreReviewDetail": {"data": {"type": "appStoreReviewDetails", "id": detail["id"]}}}}})["data"]
    for op in reserved["attributes"]["uploadOperations"]:
        put = urllib.request.Request(op["url"], data=content[op["offset"] : op["offset"] + op["length"]], method=op["method"])
        for header in op.get("requestHeaders", []):
            put.add_header(header["name"], header["value"])
        urllib.request.urlopen(put).read()
    call("PATCH", f"/v1/appStoreReviewAttachments/{reserved['id']}", {"data": {
        "type": "appStoreReviewAttachments", "id": reserved["id"],
        "attributes": {"uploaded": True, "sourceFileChecksum": hashlib.md5(content).hexdigest()}}})
    print(f"  ↑ {attachment.name} for the reviewer")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", choices=sorted(APPS), default="passenger", help="which app (default: passenger)")
    parser.add_argument("--apply", action="store_true", help="make the changes (default: show them)")
    parser.add_argument("--screenshots", action="store_true", help="replace the screenshots too")
    parser.add_argument("--review", action="store_true", help="push App Review details too")
    parser.add_argument("--attachment", type=Path, help="video for the reviewer (default: listing's name, next to it)")
    parser.add_argument("--build", help="the build number to submit with this version")
    parser.add_argument("--contact-phone", help="App Review's number for you, with + and country code (not stored)")
    args = parser.parse_args()
    global NAME, BUNDLE_ID, LISTING
    NAME, BUNDLE_ID, LISTING = APPS[args.app]

    listing = json.loads(LISTING.read_text())
    check_limits(listing)
    state = find_state()
    changes = plan(state, listing)
    print(f"▸ {NAME} {state['version']['attributes']['versionString']} "
          f"({state['version']['attributes']['appStoreState']})")
    for label, _, body in changes:
        attributes = body["data"].get("attributes") or body["data"].get("relationships")
        print(f"  • {label}: {', '.join(attributes)}")
    if not changes:
        print("  nothing to change in the text")
    if not args.apply:
        print("dry run: nothing sent. Add --apply to send it.")
        return

    for label, path, body in changes:
        call("PATCH", path, body)
        print(f"  ✓ {label}")
    ensure_free(state["app"]["id"])
    ensure_available_everywhere(state["app"]["id"])
    if args.build:
        attach_build(state["app"]["id"], state["version"]["id"], args.build)

    if args.screenshots:
        version_id = state["version"]["id"]
        for locale, text in listing["localizations"].items():
            version_loc = next(
                loc for loc in call("GET", f"/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations")["data"]
                if loc["attributes"]["locale"] == locale
            )
            for display_type, files in text["screenshots"].items():
                replace_screenshots(version_loc["id"], display_type, [LISTING.parent / f for f in files])

    if args.review:
        review = listing["review"]
        print(f"  (assuming {review['demo_account_name']} is on the server's OTP_TEST_NUMBERS "
              "and GEOFENCE_EXEMPT_PHONES -- see the module docstring)")
        attachment = args.attachment or (LISTING.parent / review["attachment"])
        push_review(state["version"]["id"], review, attachment if attachment.exists() else None, args.contact_phone)
    print("✓ done. Submitting for review is still a button in App Store Connect.")


if __name__ == "__main__":
    sys.exit(main())
