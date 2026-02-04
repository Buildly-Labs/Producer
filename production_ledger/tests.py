"""
Tests for production_ledger app.

These tests cover:
- Model creation and relationships
- Permission system (RBAC)
- Status transitions
- AI artifact approval workflow
"""
import uuid
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from unittest.mock import MagicMock, patch

from .models import (
    Show, Episode, Segment, Guest, EpisodeGuest, MediaAsset,
    Transcript, ClipMoment, AIArtifact, ShowNoteDraft, ShowNoteFinal,
    ChecklistItem, ExportRecord, ShowRoleAssignment, EpisodeRoleOverride
)
from .constants import EpisodeStatus, Role, ApprovalStatus, ArtifactType
from .permissions import (
    get_user_role_for_show, has_role, has_minimum_role,
    can_approve_artifact, can_finalize_show_notes
)
from .services.ai import generate_show_notes, generate_questions


User = get_user_model()


class ModelCreationTests(TestCase):
    """Test that all models can be created properly."""
    
    def setUp(self):
        self.org_uuid = uuid.uuid4()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_show_creation(self):
        """Show model can be created with required fields."""
        show = Show.objects.create(
            organization_uuid=self.org_uuid,
            name='Test Podcast',
            slug='test-podcast',
            created_by=self.user
        )
        self.assertEqual(show.name, 'Test Podcast')
        self.assertIsNotNone(show.pk)
        self.assertEqual(str(show), 'Test Podcast')
    
    def test_episode_creation(self):
        """Episode model can be created with show relationship."""
        show = Show.objects.create(
            organization_uuid=self.org_uuid,
            name='Test Podcast',
            slug='test-podcast',
            created_by=self.user
        )
        episode = Episode.objects.create(
            organization_uuid=self.org_uuid,
            show=show,
            title='Episode 1: Introduction',
            status=EpisodeStatus.DRAFT,
            created_by=self.user
        )
        self.assertEqual(episode.show, show)
        self.assertEqual(episode.status, EpisodeStatus.DRAFT)
        self.assertIn(episode, show.episodes.all())
    
    def test_guest_creation(self):
        """Guest model can be created with contact info."""
        guest = Guest.objects.create(
            organization_uuid=self.org_uuid,
            name='Jane Doe',
            email='jane@example.com',
            org='Acme Corp',
            title='CEO',
            created_by=self.user
        )
        self.assertEqual(guest.name, 'Jane Doe')
        self.assertEqual(guest.email, 'jane@example.com')
    
    def test_episode_guest_relationship(self):
        """EpisodeGuest links episodes and guests correctly."""
        show = Show.objects.create(
            organization_uuid=self.org_uuid,
            name='Test Podcast',
            slug='test-podcast',
            created_by=self.user
        )
        episode = Episode.objects.create(
            organization_uuid=self.org_uuid,
            show=show,
            title='Episode 1',
            created_by=self.user
        )
        guest = Guest.objects.create(
            organization_uuid=self.org_uuid,
            name='Jane Doe',
            created_by=self.user
        )
        eg = EpisodeGuest.objects.create(
            organization_uuid=self.org_uuid,
            episode=episode,
            guest=guest,
            role='primary',
            created_by=self.user
        )
        self.assertEqual(eg.episode, episode)
        self.assertEqual(eg.guest, guest)
        self.assertIn(guest, episode.guests.all())
    
    def test_ai_artifact_creation(self):
        """AIArtifact can be created with provenance info."""
        show = Show.objects.create(
            organization_uuid=self.org_uuid,
            name='Test Podcast',
            slug='test-podcast',
            created_by=self.user
        )
        episode = Episode.objects.create(
            organization_uuid=self.org_uuid,
            show=show,
            title='Episode 1',
            created_by=self.user
        )
        artifact = AIArtifact.objects.create(
            organization_uuid=self.org_uuid,
            episode=episode,
            artifact_type=ArtifactType.SHOW_NOTES,
            prompt_text='Generate show notes',
            output_text='These are the show notes...',
            provider='mock',
            model='mock-v1',
            created_by=self.user
        )
        self.assertEqual(artifact.approval_status, ApprovalStatus.PENDING)
        self.assertEqual(artifact.provider, 'mock')


class StatusTransitionTests(TestCase):
    """Test episode status workflow transitions."""
    
    def setUp(self):
        self.org_uuid = uuid.uuid4()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.show = Show.objects.create(
            organization_uuid=self.org_uuid,
            name='Test Podcast',
            slug='test-podcast',
            created_by=self.user
        )
        self.episode = Episode.objects.create(
            organization_uuid=self.org_uuid,
            show=self.show,
            title='Episode 1',
            status=EpisodeStatus.DRAFT,
            created_by=self.user
        )
    
    def test_valid_transition_draft_to_planned(self):
        """Valid transition from draft to planned succeeds."""
        success, msg = self.episode.transition_to(EpisodeStatus.PLANNED, self.user)
        self.assertTrue(success)
        self.assertEqual(self.episode.status, EpisodeStatus.PLANNED)
    
    def test_valid_transition_sequence(self):
        """Episode can follow the normal workflow sequence."""
        transitions = [
            EpisodeStatus.PLANNED,
            EpisodeStatus.SCHEDULED,
            EpisodeStatus.RECORDED,
            EpisodeStatus.INGESTED,
            EpisodeStatus.TRANSCRIBED,
            EpisodeStatus.EDITED,
        ]
        for new_status in transitions:
            success, msg = self.episode.transition_to(new_status, self.user)
            self.assertTrue(success, f"Failed transition to {new_status}: {msg}")
            self.assertEqual(self.episode.status, new_status)
    
    def test_invalid_transition_blocked(self):
        """Invalid status transition is blocked."""
        # Cannot go directly from draft to published
        success, msg = self.episode.transition_to(EpisodeStatus.PUBLISHED, self.user)
        self.assertFalse(success)
        self.assertEqual(self.episode.status, EpisodeStatus.DRAFT)
    
    def test_approved_requires_checklist(self):
        """Transition to approved requires checklist completion."""
        # Progress episode to edited
        for status in [EpisodeStatus.PLANNED, EpisodeStatus.SCHEDULED, 
                      EpisodeStatus.RECORDED, EpisodeStatus.INGESTED,
                      EpisodeStatus.TRANSCRIBED, EpisodeStatus.EDITED]:
            self.episode.transition_to(status, self.user)
        
        # Create a required checklist item that's not done
        ChecklistItem.objects.create(
            organization_uuid=self.org_uuid,
            episode=self.episode,
            title='Review show notes',
            is_required=True,
            is_done=False,
            created_by=self.user
        )
        
        # Should fail because checklist is incomplete
        success, msg = self.episode.transition_to(EpisodeStatus.APPROVED, self.user)
        self.assertFalse(success)
        self.assertIn('checklist', msg.lower())


class PermissionTests(TestCase):
    """Test RBAC permission system."""
    
    def setUp(self):
        self.org_uuid = uuid.uuid4()
        self.admin_user = User.objects.create_user(
            username='admin', email='admin@example.com', password='pass'
        )
        self.host_user = User.objects.create_user(
            username='host', email='host@example.com', password='pass'
        )
        self.guest_user = User.objects.create_user(
            username='guest', email='guest@example.com', password='pass'
        )
        self.show = Show.objects.create(
            organization_uuid=self.org_uuid,
            name='Test Podcast',
            slug='test-podcast',
            created_by=self.admin_user
        )
        # Assign roles
        ShowRoleAssignment.objects.create(
            organization_uuid=self.org_uuid,
            show=self.show,
            user=self.admin_user,
            role=Role.ADMIN,
            created_by=self.admin_user
        )
        ShowRoleAssignment.objects.create(
            organization_uuid=self.org_uuid,
            show=self.show,
            user=self.host_user,
            role=Role.HOST,
            created_by=self.admin_user
        )
        ShowRoleAssignment.objects.create(
            organization_uuid=self.org_uuid,
            show=self.show,
            user=self.guest_user,
            role=Role.GUEST,
            created_by=self.admin_user
        )
    
    def test_get_user_role_for_show(self):
        """User roles are correctly retrieved for shows."""
        self.assertEqual(get_user_role_for_show(self.admin_user, self.show), Role.ADMIN)
        self.assertEqual(get_user_role_for_show(self.host_user, self.show), Role.HOST)
        self.assertEqual(get_user_role_for_show(self.guest_user, self.show), Role.GUEST)
    
    def test_has_role(self):
        """has_role correctly checks for specific roles."""
        self.assertTrue(has_role(self.admin_user, self.show, Role.ADMIN))
        self.assertFalse(has_role(self.host_user, self.show, Role.ADMIN))
        self.assertTrue(has_role(self.host_user, self.show, Role.HOST))
    
    def test_has_minimum_role(self):
        """has_minimum_role checks role hierarchy correctly."""
        # Admin has minimum of any role
        self.assertTrue(has_minimum_role(self.admin_user, self.show, Role.GUEST))
        self.assertTrue(has_minimum_role(self.admin_user, self.show, Role.ADMIN))
        
        # Guest only has minimum of guest
        self.assertTrue(has_minimum_role(self.guest_user, self.show, Role.GUEST))
        self.assertFalse(has_minimum_role(self.guest_user, self.show, Role.EDITOR))
    
    def test_can_approve_artifact(self):
        """Only admin/host/producer can approve artifacts."""
        episode = Episode.objects.create(
            organization_uuid=self.org_uuid,
            show=self.show,
            title='Episode 1',
            created_by=self.admin_user
        )
        self.assertTrue(can_approve_artifact(self.admin_user, episode))
        self.assertTrue(can_approve_artifact(self.host_user, episode))
        self.assertFalse(can_approve_artifact(self.guest_user, episode))


class AIArtifactApprovalTests(TestCase):
    """Test AI artifact approval workflow."""
    
    def setUp(self):
        self.org_uuid = uuid.uuid4()
        self.user = User.objects.create_user(
            username='testuser', email='test@example.com', password='pass'
        )
        self.show = Show.objects.create(
            organization_uuid=self.org_uuid,
            name='Test Podcast',
            slug='test-podcast',
            created_by=self.user
        )
        self.episode = Episode.objects.create(
            organization_uuid=self.org_uuid,
            show=self.show,
            title='Episode 1',
            created_by=self.user
        )
        self.artifact = AIArtifact.objects.create(
            organization_uuid=self.org_uuid,
            episode=self.episode,
            artifact_type=ArtifactType.SHOW_NOTES,
            prompt_text='Generate show notes',
            output_text='AI generated content here',
            provider='mock',
            model='mock-v1',
            created_by=self.user
        )
    
    def test_artifact_starts_pending(self):
        """New artifacts start with pending status."""
        self.assertEqual(self.artifact.approval_status, ApprovalStatus.PENDING)
        self.assertIsNone(self.artifact.approved_by)
    
    def test_approve_artifact(self):
        """Artifact can be approved."""
        self.artifact.approve(self.user, notes='Looks good!')
        self.assertEqual(self.artifact.approval_status, ApprovalStatus.APPROVED)
        self.assertEqual(self.artifact.approved_by, self.user)
        self.assertIsNotNone(self.artifact.approved_at)
        self.assertEqual(self.artifact.notes, 'Looks good!')
    
    def test_reject_artifact(self):
        """Artifact can be rejected."""
        self.artifact.reject(self.user, notes='Needs revision')
        self.assertEqual(self.artifact.approval_status, ApprovalStatus.REJECTED)
        self.assertEqual(self.artifact.approved_by, self.user)
        self.assertEqual(self.artifact.notes, 'Needs revision')


class AIServiceTests(TestCase):
    """Test AI service layer (mock provider)."""
    
    def setUp(self):
        self.org_uuid = uuid.uuid4()
        self.user = User.objects.create_user(
            username='testuser', email='test@example.com', password='pass'
        )
        self.show = Show.objects.create(
            organization_uuid=self.org_uuid,
            name='Test Podcast',
            slug='test-podcast',
            created_by=self.user
        )
        self.episode = Episode.objects.create(
            organization_uuid=self.org_uuid,
            show=self.show,
            title='Episode 1',
            created_by=self.user
        )
    
    def test_generate_show_notes_creates_artifact(self):
        """generate_show_notes creates an AIArtifact."""
        artifact = generate_show_notes(
            episode=self.episode,
            user=self.user,
            topic_hint='Startup culture'
        )
        self.assertIsNotNone(artifact)
        self.assertEqual(artifact.artifact_type, ArtifactType.SHOW_NOTES)
        self.assertEqual(artifact.episode, self.episode)
        self.assertIn('show notes', artifact.output_text.lower())
    
    def test_generate_questions_creates_artifact(self):
        """generate_questions creates an AIArtifact."""
        artifact = generate_questions(
            episode=self.episode,
            user=self.user,
            guest_context='CEO of a tech startup'
        )
        self.assertIsNotNone(artifact)
        self.assertEqual(artifact.artifact_type, ArtifactType.QUESTIONS)


class ChecklistTests(TestCase):
    """Test checklist functionality."""
    
    def setUp(self):
        self.org_uuid = uuid.uuid4()
        self.user = User.objects.create_user(
            username='testuser', email='test@example.com', password='pass'
        )
        self.show = Show.objects.create(
            organization_uuid=self.org_uuid,
            name='Test Podcast',
            slug='test-podcast',
            created_by=self.user
        )
    
    def test_checklist_auto_seeded_on_episode_creation(self):
        """Checklist items are auto-created when episode is created."""
        episode = Episode.objects.create(
            organization_uuid=self.org_uuid,
            show=self.show,
            title='Episode 1',
            created_by=self.user
        )
        # Should have default checklist items
        self.assertTrue(episode.checklist_items.exists())
    
    def test_is_checklist_complete(self):
        """is_checklist_complete returns correct status."""
        episode = Episode.objects.create(
            organization_uuid=self.org_uuid,
            show=self.show,
            title='Episode 1',
            created_by=self.user
        )
        # Clear auto-created items
        episode.checklist_items.all().delete()
        
        # Create required item (not done)
        item = ChecklistItem.objects.create(
            organization_uuid=self.org_uuid,
            episode=episode,
            title='Required Task',
            is_required=True,
            is_done=False,
            created_by=self.user
        )
        self.assertFalse(episode.is_checklist_complete())
        
        # Mark as done
        item.is_done = True
        item.done_by = self.user
        item.save()
        self.assertTrue(episode.is_checklist_complete())
