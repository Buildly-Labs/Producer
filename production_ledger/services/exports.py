"""
Export Service Layer for Production Ledger.

Provider-agnostic export functions for generating publishing packages.
Exports are generated on-demand and can be downloaded or stored.
"""
import csv
import io
import json
from datetime import datetime
from typing import Optional

from django.template.loader import render_to_string
from django.utils import timezone

from ..models import (
    ClipMoment,
    Episode,
    EpisodeGuest,
    Guest,
    Segment,
    ShowNoteDraft,
    ShowNoteFinal,
    Transcript,
)


# =============================================================================
# JSON EXPORT
# =============================================================================

def export_episode_package_json(episode: Episode) -> dict:
    """
    Export a complete episode package as a JSON-serializable dict.
    
    Includes:
    - Episode metadata
    - Show info
    - Segments
    - Guests
    - Transcripts (metadata only)
    - Clips
    - Show notes (final or latest draft)
    - Checklist status
    
    Args:
        episode: The episode to export
    
    Returns:
        dict: Complete episode package
    """
    # Basic episode info
    package = {
        'export_generated_at': timezone.now().isoformat(),
        'export_version': '1.0',
        'episode': {
            'id': str(episode.id),
            'title': episode.title,
            'status': episode.status,
            'episode_type': episode.episode_type,
            'target_minutes': episode.target_minutes,
            'recording_context': episode.recording_context,
            'scheduled_for': episode.scheduled_for.isoformat() if episode.scheduled_for else None,
            'publish_date': episode.publish_date.isoformat() if episode.publish_date else None,
            'created_at': episode.created_at.isoformat(),
            'updated_at': episode.updated_at.isoformat(),
        },
        'show': {
            'id': str(episode.show.id),
            'name': episode.show.name,
            'slug': episode.show.slug,
            'description': episode.show.description,
            'brand_primary_color': episode.show.brand_primary_color,
        },
    }
    
    # Segments (Run of Show)
    segments = episode.segments.all().order_by('order')
    package['segments'] = [
        {
            'order': s.order,
            'title': s.title,
            'purpose': s.purpose,
            'timebox_minutes': s.timebox_minutes,
            'owner_role': s.owner_role,
            'bullet_prompts': s.bullet_prompts,
            'key_questions': s.key_questions,
        }
        for s in segments
    ]
    
    # Guests
    episode_guests = episode.episode_guests.select_related('guest').all()
    package['guests'] = [
        {
            'name': eg.guest.name,
            'title': eg.guest.title,
            'organization': eg.guest.org,
            'bio': eg.guest.bio,
            'links': eg.guest.links,
            'role': eg.role,
            'key_topics': eg.key_topics,
            'prep_notes': eg.prep_notes,
            'quote_approval_status': eg.quote_approval_status,
        }
        for eg in episode_guests
    ]
    
    # Transcripts (metadata only - full text can be large)
    transcripts = episode.transcripts.all().order_by('-revision')
    package['transcripts'] = [
        {
            'id': str(t.id),
            'revision': t.revision,
            'source_type': t.source_type,
            'format': t.format,
            'confidence_overall': t.confidence_overall,
            'created_at': t.created_at.isoformat(),
            'text_length': len(t.raw_text) if t.raw_text else 0,
        }
        for t in transcripts
    ]
    
    # Clips
    clips = episode.clip_moments.all().order_by('start_ms')
    package['clips'] = [
        {
            'id': str(c.id),
            'title': c.title,
            'start_ms': c.start_ms,
            'end_ms': c.end_ms,
            'start_formatted': c.start_formatted,
            'end_formatted': c.end_formatted,
            'hook': c.hook,
            'caption_draft': c.caption_draft,
            'tags': c.tags,
            'priority': c.priority,
        }
        for c in clips
    ]
    
    # Show Notes
    try:
        final = episode.show_note_final
        package['show_notes'] = {
            'type': 'final',
            'markdown': final.markdown,
            'approved_by': final.approved_by.username if final.approved_by else None,
            'approved_at': final.approved_at.isoformat() if final.approved_at else None,
        }
    except ShowNoteFinal.DoesNotExist:
        # Fall back to latest draft
        draft = episode.show_note_drafts.order_by('-created_at').first()
        if draft:
            package['show_notes'] = {
                'type': 'draft',
                'markdown': draft.markdown,
                'chapters': draft.chapters_json,
                'resources': draft.resources_json,
                'created_at': draft.created_at.isoformat(),
            }
        else:
            package['show_notes'] = None
    
    # Checklist status
    checklist = episode.checklist_items.all().order_by('sort_order')
    package['checklist'] = [
        {
            'title': item.title,
            'is_required': item.is_required,
            'is_done': item.is_done,
            'done_by': item.done_by.username if item.done_by else None,
            'done_at': item.done_at.isoformat() if item.done_at else None,
        }
        for item in checklist
    ]
    
    package['checklist_complete'] = episode.is_checklist_complete()
    
    return package


def export_episode_package_json_string(episode: Episode) -> str:
    """Export episode package as a formatted JSON string."""
    return json.dumps(export_episode_package_json(episode), indent=2)


# =============================================================================
# MARKDOWN EXPORT
# =============================================================================

def export_show_notes_markdown(
    episode: Episode,
    use_final: bool = True,
) -> str:
    """
    Export show notes as Markdown.
    
    Args:
        episode: The episode to export notes for
        use_final: If True, use final notes. If False or no final exists, use latest draft.
    
    Returns:
        str: Show notes in Markdown format
    """
    content = ""
    
    # Header
    content += f"# {episode.title}\n\n"
    content += f"**Show:** {episode.show.name}\n"
    
    if episode.publish_date:
        content += f"**Published:** {episode.publish_date.strftime('%B %d, %Y')}\n"
    
    # Guests
    guests = episode.episode_guests.select_related('guest').all()
    if guests:
        content += "\n**Guests:**\n"
        for eg in guests:
            g = eg.guest
            guest_line = f"- {g.name}"
            if g.title:
                guest_line += f", {g.title}"
            if g.org:
                guest_line += f" at {g.org}"
            content += guest_line + "\n"
    
    content += "\n---\n\n"
    
    # Main content
    try:
        if use_final:
            final = episode.show_note_final
            content += final.markdown
            content += f"\n\n---\n*Final notes approved by {final.approved_by.username if final.approved_by else 'Unknown'} on {final.approved_at.strftime('%Y-%m-%d') if final.approved_at else 'Unknown'}*\n"
        else:
            raise ShowNoteFinal.DoesNotExist
    except ShowNoteFinal.DoesNotExist:
        draft = episode.show_note_drafts.order_by('-created_at').first()
        if draft:
            content += draft.markdown
            content += f"\n\n---\n*Draft version - Not yet approved*\n"
        else:
            content += "*No show notes available.*\n"
    
    return content


# =============================================================================
# CSV EXPORT
# =============================================================================

def export_clips_csv(episode: Episode) -> str:
    """
    Export clip moments as CSV.
    
    Args:
        episode: The episode to export clips for
    
    Returns:
        str: CSV content
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'ID',
        'Title',
        'Start (ms)',
        'End (ms)',
        'Start (formatted)',
        'End (formatted)',
        'Duration (ms)',
        'Hook',
        'Caption Draft',
        'Priority',
        'Tags',
    ])
    
    # Data rows
    clips = episode.clip_moments.all().order_by('start_ms')
    for clip in clips:
        writer.writerow([
            str(clip.id),
            clip.title,
            clip.start_ms,
            clip.end_ms,
            clip.start_formatted,
            clip.end_formatted,
            clip.duration_ms,
            clip.hook,
            clip.caption_draft,
            clip.priority,
            '|'.join(clip.tags) if clip.tags else '',
        ])
    
    return output.getvalue()


def export_segments_csv(episode: Episode) -> str:
    """
    Export segments (run of show) as CSV.
    
    Args:
        episode: The episode to export segments for
    
    Returns:
        str: CSV content
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'Order',
        'Title',
        'Purpose',
        'Duration (min)',
        'Owner',
        'Key Questions',
        'Bullet Prompts',
    ])
    
    # Data rows
    segments = episode.segments.all().order_by('order')
    for seg in segments:
        writer.writerow([
            seg.order,
            seg.title,
            seg.purpose,
            seg.timebox_minutes,
            seg.owner_role,
            seg.key_questions,
            seg.bullet_prompts,
        ])
    
    return output.getvalue()


# =============================================================================
# GUEST BRIEF EXPORT
# =============================================================================

def export_guest_brief_html(
    episode: Episode,
    guest: Guest,
) -> str:
    """
    Export a printable guest brief as HTML.
    
    Args:
        episode: The episode
        guest: The guest to generate brief for
    
    Returns:
        str: HTML content
    """
    # Try to use template if available
    try:
        return render_to_string('production_ledger/exports/guest_brief.html', {
            'episode': episode,
            'guest': guest,
            'episode_guest': episode.episode_guests.filter(guest=guest).first(),
            'segments': episode.segments.all().order_by('order'),
            'generated_at': timezone.now(),
        })
    except Exception:
        # Fallback to inline HTML
        pass
    
    # Get episode-guest relationship
    episode_guest = episode.episode_guests.filter(guest=guest).first()
    segments = episode.segments.all().order_by('order')
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Guest Brief: {episode.title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 40px auto;
            padding: 20px;
            line-height: 1.6;
            color: #333;
        }}
        h1 {{ color: #1a1a1a; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #444; margin-top: 30px; }}
        .meta {{ color: #666; font-size: 0.9em; }}
        .section {{ margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 5px; }}
        .segment {{ margin: 10px 0; padding: 10px; background: white; border-left: 3px solid #007bff; }}
        .segment-title {{ font-weight: bold; }}
        .segment-meta {{ color: #666; font-size: 0.85em; }}
        .warning {{ background: #fff3cd; padding: 10px; border-radius: 5px; }}
        .topics {{ background: #d4edda; padding: 10px; border-radius: 5px; }}
        ul {{ padding-left: 20px; }}
        @media print {{
            body {{ margin: 0; padding: 20px; }}
            .no-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <h1>Guest Brief</h1>
    <p class="meta">Generated: {timezone.now().strftime('%B %d, %Y at %I:%M %p')}</p>
    
    <div class="section">
        <h2>Episode Information</h2>
        <p><strong>Show:</strong> {episode.show.name}</p>
        <p><strong>Episode:</strong> {episode.title}</p>
        <p><strong>Type:</strong> {episode.get_episode_type_display()}</p>
        <p><strong>Format:</strong> {episode.get_recording_context_display()}</p>
        <p><strong>Target Duration:</strong> {episode.target_minutes} minutes</p>
        {"<p><strong>Scheduled:</strong> " + episode.scheduled_for.strftime('%B %d, %Y at %I:%M %p') + "</p>" if episode.scheduled_for else ""}
    </div>
    
    <div class="section">
        <h2>About You (as we have it)</h2>
        <p><strong>Name:</strong> {guest.name}</p>
        {"<p><strong>Title:</strong> " + guest.title + "</p>" if guest.title else ""}
        {"<p><strong>Organization:</strong> " + guest.org + "</p>" if guest.org else ""}
        {"<p><strong>Bio:</strong> " + guest.bio + "</p>" if guest.bio else ""}
    </div>
"""
    
    if episode_guest:
        if episode_guest.key_topics:
            html += f"""
    <div class="section topics">
        <h2>Key Topics We'll Cover</h2>
        <p>{episode_guest.key_topics}</p>
    </div>
"""
        
        if episode_guest.no_go_topics:
            html += f"""
    <div class="section warning">
        <h2>Topics to Avoid</h2>
        <p>{episode_guest.no_go_topics}</p>
    </div>
"""
        
        if episode_guest.prep_notes:
            html += f"""
    <div class="section">
        <h2>Preparation Notes</h2>
        <p>{episode_guest.prep_notes}</p>
    </div>
"""
    
    if segments:
        html += """
    <div class="section">
        <h2>Run of Show</h2>
        <p>Here's our planned structure (times are approximate):</p>
"""
        cumulative_time = 0
        for seg in segments:
            html += f"""
        <div class="segment">
            <div class="segment-title">{seg.order}. {seg.title}</div>
            <div class="segment-meta">~{cumulative_time}-{cumulative_time + seg.timebox_minutes} min | {seg.timebox_minutes} min | Led by {seg.get_owner_role_display()}</div>
            {"<p>" + seg.purpose + "</p>" if seg.purpose else ""}
        </div>
"""
            cumulative_time += seg.timebox_minutes
        html += "    </div>\n"
    
    html += f"""
    <div class="section">
        <h2>What to Expect</h2>
        <ul>
            <li>Recording will be approximately {episode.target_minutes} minutes</li>
            <li>We'll do a quick tech check before we start</li>
            <li>Feel free to ask us to re-phrase any question</li>
            <li>We'll edit out any stumbles, so don't worry about being perfect</li>
            <li>Have water nearby!</li>
        </ul>
    </div>
    
    <div class="section">
        <h2>Contact</h2>
        <p>If you have questions before the recording, reach out to our production team.</p>
    </div>
    
    <p class="meta no-print">
        <em>This brief was generated automatically. Please review and contact us with any corrections.</em>
    </p>
</body>
</html>
"""
    
    return html


# =============================================================================
# FULL PACKAGE EXPORT
# =============================================================================

def generate_full_export_package(episode: Episode) -> dict:
    """
    Generate a complete export package with all formats.
    
    Args:
        episode: The episode to export
    
    Returns:
        dict with keys: json, markdown, clips_csv, segments_csv, guest_briefs
    """
    package = {
        'json': export_episode_package_json_string(episode),
        'markdown': export_show_notes_markdown(episode),
        'clips_csv': export_clips_csv(episode),
        'segments_csv': export_segments_csv(episode),
        'guest_briefs': {},
    }
    
    # Generate guest briefs
    for eg in episode.episode_guests.select_related('guest').all():
        package['guest_briefs'][str(eg.guest.id)] = {
            'guest_name': eg.guest.name,
            'html': export_guest_brief_html(episode, eg.guest),
        }
    
    return package
