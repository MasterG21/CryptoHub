# Getting PawConnect onto the App Store: checklist

Two kinds of steps below: things already done in this repo, and things that
can only happen on your Mac with your own Apple ID — no AI session can do
the second group for you, since it requires your identity, payment method,
and device access.

## Already done in this repo

- [x] Backend API (`pet_sitter_app/app`) with auth, sitter search, pets,
      bookings, messaging, reviews — tested (`pytest tests/`, 14 passing)
- [x] Report/moderation endpoint (`POST /api/reports`) — required for
      Guideline 1.2 (user-generated content) since the app has messaging
      and reviews
- [x] Native SwiftUI iOS client (`pet_sitter_app/ios/PawConnect`) covering
      every screen: auth, browse/search, sitter detail + booking request,
      bookings list/detail with status transitions, messaging, reviews,
      and a Report action on messages/reviews/users
- [x] App icon (`Resources/Assets.xcassets/AppIcon.appiconset`)
- [x] `Dockerfile` + `DEPLOYMENT.md` for hosting the backend publicly
- [x] Draft privacy policy (`PRIVACY_POLICY.md`) and App Store listing
      copy (`APP_STORE_LISTING.md`) — both need your details filled in

## Only you can do these (requires your Mac + your Apple ID)

### 1. Deploy the backend
- [ ] Pick a host and follow `DEPLOYMENT.md` — get a public HTTPS URL
- [ ] Generate and set `PET_SITTER_SECRET_KEY` so tokens survive restarts
- [ ] Decide on SQLite-with-a-volume (fine to start) vs. Postgres (better
      for real traffic)

### 2. Apple Developer Program
- [ ] Enroll at https://developer.apple.com/programs/ ($99/year, needs
      your legal name or business details and a payment method)
- [ ] Note your **Team ID** (Membership Details page) — goes into
      `project.yml`'s `DEVELOPMENT_TEAM`

### 3. Build the iOS app
- [ ] Install Xcode + XcodeGen on a Mac (see `ios/PawConnect/README.md`)
- [ ] Set `API_BASE_URL` in `project.yml` to your deployed backend's URL
- [ ] Pick a unique bundle identifier (change from `com.pawconnect.app` if
      that's taken)
- [ ] `xcodegen generate`, open the project, sign in with your Apple ID in
      Xcode, select your Team
- [ ] Run on Simulator and at least one physical device; walk the full
      flow (register both roles, search, book, accept, message, complete,
      review, report) end to end against your real backend

### 4. App Store Connect record
- [ ] Create the app at https://appstoreconnect.apple.com (needs the
      bundle ID from step 3 registered first, in the Apple Developer
      portal's Identifiers section)
- [ ] Fill in the listing using `APP_STORE_LISTING.md` as a starting draft
- [ ] Publish `PRIVACY_POLICY.md` (filled in) at a public URL and paste
      that URL into App Privacy
- [ ] Complete the App Privacy questionnaire using the table in
      `APP_STORE_LISTING.md`
- [ ] Complete the age rating questionnaire (flag user-generated content)
- [ ] Upload screenshots (see the list in `APP_STORE_LISTING.md`)

### 5. TestFlight (strongly recommended before submitting for review)
- [ ] Archive the app in Xcode (**Product > Archive**), upload to App Store
      Connect via the Organizer
- [ ] Add yourself (and any other testers) in TestFlight, install via the
      TestFlight app, and use it for real for a few days
- [ ] Fix anything that surfaces before moving to review

### 6. Submit for review
- [ ] Select the build in App Store Connect, fill in "App Review
      Information" (a demo account is a good idea here — reviewers will
      need to register anyway since it's free, but a pre-made
      owner+sitter pair with an existing booking saves them time and
      avoids a rejection for "we couldn't find any content to review")
- [ ] Submit

## Common rejection reasons for an app like this — worth double-checking

- **Guideline 1.2 (User-Generated Content)**: needs a way to report
  objectionable content (done — the Report action) and, ideally, a
  published content policy / terms of use reviewers can find. Consider
  adding a simple Terms of Use to your support page.
- **Guideline 5.1.1 (Data Collection and Storage)**: the privacy policy
  URL must be live and must accurately describe what's collected — don't
  submit with placeholder text still in it.
- **Guideline 2.1 (App Completeness)**: don't submit against a backend
  that's asleep/unreachable (some free hosting tiers spin down when idle —
  Apple's reviewer will hit a dead API on first load and reject). Confirm
  the deployed backend responds before submitting, and consider a paid
  tier or a keep-alive ping if you're on a tier that sleeps.
- **Guideline 4.8 (Sign in with Apple)**: only required if you offer
  *third-party* login (Sign in with Google/Facebook/etc). Plain
  email/password, which is all this app has, doesn't trigger this
  requirement.
- **Empty states**: make sure a fresh reviewer account browsing the app
  doesn't hit a completely empty "no sitters found" screen with nothing
  else to do — seed a few realistic sitter profiles on your production
  backend before submitting.
