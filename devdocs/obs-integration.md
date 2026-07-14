# OBS Studio Integration (Phase 1: Browser Source overlay)

Lets a host add the second-screen overlay (segment title, sponsor, QR code)
directly into OBS Studio as a **Browser Source**, composited over their
camera feed, updating live as segments change from Control Room. No OBS
scripting, plugins, or websocket control involved — this is the same
mechanism most streaming tools use for sponsor/lower-third overlays.

## How to use it

1. Open an episode's Control Room.
2. Expand **🎥 Use in OBS Studio** at the bottom of the Live Control panel.
3. Copy the overlay URL and add it to OBS: **Sources → + → Browser**, paste
   the URL, set Width/Height to match your canvas (e.g. 1920×1080).
4. The first time OBS loads it, it'll hit our normal login page (OBS's
   browser source is a real, isolated Chromium profile) — sign in once
   there; the session persists in that profile afterward, like any browser.
5. Leave "Shutdown source when not visible" **unchecked** so the overlay
   keeps polling for segment changes even while its scene isn't active.
6. Resize/position the source over the camera in your scene — the page
   background is transparent in this mode, so only the segment card and
   sponsor bar render, nothing else.

## How it works

- `?overlay=1` on the existing second-screen URL
  (`SecondScreenView`, `production_ledger/views.py`) sets `is_overlay` in
  the template context.
- `second_screen.html`: an `overlay` body class strips the opaque
  background and the gradient scrim (`body.overlay .stage::after { display:
  none }`), and hides the connection-status dot. The JS `render()` function
  also skips the show name/logo/episode title text and, when no segment is
  live, renders nothing at all (rather than the "Stand by…" placeholder
  a human would see on a real second monitor) — you don't want a floating
  placeholder box sitting over your webcam between segments.
- No new auth mechanism: this reuses the exact same `LoginRequiredMixin` +
  session cookie as the regular second-screen page, per the explicit
  decision to keep this simple rather than build a signed-token bypass.
  OBS's browser source keeps its own cookie jar in its CEF profile, so
  logging in once there is a one-time setup step, not a per-session one —
  it survives OBS restarts, but can be reset by clearing OBS's browser
  cache or a major OBS update resetting its CEF profile.
- No new dependencies, no websocket, no OBS scripting.

## What's out of scope for this phase (documented, not built)

Per explicit scope decision, this pass is Browser-Source-only. Deferred:

- **OBS-WebSocket control** (auto-detecting OBS, auto-adding the source to
  a scene, starting/stopping recording from the app). Research finding:
  this can only ever work from JavaScript running in the *presenter's own
  browser tab* connecting to `ws://127.0.0.1:4455` — the Django server
  itself can never reach into a client's local machine to detect or control
  OBS, regardless of architecture. If built later, it's a client-side-only
  feature using the `obsws-python`-equivalent JS client, not a backend
  integration.
- **In-app recording fallback** (`getUserMedia`/`MediaRecorder` capturing a
  single webcam+mic locally in-browser, uploading into `MediaAsset`). Also
  deferred — noted here so it's not lost, since it's the natural fallback
  for someone without OBS at all.
- **Multi-guest/remote call-in, scene switching from the app, or any
  compositing beyond "one static overlay over one camera"** — explicitly
  future work per the original request.

## Tests

`production_ledger/test_second_screen_e2e.py::test_overlay_mode_is_transparent_and_control_room_links_it`
— confirms Control Room links the `?overlay=1` URL and shows the OBS
instructions panel, and that overlay mode actually sets the `overlay` body
class and `IS_OVERLAY` JS flag (vs. `false` on the normal page).
