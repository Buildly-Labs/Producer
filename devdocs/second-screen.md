# Second Screen: Live Broadcast Display

A full-screen display for a second monitor during live recording. Shows
the show's branding, the currently-live segment, and that segment's
sponsor with a scannable QR code to the sponsor's site/ad.

## How it works

1. Before recording, add a `Sponsor` to a `Show` (Django admin, or a future
   dedicated UI) — name, website URL, ad copy, optional logo. Sponsors are
   scoped to a show and reusable across episodes (e.g. a recurring sponsor
   for a weekly segment).
2. When building the run of show, optionally assign a sponsor to each
   `Segment` (Segments tab → Add/Edit Segment → Sponsor dropdown, scoped to
   the show's active sponsors).
3. Open the episode's **Control Room**. Click **Open Second Screen** — this
   opens `/ledger/episodes/<id>/second-screen/` in a new tab/window; drag
   that window to the second monitor and make it full-screen.
4. As the show progresses, click **Set Live** next to the current segment
   in Control Room's new "Live Control" panel. The second screen picks this
   up automatically — no need to touch the second monitor at all.
5. **Clear live segment** returns the second screen to its default
   "Stand by…" state (or the show's default background, if one is set).

## Data model additions

- `Show.logo`, `Show.second_screen_background` — branding images
  (`production_ledger/models.py`).
- `Sponsor` — new model: `show` FK, `name`, `website_url`, `ad_copy`,
  `logo`, `is_active`. Reusable across segments/episodes.
- `Segment.sponsor` — optional FK to `Sponsor`.
- `Episode.active_segment` — optional FK to `Segment`, tracks what's
  currently live. Set/cleared only from Control Room.

Migration: `production_ledger/migrations/0005_episode_active_segment_show_logo_and_more.py`.

## Views/URLs

- `GET /ledger/episodes/<pk>/second-screen/` — `SecondScreenView`, the
  full-screen display page. Read-only, `Role.GUEST` minimum (same
  visibility as other episode tabs).
- `GET /ledger/episodes/<pk>/second-screen/state/` — `SecondScreenStateView`,
  JSON polled by the display page every 4s.
- `GET /ledger/sponsors/<pk>/qr-code/` — `SponsorQRCodeView`, generates a
  PNG QR code (via the `qrcode` package) pointing at the sponsor's
  `website_url`. Cached 5 minutes client-side.
- `ControlRoomView.post()` gained a `set_live_segment` action:
  `POST` with `action=set_live_segment` and `segment_id` (empty string
  clears it). Requires the same roles as the rest of Control Room
  (`ADMIN`, `HOST`, `PRODUCER`).

## Sync mechanism

Deliberately simple: the second-screen page polls its JSON state endpoint
every 4 seconds. No websockets/Django Channels — the project has neither
installed, and a second monitor tucked away for the duration of a
recording doesn't need sub-second latency. The connection-status dot
(top-right of the display) turns red if three consecutive polls fail, so
a producer glancing at the second monitor can tell if it's gone stale.

## Dependencies added

- `Pillow==10.4.0` — required by Django's `ImageField` (was previously
  installed ambiently but never declared in `requirements.txt`).
- `qrcode==7.4.2` — QR code generation.
- `MEDIA_ROOT`/`MEDIA_URL` settings and a dev-mode media-serving route were
  also added (`logic_service/settings/base.py`, `logic_service/urls.py`) —
  these didn't exist before, so `Show.logo`/`Sponsor.logo` uploads would
  have had nowhere to go.

## Tests

`production_ledger/test_second_screen_e2e.py` — exercises the full flow:
Control Room renders Set Live controls, setting a segment live persists
and is reflected in both the second-screen page and its JSON state, the
QR code endpoint returns a valid PNG, and clearing the live segment works.

## Bugs found and fixed along the way

While building this, exercising `control_room.html`'s full render (which
none of the prior work had actually done) surfaced two previously-unknown,
sitewide-breaking template bugs — every page extending `base.html` was
one click away from a 500:

1. **`{% url 'production_ledger:episode_list' %}`** in
   `templates/partials/sidebar.html` — no such URL existed anywhere (there
   was no episode-listing view at all, only per-episode routes). Fixed by
   adding `EpisodeListView` + `episode_list.html` + the URL pattern.
2. **`{% url 'production_ledger:logout' %}`** in `templates/partials/navbar.html`,
   and **`{% url 'production_ledger:login' %}` / `{% url 'production_ledger:register' %}`**
   in `production_ledger/templates/production_ledger/landing.html` — `login`
   and `logout` are registered at the root `urls.py` with no app namespace,
   and `register` doesn't exist at all (there's no self-serve signup — accounts
   are admin-provisioned). Fixed the login/logout references to the
   un-namespaced names, and pointed the "Get Started" CTAs at login instead
   of a nonexistent registration page.

Separately (not fixed — flagged as its own follow-up): `production_ledger/tests.py`
has 15 of 20 tests failing against the current model API (stale
`transition_to()` return-value contract, a bad `ShowRoleAssignment` field).
This predates the second-screen work and is unrelated to it.
