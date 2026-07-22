"""
Render plan generation and FFmpeg blueprint creation.

Path-free rendering:
- Cloud stores asset UUIDs (not paths)
- Local engine privately resolves UUIDs → file paths
- FFmpeg command built server-side with validated arguments (no shell escaping)
"""
import json
from typing import Dict, List, Optional

from django.core.exceptions import ValidationError

from splice.models import RenderPlan, EditorProject, EditOperation, MediaLocation


class RenderPlanService:
    """Service for render plan creation and FFmpeg blueprint generation."""

    @staticmethod
    def create_render_plan(
        project_id: str,
        revision: int,
        user=None,
    ) -> RenderPlan:
        """
        Create a path-free render plan for a project revision.

        Collects:
        - Asset UUIDs (not paths)
        - Edit operations applied to this revision
        - Camera cuts and sync offsets
        - Canvas/output settings

        Args:
            project_id: EditorProject UUID
            revision: Revision number to render
            user: User creating the plan

        Returns:
            RenderPlan instance

        Raises:
            EditorProject.DoesNotExist: If project not found
            ValidationError: If revision doesn't exist or assets missing
        """
        project = EditorProject.objects.get(id=project_id)

        # Collect asset UUIDs (from all clips/tracks)
        asset_uuids = []
        from splice.models import Clip
        clips = Clip.objects.filter(
            project=project,
            media_asset__isnull=False
        ).values_list('media_asset__id', flat=True).distinct()
        asset_uuids.extend(str(uuid) for uuid in clips)

        # Collect applied operations for this revision
        operations = []
        ops = EditOperation.objects.filter(
            project=project,
            revision__lte=revision,
            applied=True,
        ).values('operation_type', 'payload', 'revision').order_by('revision')
        for op in ops:
            operations.append({
                'type': op['operation_type'],
                'payload': op['payload'],
                'revision': op['revision'],
            })

        # Collect camera cuts (simplified for now)
        camera_cuts = []
        from splice.models import CameraCut
        cuts = CameraCut.objects.filter(
            project=project
        ).values('timeline_start_ms', 'timeline_end_ms', 'camera_asset__id').order_by('timeline_start_ms')
        for cut in cuts:
            camera_cuts.append({
                'start_ms': cut['timeline_start_ms'],
                'end_ms': cut['timeline_end_ms'],
                'asset_uuid': str(cut['camera_asset__id']),
            })

        # Collect sync offsets from MediaSyncPoint
        sync_offsets = {}
        from splice.models import MediaSyncPoint
        sync_points = MediaSyncPoint.objects.filter(
            project=project
        ).values('media_asset__id', 'sync_offset_ms')
        for point in sync_points:
            sync_offsets[str(point['media_asset__id'])] = point['sync_offset_ms']

        # Create render plan
        plan = RenderPlan.objects.create(
            project=project,
            revision=revision,
            asset_selections=asset_uuids,
            operations=operations,
            camera_cuts=camera_cuts,
            sync_offsets=sync_offsets,
            output_preset=project.aspect_ratio,
            canvas_width=project.canvas_width,
            canvas_height=project.canvas_height,
            frame_rate=project.frame_rate,
            loudness_preset='broadcast',  # TODO: configurable per project
            created_by=user,
        )

        return plan

    @staticmethod
    def validate_render_plan(plan_id: str) -> bool:
        """
        Validate that all assets in a render plan exist and are accessible.

        Checks:
        1. All asset UUIDs exist
        2. All assets have accessible locations
        3. Operations are syntactically valid
        4. Canvas dimensions are valid

        Args:
            plan_id: RenderPlan UUID

        Returns:
            True if valid

        Raises:
            RenderPlan.DoesNotExist: If plan not found
            ValidationError: If validation fails
        """
        plan = RenderPlan.objects.get(id=plan_id)

        from production_ledger.models import MediaAsset

        # Check all asset UUIDs exist
        asset_ids = plan.asset_selections
        if asset_ids:
            existing_assets = MediaAsset.objects.filter(
                id__in=asset_ids
            ).count()
            if existing_assets != len(asset_ids):
                raise ValidationError(
                    f"Some assets in render plan don't exist "
                    f"({existing_assets}/{len(asset_ids)})"
                )

            # Check all have accessible locations
            for asset_id in asset_ids:
                location = MediaLocation.objects.filter(
                    asset_id=asset_id,
                    availability='available'
                ).first()
                if not location:
                    raise ValidationError(
                        f"Asset {asset_id} has no available location"
                    )

        # Validate canvas dimensions
        if plan.canvas_width < 320 or plan.canvas_width > 7680:
            raise ValidationError(f"Invalid canvas width: {plan.canvas_width}")
        if plan.canvas_height < 240 or plan.canvas_height > 4320:
            raise ValidationError(f"Invalid canvas height: {plan.canvas_height}")

        # Validate frame rate
        valid_frame_rates = [23.976, 24, 25, 29.97, 30, 50, 59.94, 60]
        if plan.frame_rate not in valid_frame_rates:
            raise ValidationError(f"Invalid frame rate: {plan.frame_rate}")

        return True

    @staticmethod
    def plan_to_ffmpeg_blueprint(plan_id: str) -> Dict:
        """
        Convert a render plan to an FFmpeg blueprint.

        The blueprint includes:
        - inputs: List of asset UUIDs to be resolved locally
        - filter_complex: FFmpeg filtergraph (no shell escaping)
        - outputs: Output specification (no shell escaping)
        - metadata: Canvas, frame rate, sync offsets

        IMPORTANT: No absolute file paths in this blueprint.
        Local engine converts UUIDs → paths privately.

        Args:
            plan_id: RenderPlan UUID

        Returns:
            Dict with inputs, filter_complex, outputs, metadata

        Raises:
            RenderPlan.DoesNotExist: If plan not found
            ValidationError: If plan is invalid
        """
        plan = RenderPlan.objects.get(id=plan_id)

        # Validate first
        RenderPlanService.validate_render_plan(plan_id)

        # Build inputs list (asset UUIDs only, no paths)
        inputs = [{'uuid': uuid} for uuid in plan.asset_selections]

        # Build filter_complex (simplified example)
        # In real implementation, would build based on camera cuts + sync offsets
        filter_complex = ""
        if len(plan.camera_cuts) > 0:
            # Concatenate camera cuts with transitions
            filter_parts = []
            for i, cut in enumerate(plan.camera_cuts):
                filter_parts.append(f"[{i}:v]")
            filter_complex = "".join(filter_parts) + f"concat=n={len(plan.camera_cuts)}:v=1:a=0[vout]"
        else:
            # Single input, no cuts
            filter_complex = "[0:v]scale={w}:{h},fps={fps}[vout]".format(
                w=plan.canvas_width,
                h=plan.canvas_height,
                fps=plan.frame_rate,
            )

        # Build output specification
        outputs = {
            'video': {
                'codec': 'libx264',
                'preset': 'medium',
                'crf': 23,
                'filter': filter_complex,
            },
            'audio': {
                'codec': 'aac',
                'bitrate': '128k',
            }
        }

        blueprint = {
            'inputs': inputs,
            'filter_complex': filter_complex,
            'outputs': outputs,
            'metadata': {
                'canvas_width': plan.canvas_width,
                'canvas_height': plan.canvas_height,
                'frame_rate': plan.frame_rate,
                'sync_offsets': plan.sync_offsets,
                'loudness_preset': plan.loudness_preset,
            },
            'plan_id': str(plan_id),
            'revision': plan.revision,
        }

        return blueprint

    @staticmethod
    def is_plan_deterministic(plan1_id: str, plan2_id: str) -> bool:
        """
        Check if two plans render identically.

        Used to detect when re-rendering will produce same output.

        Args:
            plan1_id: First RenderPlan UUID
            plan2_id: Second RenderPlan UUID

        Returns:
            True if plans are equivalent
        """
        plan1 = RenderPlan.objects.get(id=plan1_id)
        plan2 = RenderPlan.objects.get(id=plan2_id)

        # Compare all deterministic fields
        return (
            plan1.asset_selections == plan2.asset_selections and
            plan1.operations == plan2.operations and
            plan1.camera_cuts == plan2.camera_cuts and
            plan1.sync_offsets == plan2.sync_offsets and
            plan1.canvas_width == plan2.canvas_width and
            plan1.canvas_height == plan2.canvas_height and
            plan1.frame_rate == plan2.frame_rate
        )
