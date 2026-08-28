# App Store Connect listing copy

Draft copy for the App Store Connect product page. Adjust freely — this is
a starting point, not a script to paste verbatim.

## App name (30 char max)

`PawConnect`

## Subtitle (30 char max)

`Find trusted pet sitters`

## Promotional text (170 char max, editable without a new review)

`Search local sitters, request bookings, message about the details, and
leave a review — everything you need to line up trustworthy pet care.`

## Description

```
PawConnect connects pet owners with pet sitters in their area.

FOR PET OWNERS
• Search sitters by city, service type, pet type, and hourly rate
• See each sitter's bio, experience, services offered, and reviews
• Add your pets with care notes (feeding schedule, medications, quirks)
• Request a booking for specific dates and message the sitter directly
• Leave a rating and review once the booking is complete

FOR PET SITTERS
• Build a profile: bio, hourly rate, experience, services, accepted pet
  types
• Review and accept or decline booking requests
• Message owners about the details before a booking starts
• Mark bookings complete and build up a public review history

Every booking has its own message thread, and every message, review, and
user can be reported if something's not right.
```

## Keywords (100 char max, comma-separated, no spaces needed)

`pet,sitter,dog,walker,boarding,daycare,pet care,dog walking,pet sitting,house sitting`

## Category

Primary: **Lifestyle**
Secondary: **Business** (marketplace / two-sided booking apps often fit
here too — try both and see which converts better once you have data)

## Age rating

Answer App Store Connect's age rating questionnaire honestly. Relevant bits
for this app:
- **User-generated content**: Yes (messages, reviews) → this pushes the
  minimum rating up and is exactly why the in-app Report feature
  (Guideline 1.2) needs to exist, which it does — see `SUBMISSION_CHECKLIST.md`.
- No violence, mature/suggestive content, gambling, etc. — answer "No" to
  those unless something in your actual content policy says otherwise.

## Support URL / Marketing URL

App Store Connect requires a support URL (a page or even just a `mailto:`
landing page works to start). If you don't have a website yet, a simple
GitHub Pages page with a support email is enough to submit.

## App Privacy questionnaire (App Store Connect > App Privacy)

Map to what the app actually collects (see `PRIVACY_POLICY.md`):

| Data type | Collected? | Linked to identity? | Used for tracking? |
|---|---|---|---|
| Name | Yes | Yes | No |
| Email address | Yes | Yes | No |
| Phone number | Yes (optional) | Yes | No |
| Physical address | No — only a free-text "city" field, not a device location | — | — |
| Precise location | No (app does not request location permission) | — | — |
| User content (messages) | Yes | Yes | No |
| Other user content (reviews, pet notes) | Yes | Yes | No |
| Photos | No (not implemented — add this row if you later add photo upload) | — | — |
| Identifiers (user ID) | Yes | Yes | No |
| Password | Yes (stored hashed) | Yes | No |

None of this data is used for third-party advertising or tracking as
shipped. If you add analytics, crash reporting, or ads later, update this
table and the privacy policy before releasing that version.

## Screenshots

You'll need screenshots sized for at least one 6.5"/6.7" iPhone display
(App Store Connect lists the exact required sizes for whatever devices
you're targeting). Suggested shots, in order:
1. Browse/search sitters (the search filters + results list)
2. A sitter's detail page with reviews
3. The booking request form
4. My Bookings list with a status badge visible
5. A booking's message thread
6. The review form after a completed booking

Capture these from the Simulator (`⌘S` saves a screenshot) once the app is
pointed at a backend with a few realistic-looking sitters/bookings/reviews
seeded in it — empty-state screenshots don't sell the app.
