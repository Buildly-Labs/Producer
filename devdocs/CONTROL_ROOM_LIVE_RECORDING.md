# Control Room - Live Recording Feature

## Overview

The Control Room has been enhanced with a complete "Start the Show" live recording interface that provides real-time production support during podcast recording sessions.

## What Was Implemented

### 1. Database Enhancements ✅

**File**: `production_ledger/models.py`

Added three new fields to the `Segment` model:
- `is_completed` (Boolean) - Tracks whether a segment has been completed during recording
- `completed_at` (DateTime) - Timestamp when segment was marked complete
- `live_notes` (TextField) - Notes captured during live recording of this segment

**Migration**: `production_ledger/migrations/0008_add_segment_live_recording_fields.py`

### 2. Enhanced Control Room View ✅

**File**: `production_ledger/views.py` (lines 873-960)

Updated `ControlRoomView` to support three modes:
- **Dashboard Mode** (default) - Quick access to all workflows
- **Live Mode** (`?mode=live`) - Full production interface during recording
- **Guest View** (`?view=guest`) - Simplified view for guests

New POST actions added:
- `toggle_segment` - Mark segments complete/incomplete (AJAX)
- `save_segment_notes` - Auto-save live notes per segment (AJAX)

### 3. Three New Templates ✅

#### A. Control Room Dashboard (Enhanced)
**File**: `production_ledger/templates/production_ledger/control_room.html`

Added prominent **"START THE SHOW"** button that launches live recording mode.

#### B. Live Recording Interface
**File**: `production_ledger/templates/production_ledger/control_room_live.html`

**Features:**
- ⏱️ **Live Timer** - Start/pause/reset timer to track recording duration
- 📊 **Progress Tracking** - Visual progress bar showing segments completed
- ✅ **Interactive Checklist** - Click checkboxes to mark segments complete
- 📝 **Live Notes per Segment** - Expandable note-taking for each segment
- 💡 **Show Rundown** - All segments with prompts and questions visible
- 👥 **Guest Quick Reference** - Guest bios and key topics at top
- 🎯 **Auto-Save** - Notes automatically save when you click outside text area

**Technology:**
- Alpine.js for reactive UI
- Tailwind CSS for styling
- Async/await for AJAX calls
- Visual feedback for completed segments

#### C. Guest View
**File**: `production_ledger/templates/production_ledger/control_room_guest.html`

**Features:**
- 🎯 **Single Segment Focus** - Shows one segment at a time in large, readable format
- ⌨️ **Keyboard Navigation** - Arrow keys to move between segments
- 💡 **Talking Points** - Large, easy-to-read bullet points
- ❓ **Key Questions** - Questions to answer during this segment
- ⚠️ **No-Go Topics** - Topics to avoid (if specified)
- 📋 **Quick Reference** - Collapsible view of all segments
- 🎨 **Clean Design** - Distraction-free interface for guests

**Technology:**
- Standalone HTML page (no base template dependencies)
- Full-screen gradient background
- Large text for easy reading during recording

## How to Use

### For Hosts/Producers

1. **Navigate to Control Room**
   ```
   /producer/episodes/<episode-uuid>/control-room/
   ```

2. **Click "START THE SHOW" button**
   - Redirects to: `/producer/episodes/<episode-uuid>/control-room/?mode=live`

3. **During Recording:**
   - Click ▶ Start to begin timer
   - Check off segments as you complete them
   - Click "Add live notes" to capture thoughts/quotes/timestamps per segment
   - Notes auto-save when you click outside the text box
   - Progress bar updates automatically

4. **Open Guest View** (optional)
   - Click "📺 Open Guest View" button
   - Opens in new tab/window
   - Share this screen with guests during remote recordings

5. **End Recording**
   - Click "🏁 End Recording" to return to episode detail

### For Guests

Hosts can share the Guest View URL:
```
/producer/episodes/<episode-uuid>/control-room/?view=guest
```

**Guest Interface:**
- See current segment with large, readable text
- Use Previous/Next buttons to navigate
- Use arrow keys (← →) for quick navigation
- View talking points, questions, and topics for each segment
- No production clutter - just what they need to know

## URLs

| URL Pattern | Description |
|-------------|-------------|
| `/producer/episodes/<uuid>/control-room/` | Default dashboard |
| `/producer/episodes/<uuid>/control-room/?mode=live` | Live recording interface |
| `/producer/episodes/<uuid>/control-room/?view=guest` | Guest view (simplified) |

## Data Flow

### Segment Completion
1. User clicks checkbox → JavaScript toggles state
2. AJAX POST to server with `action=toggle_segment`
3. Server updates `is_completed` and `completed_at` fields
4. Returns JSON response
5. Progress bar updates automatically

### Live Notes
1. User types in notes textarea
2. On blur (click outside), JavaScript triggers save
3. AJAX POST to server with `action=save_segment_notes`
4. Server saves to `segment.live_notes` field
5. No page reload needed

## Features Breakdown

### Live Recording View (Host)

| Feature | Description |
|---------|-------------|
| Timer | Start/pause/reset with HH:MM:SS display |
| Progress Bar | Visual indicator of segments completed |
| Segment Cards | Each segment shows: order, duration, owner, prompts, questions |
| Checkboxes | Mark segments complete in real-time |
| Live Notes | Per-segment expandable note-taking |
| Guest Info | Quick reference card at top |
| Auto-Save | Notes save automatically on blur |
| Visual Feedback | Completed segments get green border and fade |

### Guest View

| Feature | Description |
|---------|-------------|
| Single Focus | One segment at a time, full screen |
| Large Text | 2-3x normal size for easy reading |
| Navigation | Previous/Next buttons + arrow keys |
| Talking Points | Highlighted in yellow with large font |
| Key Questions | Highlighted in green with large font |
| Topics | Guest-specific prep notes |
| No-Go Topics | Red warning box if specified |
| All Segments | Collapsible list to jump to any segment |

## Technical Details

### Alpine.js Data Structure

```javascript
{
  // Timer
  elapsedSeconds: 0,
  isRunning: false,
  timerInterval: null,

  // Segments
  segments: [
    { id: 'uuid', completed: false, notes: '' },
    // ...
  ],

  // Computed properties
  completedCount: // calculated
  progressPercentage: // calculated
}
```

### AJAX Endpoints

**Toggle Segment:**
```javascript
POST /producer/episodes/<uuid>/control-room/
{
  action: 'toggle_segment',
  segment_id: 'uuid',
  csrfmiddlewaretoken: 'token'
}

Response: { success: true, is_completed: true, completed_at: '2025-01-15T...' }
```

**Save Notes:**
```javascript
POST /producer/episodes/<uuid>/control-room/
{
  action: 'save_segment_notes',
  segment_id: 'uuid',
  notes: 'Note content...',
  csrfmiddlewaretoken: 'token'
}

Response: { success: true }
```

## File Changes Summary

| File | Type | Changes |
|------|------|---------|
| `models.py` | Modified | Added 3 fields to Segment model |
| `views.py` | Modified | Enhanced ControlRoomView with mode support |
| `control_room.html` | Modified | Added "START THE SHOW" button |
| `control_room_live.html` | Created | Full live recording interface |
| `control_room_guest.html` | Created | Guest-focused view |
| `0008_add_segment_live_recording_fields.py` | Created | Database migration |

## Testing Checklist

- [ ] Database migration runs successfully
- [ ] "START THE SHOW" button appears on control room dashboard
- [ ] Live recording interface loads at `?mode=live`
- [ ] Timer starts/pauses/resets correctly
- [ ] Checking segments updates progress bar
- [ ] Live notes save without page reload
- [ ] Guest view loads at `?view=guest`
- [ ] Guest view navigation works (buttons + arrow keys)
- [ ] All segments display correctly in both views
- [ ] AJAX requests work without errors
- [ ] Progress percentage calculates correctly

## Future Enhancements

Potential improvements for future versions:

1. **Real-time Sync** - WebSocket support for multi-user collaboration
2. **Audio Waveform** - Visual audio playback during recording
3. **Clip Markers** - Quick clip creation with timer-based timestamps
4. **AI Transcription** - Live transcript during recording
5. **Producer Notes** - Separate notes field visible only to producers
6. **Recording Status** - "On Air" indicator shared across all views
7. **Countdown Timer** - Target time vs elapsed with warnings
8. **Break Timer** - Pause recording with separate break counter
9. **Guest Prompting** - Host can send specific prompts to guest view
10. **Export Recording Notes** - Generate formatted notes document after recording

## Troubleshooting

**Migration fails:**
- Check if there's a conflicting old migration
- Try: `python3 manage.py migrate production_ledger --fake-initial`
- Or delete db.sqlite3 and re-run all migrations

**AJAX not working:**
- Check browser console for JavaScript errors
- Verify CSRF token is present
- Check Django logs for backend errors

**Timer not starting:**
- Check Alpine.js is loaded (should see `[x-data]` in dev tools)
- Verify no JavaScript errors in console

**Guest view not displaying:**
- Ensure segments exist for the episode
- Check template path in view `get_template_names()`
- Verify Tailwind CSS is loading from CDN

## Best Practices

1. **Before Recording:**
   - Create all segments with prompts and questions
   - Add guest information and prep notes
   - Review the rundown in control room dashboard

2. **During Recording:**
   - Start timer when recording begins
   - Check off segments as you complete them
   - Add live notes for memorable quotes, timestamps, or follow-ups
   - Share guest view screen if recording remotely

3. **After Recording:**
   - Review live notes before closing
   - Export notes for post-production
   - Check all segments are marked complete

## Support

For issues or questions:
- Check Django logs: `tail -f /path/to/logs/`
- Check browser console for JavaScript errors
- Review this documentation
- Check Producer README.md for general setup

---

**Status**: ✅ COMPLETE
**Version**: 1.0.0
**Last Updated**: 2025-01-15
**Author**: AI Engineering Team
