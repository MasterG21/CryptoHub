# PawConnect Privacy Policy

_Last updated: [FILL IN DATE BEFORE PUBLISHING]_

This policy covers the PawConnect app and its backend service (together,
"PawConnect", "we", "us"). Replace the bracketed placeholders below with
your real details before publishing this page — App Store Connect requires
a live URL to a privacy policy that accurately describes your app, and
"[FILL IN]" placeholders left in a published policy are themselves a
rejection reason.

## Who operates PawConnect

PawConnect is operated by **[YOUR NAME OR BUSINESS NAME]**. You can reach
us at **[YOUR SUPPORT EMAIL]** with any question about this policy or your
data.

## Information we collect

**Account information you provide directly:**
- Full name, email address, and password (stored as a salted PBKDF2 hash —
  we never store or can recover your plaintext password)
- Role (pet owner or pet sitter)
- Optional: phone number and city (a free-text field you type in — the app
  does not access your device's GPS or precise location)

**Content you create in the app:**
- Pet profiles (name, species, breed, care notes) if you're an owner
- Sitter profile details (bio, rate, experience, services, accepted pet
  types) if you're a sitter
- Booking requests (dates, service type, notes)
- Messages you send within a booking's message thread
- Reviews and star ratings you leave after a completed booking
- Reports you file about other users' content

**Automatically collected:** PawConnect does not use analytics SDKs,
advertising identifiers, or crash reporting services as shipped. If you add
any (e.g. for crash reporting), update this section and your App Store
privacy nutrition label to match before releasing.

## How we use this information

- To create and authenticate your account (email + password, via a JSON
  Web Token stored securely in your device's Keychain)
- To show sitter profiles to owners and match booking requests
- To let you communicate with the other party on a booking
- To display reviews and ratings to help owners choose a sitter
- To review and act on content you or others report (see **Moderation**
  below)

We do not sell your personal information, and we do not use your data for
third-party advertising.

## Moderation and reporting

PawConnect lets users report messages, reviews, or other users they believe
are spam, abusive, inappropriate, or a safety concern. Reports are reviewed
by **[describe your moderation process — even "the app's operator reviews
reports submitted through the app and may remove content or suspend
accounts that violate these terms" is fine for a small team]**.

## Data retention and deletion

We retain your account and content for as long as your account is active.
To request deletion of your account and associated data, email
**[YOUR SUPPORT EMAIL]** — [describe your actual process and expected
turnaround time].

## Children's privacy

PawConnect is not directed at children under 13, and we do not knowingly
collect information from them.

## Changes to this policy

We may update this policy from time to time. Material changes will be
reflected here with an updated "Last updated" date.

## Contact

Questions about this policy: **[YOUR SUPPORT EMAIL]**

---

### Notes for whoever is publishing this (delete before publishing)

- Fill in every bracketed placeholder above.
- Host the final version at a stable, public URL (GitHub Pages is a free,
  easy option: enable Pages for this repo, point it at this file or a
  converted HTML version). App Store Connect asks for this exact URL under
  **App Privacy > Privacy Policy URL**.
- Make sure this document's claims match what the App Store Connect
  "App Privacy" questionnaire says you collect — see
  `APP_STORE_LISTING.md` in this directory for a mapping to that
  questionnaire's categories.
