"""
Tests for Splice services: local_engine, media, render_plan.
"""
import hashlib
import os
import tempfile
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError

from production_ledger.models import Show, Episode, MediaAsset
from splice.models import (
    EditorProject, LocalEngineInstallation, LocalEngineSession,
    MediaLocation, MediaFingerprint, RenderPlan
)
from splice.services.local_engine import LocalEngineService
from splice.services.media import MediaService
from splice.services.render_plan import RenderPlanService


class LocalEngineServiceTest(TestCase):
    """Tests for LocalEngineService."""

    def setUp(self):
        self.org_uuid = uuid.uuid4()

    def test_register_engine_success(self):
        """Engine registration creates installation and returns one-time key."""
        engine, reg_key = LocalEngineService.register_engine(
            org_uuid=self.org_uuid,
            engine_name='My Engine',
            platform='macos'
        )

        self.assertIsNotNone(engine.id)
        self.assertEqual(engine.engine_name, 'My Engine')
        self.assertEqual(engine.platform, 'macos')
        self.assertFalse(engine.is_online)
        self.assertIsNotNone(reg_key)
        # Key should not be stored plaintext
        self.assertNotEqual(reg_key, engine.registration_key_hash)

    def test_register_engine_invalid_platform(self):
        """Invalid platform raises ValidationError."""
        with self.assertRaises(ValidationError):
            LocalEngineService.register_engine(
                org_uuid=self.org_uuid,
                engine_name='My Engine',
                platform='invalid'
            )

    def test_register_engine_duplicate_name(self):
        """Duplicate engine name in same org raises ValidationError."""
        LocalEngineService.register_engine(
            org_uuid=self.org_uuid,
            engine_name='My Engine',
            platform='macos'
        )

        with self.assertRaises(ValidationError):
            LocalEngineService.register_engine(
                org_uuid=self.org_uuid,
                engine_name='My Engine',
                platform='windows'
            )

    def test_create_session(self):
        """Session creation with correct token and expiration."""
        engine, _ = LocalEngineService.register_engine(
            org_uuid=self.org_uuid,
            engine_name='My Engine',
            platform='macos'
        )

        session = LocalEngineService.create_session(
            local_engine_id=engine.id,
            browser_origin='http://localhost:3000',
            expires_in_minutes=60
        )

        self.assertIsNotNone(session.session_token)
        self.assertEqual(session.browser_origin, 'http://localhost:3000')
        self.assertIsNotNone(session.expires_at)

    def test_validate_session_success(self):
        """Valid session returns engine."""
        engine, _ = LocalEngineService.register_engine(
            org_uuid=self.org_uuid,
            engine_name='My Engine',
            platform='macos'
        )

        session = LocalEngineService.create_session(
            local_engine_id=engine.id,
            browser_origin='http://localhost:3000'
        )

        validated_engine = LocalEngineService.validate_session(
            session_token=session.session_token,
            browser_origin='http://localhost:3000'
        )

        self.assertEqual(validated_engine.id, engine.id)

    def test_validate_session_expired(self):
        """Expired session returns None."""
        engine, _ = LocalEngineService.register_engine(
            org_uuid=self.org_uuid,
            engine_name='My Engine',
            platform='macos'
        )

        session = LocalEngineService.create_session(
            local_engine_id=engine.id,
            browser_origin='http://localhost:3000',
            expires_in_minutes=1
        )

        # Manually expire the session
        session.expires_at = timezone.now() - timedelta(minutes=1)
        session.save()

        validated_engine = LocalEngineService.validate_session(
            session_token=session.session_token,
            browser_origin='http://localhost:3000'
        )

        self.assertIsNone(validated_engine)

    def test_validate_session_wrong_origin(self):
        """Session with wrong origin returns None."""
        engine, _ = LocalEngineService.register_engine(
            org_uuid=self.org_uuid,
            engine_name='My Engine',
            platform='macos'
        )

        session = LocalEngineService.create_session(
            local_engine_id=engine.id,
            browser_origin='http://localhost:3000'
        )

        validated_engine = LocalEngineService.validate_session(
            session_token=session.session_token,
            browser_origin='http://different-origin:3000'
        )

        self.assertIsNone(validated_engine)

    def test_heartbeat(self):
        """Heartbeat updates last_heartbeat and is_online."""
        engine, _ = LocalEngineService.register_engine(
            org_uuid=self.org_uuid,
            engine_name='My Engine',
            platform='macos'
        )

        result = LocalEngineService.heartbeat(engine.id)
        self.assertTrue(result)

        engine.refresh_from_db()
        self.assertTrue(engine.is_online)
        self.assertIsNotNone(engine.last_heartbeat)

    def test_cleanup_expired_sessions(self):
        """Cleanup removes sessions older than threshold."""
        engine, _ = LocalEngineService.register_engine(
            org_uuid=self.org_uuid,
            engine_name='My Engine',
            platform='macos'
        )

        # Create a session that expires soon
        session = LocalEngineService.create_session(
            local_engine_id=engine.id,
            browser_origin='http://localhost:3000',
            expires_in_minutes=1
        )

        # Manually set it to 8 days ago (beyond cleanup threshold)
        session.expires_at = timezone.now() - timedelta(days=8)
        session.save()

        count = LocalEngineService.cleanup_expired_sessions(older_than_days=7)
        self.assertEqual(count, 1)


class MediaServiceTest(TestCase):
    """Tests for MediaService."""

    def setUp(self):
        self.org_uuid = uuid.uuid4()
        self.show = Show.objects.create(
            title='Test Show',
            organization_uuid=self.org_uuid,
        )
        self.episode = Episode.objects.create(
            title='Test Episode',
            show=self.show,
            organization_uuid=self.org_uuid,
        )
        self.asset = MediaAsset.objects.create(
            episode=self.episode,
            filename='test.mp4',
            organization_uuid=self.org_uuid,
        )

    def test_create_location(self):
        """Location creation with valid type and details."""
        location = MediaService.create_location(
            asset_id=self.asset.id,
            location_type='local_device',
            details={
                'local_engine_id': str(uuid.uuid4()),
                'local_location_id': 'opaque_ref_123',
            }
        )

        self.assertIsNotNone(location.id)
        self.assertEqual(location.location_type, 'local_device')
        self.assertEqual(location.availability, 'available')

    def test_create_location_invalid_type(self):
        """Invalid location_type raises ValidationError."""
        with self.assertRaises(ValidationError):
            MediaService.create_location(
                asset_id=self.asset.id,
                location_type='invalid_type',
                details={}
            )

    def test_get_location_for_asset(self):
        """Get location returns best available location."""
        # Create cloud location
        MediaService.create_location(
            asset_id=self.asset.id,
            location_type='cloud_original',
            details={'cloud_path': 's3://bucket/file.mp4'}
        )

        # Create local location
        local_location = MediaService.create_location(
            asset_id=self.asset.id,
            location_type='local_device',
            details={
                'local_engine_id': str(uuid.uuid4()),
                'local_location_id': 'opaque_ref',
            }
        )

        # Should prefer local_device
        location = MediaService.get_location_for_asset(self.asset.id)
        self.assertEqual(location.id, local_location.id)

    @patch('splice.services.media.subprocess.run')
    def test_probe_media_success(self, mock_run):
        """ffprobe returns media metadata."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"format": {"duration": "60.0", "size": "1000000"}, "streams": []}'
        )

        with tempfile.NamedTemporaryFile(suffix='.mp4') as f:
            result = MediaService.probe_media(f.name)

            self.assertEqual(result['duration_ms'], 60000)
            self.assertEqual(result['file_size'], 1000000)

    def test_compute_fingerprints(self):
        """Fingerprint computation returns all hash types."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            # Write test data
            test_data = b'test data' * 1000
            f.write(test_data)
            f.flush()

            try:
                hashes = MediaService.compute_fingerprints(f.name)

                self.assertIn('first_chunk_hash', hashes)
                self.assertIn('last_chunk_hash', hashes)
                self.assertIn('partial_hash', hashes)
                self.assertIn('full_hash', hashes)

                # All should be valid SHA256 hashes
                for key, hash_val in hashes.items():
                    self.assertEqual(len(hash_val), 64)  # SHA256 hex length
            finally:
                os.unlink(f.name)

    def test_match_fingerprints_success(self):
        """Matching fingerprints returns True."""
        probe = {
            'file_size': 1000000,
            'duration_ms': 60000,
            'codec_metadata': {'video': {'name': 'h264'}},
        }

        existing_fp = MediaFingerprint(
            file_size=1000000,
            duration_ms=60000,
            codec_metadata={'video': {'name': 'h264'}},
            partial_hash='abc123',
            full_hash='def456',
        )

        hashes = {
            'partial_hash': 'abc123',
            'full_hash': 'def456',
        }

        result = MediaService.match_fingerprints(probe, hashes, existing_fp)
        self.assertTrue(result)

    def test_match_fingerprints_size_mismatch(self):
        """Mismatched file size returns False."""
        probe = {
            'file_size': 2000000,  # Different
            'duration_ms': 60000,
            'codec_metadata': {'video': {'name': 'h264'}},
        }

        existing_fp = MediaFingerprint(
            file_size=1000000,
            duration_ms=60000,
            codec_metadata={'video': {'name': 'h264'}},
        )

        hashes = {}

        result = MediaService.match_fingerprints(probe, hashes, existing_fp)
        self.assertFalse(result)


class RenderPlanServiceTest(TestCase):
    """Tests for RenderPlanService."""

    def setUp(self):
        self.org_uuid = uuid.uuid4()
        self.show = Show.objects.create(
            title='Test Show',
            organization_uuid=self.org_uuid,
        )
        self.episode = Episode.objects.create(
            title='Test Episode',
            show=self.show,
            organization_uuid=self.org_uuid,
        )
        self.project = EditorProject.objects.create(
            episode=self.episode,
            organization_uuid=self.org_uuid,
        )

    def test_create_render_plan(self):
        """Render plan creation captures project state."""
        plan = RenderPlanService.create_render_plan(
            project_id=self.project.id,
            revision=1
        )

        self.assertIsNotNone(plan.id)
        self.assertEqual(plan.revision, 1)
        self.assertEqual(plan.canvas_width, self.project.canvas_width)
        self.assertEqual(plan.canvas_height, self.project.canvas_height)
        self.assertEqual(plan.frame_rate, self.project.frame_rate)

    def test_validate_render_plan_invalid_canvas(self):
        """Invalid canvas dimensions raise ValidationError."""
        plan = RenderPlanService.create_render_plan(
            project_id=self.project.id,
            revision=1
        )

        # Manually set invalid dimensions
        plan.canvas_width = 100  # Too small
        plan.save()

        with self.assertRaises(ValidationError):
            RenderPlanService.validate_render_plan(plan.id)

    def test_is_plan_deterministic(self):
        """Identical plans are deterministic."""
        plan1 = RenderPlanService.create_render_plan(
            project_id=self.project.id,
            revision=1
        )

        plan2 = RenderPlanService.create_render_plan(
            project_id=self.project.id,
            revision=1
        )

        result = RenderPlanService.is_plan_deterministic(plan1.id, plan2.id)
        self.assertTrue(result)

    def test_plan_to_ffmpeg_blueprint(self):
        """FFmpeg blueprint generation succeeds."""
        plan = RenderPlanService.create_render_plan(
            project_id=self.project.id,
            revision=1
        )

        blueprint = RenderPlanService.plan_to_ffmpeg_blueprint(plan.id)

        self.assertIn('inputs', blueprint)
        self.assertIn('filter_complex', blueprint)
        self.assertIn('outputs', blueprint)
        self.assertIn('metadata', blueprint)

        # Should have no absolute paths
        blueprint_str = str(blueprint)
        self.assertNotIn('/Users', blueprint_str)
        self.assertNotIn('C:', blueprint_str)
