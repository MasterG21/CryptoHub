# PawConnect for iOS

A native SwiftUI client for the PawConnect backend (`pet_sitter_app/app`) —
browse and search sitters, request bookings, message about a booking, leave
reviews, and report objectionable content. No third-party dependencies.

This directory has Swift source files and a `project.yml` (an
[XcodeGen](https://github.com/yonaskolb/XcodeGen) spec) instead of a
committed `.xcodeproj`, since `.xcodeproj` files are large, binary-ish, and
merge-conflict-prone. You generate the real Xcode project locally.

**Everything below requires a Mac with Xcode.** This project was built and
tested in a Linux cloud session that has no way to run Xcode, sign a binary,
or talk to App Store Connect — those steps only work on your machine with
your Apple ID.

## Prerequisites

- A Mac running a recent version of Xcode (15+ recommended; the project
  targets iOS 16+)
- [XcodeGen](https://github.com/yonaskolb/XcodeGen): `brew install xcodegen`
- An [Apple Developer Program](https://developer.apple.com/programs/)
  account ($99/year) if you intend to run on a physical device, use
  TestFlight, or submit to the App Store. A free Apple ID is enough to run
  in the iOS Simulator.
- The backend deployed somewhere with a public HTTPS URL — see
  `../DEPLOYMENT.md`. The Simulator can also talk to `http://localhost:8000`
  for local development (already allow-listed in `project.yml`'s ATS
  exception), but a release build must point at your real backend.

## First-time setup

```bash
cd pet_sitter_app/ios/PawConnect

# 1. Point the app at your deployed backend (skip this to keep testing
#    against localhost in the Simulator for now):
#    edit project.yml -> settings.base.API_BASE_URL

# 2. Generate the Xcode project
xcodegen generate

# 3. Open it
open PawConnect.xcodeproj
```

In Xcode:
1. Select the `PawConnect` target > **Signing & Capabilities**.
2. Pick your Team (or set `DEVELOPMENT_TEAM` in `project.yml` and re-run
   `xcodegen generate`).
3. Change `PRODUCT_BUNDLE_IDENTIFIER` in `project.yml` from
   `com.pawconnect.app` to something under your own domain if `pawconnect`
   is already taken in App Store Connect (bundle IDs are globally unique).
4. Build and run (⌘R) — pick a Simulator, or a physical device once it's
   registered to your team.

## Project layout

```
PawConnect/
  App/PawConnectApp.swift       App entry point
  Models/Models.swift            Codable models mirroring app/schemas.py
  Networking/                    APIClient (URLSession + async/await), APIService
                                  (one typed method per endpoint), Keychain-backed
                                  token storage, date formatting
  ViewModels/                    SessionStore (auth), Browse/Bookings/Pets view models
  Views/
    Auth/          Login + registration
    Browse/         Search/filter sitters, sitter detail, inline booking request form
    Bookings/       Booking list/detail, status transitions, messaging, reviews
    Profile/        Owner pet management / sitter profile editor
    Shared/         Theme, status badge, the report-content sheet
  Resources/Assets.xcassets      App icon (paw mark) + accent color
```

Every screen maps directly to a `pet_sitter_app/app/routers/*.py` endpoint —
if you change the backend's API shape, update `Models/Models.swift` and
`Networking/APIService.swift` to match.

## Whenever you add/remove/rename Swift files

Re-run `xcodegen generate` — it re-derives the `.xcodeproj` target
membership from what's on disk in `project.yml`'s `sources` path, so you
never hand-edit project file references.

## Testing before you submit

1. Run in the Simulator against your deployed backend and walk the full
   flow once: register as an owner and as a sitter, search, request a
   booking, accept it (as the sitter), exchange a message, mark it
   completed, leave a review, and try the Report action.
2. Run on a physical device at least once — Simulator networking and Sign
   in with Apple/Keychain behavior can differ slightly from device.
3. See `../SUBMISSION_CHECKLIST.md` for what Apple's review process expects
   beyond "it runs."
