# Usage Guide

## Overview

Production Ledger is a comprehensive system for managing podcast and media production workflows. It provides:

- **Show Management**: Organize content by show/series
- **Episode Workflow**: Track episodes from draft to publication
- **Guest Management**: Maintain a directory of guests and their appearances
- **Media Ingestion**: Upload and track audio/video assets
- **Transcript Management**: Import and version transcripts
- **Clip Marking**: Mark highlight moments for promotion
- **AI Drafts**: Generate content with human approval gates
- **Show Notes**: Create, edit, and finalize episode descriptions
- **Exports**: Package episodes for publishing platforms

## Accessing the Dashboard

Navigate to `/ledger/` to access the main dashboard. From here you can:

- View all shows you have access to
- See recent episode activity
- Quick-access common workflows

## Core Workflows

### 1. Creating a Show

1. From the dashboard, click **"+ New Show"**
2. Enter the show name and slug
3. Optionally add description and default settings
4. Save to create the show

### 2. Episode Lifecycle

Episodes follow a defined workflow:

```
draft → planned → scheduled → recorded → ingested → transcribed → edited → approved → published
```

To move an episode through stages:

1. Open the episode detail page
2. Click **"Change Status"**
3. Select the next valid status
4. Confirm the transition

**Note**: Transitioning to "approved" or "published" requires completing the episode checklist.

### 3. Control Room

The Control Room provides a single-page view of all episode workflows:

1. Open an episode
2. Click **"🎬 Control Room"**
3. See status of: Planning, Media, Transcript, Clips, AI Content, Show Notes
4. Quick links to each workflow section

### 4. Managing Segments (Run of Show)

1. Go to episode → **Segments** tab
2. Add segments with: order, title, duration, owner
3. Include key questions for interview segments
4. Reorder by editing segment numbers

### 5. Adding Guests

1. First, add guests to your directory: `/ledger/guests/`
2. Then add guests to episodes via the **Guests** tab
3. Assign roles (Primary, Supporting, Cameo)
4. Track quote approval status

### 6. Uploading Media

1. Go to episode → **Media** tab
2. Select asset type (raw audio, edited audio, video, etc.)
3. Upload the file
4. System computes checksum for verification

### 7. Working with Transcripts

1. Go to episode → **Transcript** tab
2. Upload an SRT/VTT file OR paste text directly
3. Edit transcript content as needed
4. System tracks versions automatically

### 8. Marking Clips

1. Go to episode → **Clips** tab
2. Enter start/end times in seconds
3. Add title and reason/notes
4. Set priority (must, should, could)

### 9. AI Content Generation

1. Go to episode → **AI Drafts** tab
2. Select content type (show notes, questions, social posts)
3. Optionally provide topic/focus prompt
4. Click **"🤖 Generate"**
5. Review the generated content
6. **Approve** or **Reject** with notes

**Important**: All AI output requires human approval before use.

### 10. Finalizing Show Notes

1. Go to episode → **Show Notes** tab
2. Create drafts manually or from approved AI artifacts
3. Edit content as needed
4. When ready, click **"✓ Finalize"** to lock the official version

### 11. Exporting for Publishing

1. Go to episode → **Exports** tab
2. Download individual exports:
   - **JSON Package**: Complete structured data
   - **Show Notes (Markdown)**: For website/blog
   - **Clips CSV**: For video editing/social
   - **Guest Briefs**: Preparation documents
3. Or download **Complete Package (ZIP)** with everything

## API Access

All features are available via REST API at `/api/ledger/`:

```bash
# List shows
curl -H "Authorization: Token <token>" http://localhost:8000/api/ledger/shows/

# Get episode details
curl -H "Authorization: Token <token>" http://localhost:8000/api/ledger/episodes/<uuid>/

# Generate AI content
curl -X POST -H "Authorization: Token <token>" \
  -d '{"artifact_type": "show_notes", "topic_prompt": "Focus on startup tips"}' \
  http://localhost:8000/api/ledger/episodes/<uuid>/generate/
```

## Tips

- Use the **Control Room** for a comprehensive view of episode status
- Complete the **Checklist** before trying to approve/publish
- **AI drafts** are starting points—always review and edit
- **Export packages** include all metadata for integration with publishing platforms
