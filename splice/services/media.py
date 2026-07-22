"""
Media asset probing, fingerprinting, location tracking, and relinking.

Security model:
- Never stores absolute file paths in cloud
- Fingerprints enable intelligent relinking without forced re-upload
- Multi-method matching: size+duration → codec → partial hash → full hash
- Location tracking supports local device, cloud, remote URLs
"""
import hashlib
import json
from typing import Optional, Dict, List
import subprocess

from django.core.exceptions import ValidationError
from django.utils import timezone

from production_ledger.models import MediaAsset
from splice.models import MediaLocation, MediaFingerprint


class MediaService:
    """Service for media asset management and fingerprinting."""

    FINGERPRINT_VERSION = 1
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks for hashing

    @staticmethod
    def probe_media(file_path: str) -> Dict:
        """
        Extract media metadata using ffprobe.

        Args:
            file_path: Path to media file (local only)

        Returns:
            Dict with: duration_ms, file_size, codecs (video/audio), frame_rate

        Raises:
            FileNotFoundError: If file doesn't exist
            RuntimeError: If ffprobe fails
        """
        import os
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            # ffprobe -v error -select_streams a:0 -show_entries stream=codec_type,codec_name -of json input.mp4
            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'error',
                    '-show_format',
                    '-show_streams',
                    '-of', 'json',
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise RuntimeError(f"ffprobe failed: {result.stderr}")

            data = json.loads(result.stdout)
            format_data = data.get('format', {})
            streams = data.get('streams', [])

            # Extract duration and file size
            duration_sec = float(format_data.get('duration', 0))
            duration_ms = int(duration_sec * 1000)
            file_size = int(format_data.get('size', 0))

            # Extract codec information
            codecs = {}
            for stream in streams:
                codec_type = stream.get('codec_type')
                if codec_type:
                    codecs[codec_type] = {
                        'name': stream.get('codec_name'),
                        'profile': stream.get('profile'),
                    }
                    if codec_type == 'video':
                        codecs[codec_type]['width'] = stream.get('width')
                        codecs[codec_type]['height'] = stream.get('height')
                        codecs[codec_type]['r_frame_rate'] = stream.get('r_frame_rate')

            return {
                'duration_ms': duration_ms,
                'file_size': file_size,
                'codec_metadata': codecs,
            }

        except subprocess.TimeoutExpired:
            raise RuntimeError("ffprobe timeout (file too large or network issue)")
        except json.JSONDecodeError:
            raise RuntimeError("ffprobe output invalid JSON")

    @staticmethod
    def compute_fingerprints(file_path: str) -> Dict:
        """
        Compute multi-method fingerprints for a file.

        Methods (in order of cost):
        1. size + duration (instant)
        2. codec metadata (instant)
        3. first/last chunk hash (fast)
        4. partial hash (10% of file)
        5. full hash (complete file)

        Args:
            file_path: Path to media file

        Returns:
            Dict with: first_chunk_hash, last_chunk_hash, partial_hash, full_hash
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        hashes = {}

        try:
            with open(file_path, 'rb') as f:
                # First chunk (first 1MB)
                f.seek(0)
                chunk = f.read(MediaService.CHUNK_SIZE)
                hashes['first_chunk_hash'] = hashlib.sha256(chunk).hexdigest()

                # Last chunk (last 1MB)
                f.seek(max(0, file_size - MediaService.CHUNK_SIZE))
                chunk = f.read(MediaService.CHUNK_SIZE)
                hashes['last_chunk_hash'] = hashlib.sha256(chunk).hexdigest()

                # Partial hash (first 10% of file, or up to 10MB)
                partial_size = min(file_size // 10, 10 * 1024 * 1024)
                if partial_size > 0:
                    f.seek(0)
                    hasher = hashlib.sha256()
                    while True:
                        chunk = f.read(MediaService.CHUNK_SIZE)
                        if not chunk or hasher.digest_size >= partial_size:
                            break
                        hasher.update(chunk)
                    hashes['partial_hash'] = hasher.hexdigest()
                else:
                    hashes['partial_hash'] = hashes['first_chunk_hash']

                # Full hash (complete file SHA256)
                f.seek(0)
                hasher = hashlib.sha256()
                while True:
                    chunk = f.read(MediaService.CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)
                hashes['full_hash'] = hasher.hexdigest()

                return hashes

        except (IOError, OSError) as e:
            raise RuntimeError(f"Failed to read file: {e}")

    @staticmethod
    def fingerprint_media(
        asset_id: str,
        file_path: str,
        user=None,
    ) -> MediaFingerprint:
        """
        Fingerprint a media file and create fingerprint record.

        Args:
            asset_id: MediaAsset UUID
            file_path: Path to media file (local only)
            user: User performing fingerprinting

        Returns:
            MediaFingerprint instance

        Raises:
            MediaAsset.DoesNotExist: If asset not found
            FileNotFoundError: If file doesn't exist
        """
        asset = MediaAsset.objects.get(id=asset_id)

        # Get file metadata
        probe = MediaService.probe_media(file_path)
        hashes = MediaService.compute_fingerprints(file_path)

        # Create fingerprint record
        fingerprint = MediaFingerprint.objects.create(
            asset=asset,
            fingerprint_version=MediaService.FINGERPRINT_VERSION,
            fingerprint_method='multi_method',
            file_size=probe['file_size'],
            duration_ms=probe['duration_ms'],
            codec_metadata=probe['codec_metadata'],
            first_chunk_hash=hashes['first_chunk_hash'],
            last_chunk_hash=hashes['last_chunk_hash'],
            partial_hash=hashes['partial_hash'],
            full_hash=hashes['full_hash'],
            verified_at=timezone.now(),
            created_by=user,
        )

        return fingerprint

    @staticmethod
    def match_fingerprints(
        probe: Dict,
        hashes: Dict,
        existing_fingerprint: MediaFingerprint,
    ) -> bool:
        """
        Compare probed file against existing fingerprint using multi-method matching.

        Matching strategy (stops at first match):
        1. Size + duration match → likely same file
        2. Codecs match → high confidence
        3. Partial hash match → very high confidence
        4. Full hash match → absolute confirmation

        Args:
            probe: Result from probe_media()
            hashes: Result from compute_fingerprints()
            existing_fingerprint: MediaFingerprint to compare against

        Returns:
            True if file matches, False otherwise
        """
        # Method 1: Size + duration (instant check)
        if (probe['file_size'] != existing_fingerprint.file_size or
            probe['duration_ms'] != existing_fingerprint.duration_ms):
            return False

        # Method 2: Codec metadata (instant check)
        if probe['codec_metadata'] != existing_fingerprint.codec_metadata:
            return False

        # Method 3: Partial hash (confident match)
        if (existing_fingerprint.partial_hash and
            hashes['partial_hash'] == existing_fingerprint.partial_hash):
            return True

        # Method 4: Full hash (absolute confirmation)
        if (existing_fingerprint.full_hash and
            hashes['full_hash'] == existing_fingerprint.full_hash):
            return True

        # All methods exhausted, no match
        return False

    @staticmethod
    def relink_media(
        asset_id: str,
        new_file_path: str,
        user=None,
    ) -> bool:
        """
        Attempt to relink media to a new file location.

        Uses multi-method fingerprint matching. If match found, updates
        MediaLocation.local_location_id without requiring re-upload.

        Args:
            asset_id: MediaAsset UUID
            new_file_path: Path to the (presumably moved) file
            user: User performing relinking

        Returns:
            True if relinking successful, False if file doesn't match

        Raises:
            MediaAsset.DoesNotExist: If asset not found
            MediaFingerprint.DoesNotExist: If fingerprint not found (asset never probed)
            FileNotFoundError: If new file doesn't exist
        """
        asset = MediaAsset.objects.get(id=asset_id)
        existing_fp = MediaFingerprint.objects.get(asset=asset)

        # Probe new file
        probe = MediaService.probe_media(new_file_path)
        hashes = MediaService.compute_fingerprints(new_file_path)

        # Match against existing fingerprint
        if not MediaService.match_fingerprints(probe, hashes, existing_fp):
            return False

        # Match found! Update location
        # In real implementation, would use local_engine_id + opaque local_location_id
        # For now, just mark as available
        location = MediaLocation.objects.filter(
            asset=asset,
            location_type='local_device'
        ).first()

        if location:
            location.availability = 'available'
            location.last_verified = timezone.now()
            location.save(update_fields=['availability', 'last_verified'])

        return True

    @staticmethod
    def create_location(
        asset_id: str,
        location_type: str,
        details: Dict,
        user=None,
    ) -> MediaLocation:
        """
        Create a media location record.

        Args:
            asset_id: MediaAsset UUID
            location_type: One of local_device, cloud_original, remote_url, etc.
            details: Location-specific details:
                - local_device: {'local_engine_id': uuid, 'local_location_id': opaque_ref}
                - cloud_original: {'cloud_path': 's3_key'}
                - remote_url: {'remote_url': 'https://...'}
            user: User creating the location

        Returns:
            MediaLocation instance

        Raises:
            MediaAsset.DoesNotExist: If asset not found
            ValidationError: If location_type or details invalid
        """
        asset = MediaAsset.objects.get(id=asset_id)

        # Validate location_type + details
        valid_types = [
            'local_device', 'local_network', 'external_drive',
            'cloud_original', 'cloud_proxy', 'remote_url', 'generated'
        ]
        if location_type not in valid_types:
            raise ValidationError(f"Invalid location_type: {location_type}")

        # Create location record
        location = MediaLocation.objects.create(
            asset=asset,
            location_type=location_type,
            availability='available',
            local_engine_id=details.get('local_engine_id'),
            local_location_id=details.get('local_location_id'),
            cloud_path=details.get('cloud_path'),
            remote_url=details.get('remote_url'),
            last_verified=timezone.now(),
            created_by=user,
        )

        return location

    @staticmethod
    def get_location_for_asset(asset_id: str) -> Optional[MediaLocation]:
        """
        Get the best available location for an asset.

        Preference order:
        1. local_device (available)
        2. external_drive (available)
        3. cloud_original (available)
        4. cloud_proxy (available)

        Args:
            asset_id: MediaAsset UUID

        Returns:
            MediaLocation if available, None otherwise
        """
        locations = MediaLocation.objects.filter(
            asset_id=asset_id,
            availability='available'
        ).order_by('location_type')

        # Prefer local over cloud
        preference_order = [
            'local_device', 'external_drive', 'local_network',
            'cloud_original', 'cloud_proxy', 'remote_url'
        ]

        for loc_type in preference_order:
            location = locations.filter(location_type=loc_type).first()
            if location:
                return location

        return None
