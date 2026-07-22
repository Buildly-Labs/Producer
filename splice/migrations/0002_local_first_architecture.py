# Generated migration: Add local-first architecture support

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('production_ledger', '0008_episode_active_segment_constraint'),
        ('splice', '0001_initial'),
    ]

    operations = [
        # Add fields to EditorProject for processing mode and render location
        migrations.AddField(
            model_name='editorproject',
            name='processing_mode',
            field=models.CharField(
                choices=[
                    ('local', 'Local Device'),
                    ('hybrid', 'Hybrid (Local + Cloud)'),
                    ('cloud', 'Cloud Only'),
                ],
                default='hybrid',
                max_length=20,
                help_text='Where media processing happens'
            ),
        ),
        migrations.AddField(
            model_name='editorproject',
            name='render_location',
            field=models.CharField(
                choices=[
                    ('local_engine', 'Local Engine'),
                    ('cloud_worker', 'Cloud Worker'),
                    ('browser_quick', 'Browser Quick Export'),
                ],
                default='local_engine',
                max_length=20,
                help_text='Where final render happens'
            ),
        ),
        migrations.AddField(
            model_name='editorproject',
            name='allow_cloud_upload',
            field=models.BooleanField(
                default=False,
                help_text='User has approved deliberate cloud uploads'
            ),
        ),

        # Create MediaLocation model
        migrations.CreateModel(
            name='MediaLocation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('organization_uuid', models.UUIDField(db_index=True, help_text='Organization UUID for multi-tenancy')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('location_type', models.CharField(
                    choices=[
                        ('local_device', 'Local Device'),
                        ('local_network', 'Local Network'),
                        ('external_drive', 'External Drive'),
                        ('cloud_original', 'Cloud Original'),
                        ('cloud_proxy', 'Cloud Proxy'),
                        ('remote_url', 'Remote URL'),
                        ('generated', 'Generated Media'),
                    ],
                    max_length=30,
                    help_text='Type of location where asset is stored'
                )),
                ('availability', models.CharField(
                    choices=[
                        ('available', 'Available'),
                        ('offline', 'Offline'),
                        ('needs_relink', 'Needs Relink'),
                        ('proxy_available', 'Proxy Available'),
                        ('cloud_available', 'Cloud Available'),
                        ('processing', 'Processing'),
                        ('invalid', 'Invalid'),
                    ],
                    default='available',
                    max_length=20,
                    help_text='Current availability state'
                )),
                ('local_engine_id', models.UUIDField(
                    null=True,
                    blank=True,
                    help_text='Local engine that manages this asset'
                )),
                ('local_location_id', models.CharField(
                    max_length=255,
                    null=True,
                    blank=True,
                    help_text='Opaque local reference (never a path)'
                )),
                ('cloud_path', models.CharField(
                    max_length=1000,
                    null=True,
                    blank=True,
                    help_text='S3 key or similar cloud path'
                )),
                ('remote_url', models.URLField(
                    max_length=2000,
                    null=True,
                    blank=True,
                    help_text='Remote URL if from external source'
                )),
                ('last_verified', models.DateTimeField(
                    null=True,
                    blank=True,
                    help_text='When availability was last checked'
                )),
                ('proxy_available', models.BooleanField(
                    default=False,
                    help_text='Whether a proxy exists for this asset'
                )),
                ('waveform_available', models.BooleanField(
                    default=False,
                    help_text='Whether waveform data exists'
                )),
                ('thumbnail_available', models.BooleanField(
                    default=False,
                    help_text='Whether thumbnail grid exists'
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_created',
                    to='auth.user'
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_updated',
                    to='auth.user'
                )),
                ('asset', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='locations',
                    to='production_ledger.mediaasset'
                )),
            ],
            options={
                'verbose_name': 'Media Location',
                'verbose_name_plural': 'Media Locations',
                'indexes': [
                    models.Index(fields=['asset', 'location_type'], name='media_loc_asset_type'),
                    models.Index(fields=['availability'], name='media_loc_avail'),
                    models.Index(fields=['organization_uuid', 'location_type'], name='media_loc_org_type'),
                ],
            },
        ),

        # Create MediaFingerprint model
        migrations.CreateModel(
            name='MediaFingerprint',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('organization_uuid', models.UUIDField(db_index=True, help_text='Organization UUID for multi-tenancy')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('fingerprint_version', models.PositiveIntegerField(
                    help_text='Version of fingerprinting algorithm'
                )),
                ('fingerprint_method', models.CharField(
                    choices=[
                        ('size_duration', 'Size + Duration'),
                        ('size_duration_codec', 'Size + Duration + Codec'),
                        ('partial_hash', 'Partial Hash'),
                        ('full_hash', 'Full Hash'),
                        ('multi_method', 'Multi-Method'),
                    ],
                    max_length=30,
                    help_text='Method used for fingerprinting'
                )),
                ('file_size', models.BigIntegerField(
                    help_text='File size in bytes'
                )),
                ('duration_ms', models.PositiveIntegerField(
                    help_text='Duration in milliseconds'
                )),
                ('codec_metadata', models.JSONField(
                    null=True,
                    blank=True,
                    help_text='Codec information (video/audio codecs, frame rate, etc.)'
                )),
                ('first_chunk_hash', models.CharField(
                    max_length=64,
                    null=True,
                    blank=True,
                    help_text='Hash of first 1MB chunk'
                )),
                ('last_chunk_hash', models.CharField(
                    max_length=64,
                    null=True,
                    blank=True,
                    help_text='Hash of last 1MB chunk'
                )),
                ('partial_hash', models.CharField(
                    max_length=64,
                    null=True,
                    blank=True,
                    help_text='Hash of first 10% of file'
                )),
                ('full_hash', models.CharField(
                    max_length=64,
                    null=True,
                    blank=True,
                    db_index=True,
                    help_text='Complete SHA256 hash'
                )),
                ('verified_at', models.DateTimeField(
                    null=True,
                    blank=True,
                    help_text='When fingerprint was verified'
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_created',
                    to='auth.user'
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_updated',
                    to='auth.user'
                )),
                ('asset', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='fingerprint',
                    to='production_ledger.mediaasset'
                )),
            ],
            options={
                'verbose_name': 'Media Fingerprint',
                'verbose_name_plural': 'Media Fingerprints',
                'indexes': [
                    models.Index(fields=['full_hash'], name='media_fp_hash'),
                    models.Index(fields=['file_size', 'duration_ms'], name='media_fp_size_dur'),
                ],
            },
        ),

        # Create LocalEngineInstallation model
        migrations.CreateModel(
            name='LocalEngineInstallation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('organization_uuid', models.UUIDField(db_index=True, help_text='Organization UUID for multi-tenancy')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('engine_name', models.CharField(
                    max_length=255,
                    help_text='User-facing name for this installation'
                )),
                ('engine_uuid', models.UUIDField(
                    unique=True,
                    help_text='Unique identifier for this local engine'
                )),
                ('registration_key_hash', models.CharField(
                    max_length=64,
                    help_text='Hash of one-time registration key'
                )),
                ('last_heartbeat', models.DateTimeField(
                    null=True,
                    blank=True,
                    help_text='Last time engine checked in'
                )),
                ('is_online', models.BooleanField(
                    default=False,
                    help_text='Engine currently connected'
                )),
                ('version', models.CharField(
                    max_length=50,
                    blank=True,
                    help_text='Engine software version'
                )),
                ('platform', models.CharField(
                    max_length=50,
                    blank=True,
                    choices=[
                        ('windows', 'Windows'),
                        ('macos', 'macOS'),
                        ('linux', 'Linux'),
                    ],
                    help_text='Operating system'
                )),
                ('auto_process_jobs', models.BooleanField(
                    default=False,
                    help_text='Automatically start queued jobs'
                )),
                ('max_concurrent_jobs', models.PositiveIntegerField(
                    default=1,
                    help_text='Maximum concurrent jobs to process'
                )),
                ('proxy_quality', models.CharField(
                    max_length=50,
                    default='720p',
                    help_text='Proxy quality preset (720p, 1080p, etc.)'
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_created',
                    to='auth.user'
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_updated',
                    to='auth.user'
                )),
            ],
            options={
                'verbose_name': 'Local Engine Installation',
                'verbose_name_plural': 'Local Engine Installations',
                'unique_together': {('organization_uuid', 'engine_uuid')},
                'indexes': [
                    models.Index(fields=['organization_uuid', 'is_online'], name='loc_eng_org_on'),
                    models.Index(fields=['last_heartbeat'], name='loc_eng_hb'),
                ],
            },
        ),

        # Create LocalEngineSession model
        migrations.CreateModel(
            name='LocalEngineSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('organization_uuid', models.UUIDField(db_index=True, help_text='Organization UUID for multi-tenancy')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session_token', models.CharField(
                    max_length=255,
                    db_index=True,
                    unique=True,
                    help_text='Short-lived authentication token'
                )),
                ('browser_origin', models.CharField(
                    max_length=255,
                    help_text='Browser origin for validation'
                )),
                ('expires_at', models.DateTimeField(
                    help_text='When this session expires'
                )),
                ('last_heartbeat', models.DateTimeField(
                    auto_now=True,
                    help_text='Last activity timestamp'
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_created',
                    to='auth.user'
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_updated',
                    to='auth.user'
                )),
                ('local_engine', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sessions',
                    to='splice.localengineinstallation'
                )),
            ],
            options={
                'verbose_name': 'Local Engine Session',
                'verbose_name_plural': 'Local Engine Sessions',
                'indexes': [
                    models.Index(fields=['local_engine', 'expires_at'], name='ses_eng_exp'),
                    models.Index(fields=['session_token'], name='ses_token'),
                ],
            },
        ),

        # Create LocalProcessingJob model
        migrations.CreateModel(
            name='LocalProcessingJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('organization_uuid', models.UUIDField(db_index=True, help_text='Organization UUID for multi-tenancy')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('job_type', models.CharField(
                    choices=[
                        ('probe_media', 'Probe Media File'),
                        ('create_proxy_video', 'Create Video Proxy'),
                        ('create_proxy_audio', 'Create Audio Proxy'),
                        ('generate_waveform', 'Generate Waveform'),
                        ('generate_thumbnails', 'Generate Thumbnails'),
                        ('synchronize_media', 'Synchronize Media'),
                        ('transcribe_asset', 'Transcribe Asset'),
                        ('render_video', 'Render Video'),
                        ('render_audio', 'Render Audio'),
                        ('render_social_clip', 'Render Social Clip'),
                    ],
                    max_length=50,
                    help_text='Type of processing job'
                )),
                ('status', models.CharField(
                    choices=[
                        ('queued', 'Queued'),
                        ('waiting_for_engine', 'Waiting for Engine'),
                        ('waiting_for_media', 'Waiting for Media'),
                        ('processing', 'Processing'),
                        ('completed', 'Completed'),
                        ('failed', 'Failed'),
                        ('cancelled', 'Cancelled'),
                    ],
                    default='queued',
                    max_length=20,
                    help_text='Current job status'
                )),
                ('priority', models.PositiveIntegerField(
                    default=5,
                    help_text='Job priority (0=highest, 10=lowest)'
                )),
                ('progress_percent', models.PositiveIntegerField(
                    default=0,
                    help_text='Processing progress 0-100'
                )),
                ('input_data', models.JSONField(
                    help_text='Job parameters (no file paths)'
                )),
                ('output_data', models.JSONField(
                    null=True,
                    blank=True,
                    help_text='Job results'
                )),
                ('error_code', models.CharField(
                    max_length=50,
                    null=True,
                    blank=True,
                    help_text='Error code if job failed'
                )),
                ('error_message', models.TextField(
                    blank=True,
                    help_text='Human-readable error message'
                )),
                ('started_at', models.DateTimeField(
                    null=True,
                    blank=True,
                    help_text='When processing started'
                )),
                ('completed_at', models.DateTimeField(
                    null=True,
                    blank=True,
                    help_text='When processing completed'
                )),
                ('user_confirmed', models.BooleanField(
                    default=False,
                    help_text='User confirmed job execution'
                )),
                ('auto_start_approved', models.BooleanField(
                    default=False,
                    help_text='User approved auto-start of jobs'
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_created',
                    to='auth.user'
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_updated',
                    to='auth.user'
                )),
                ('editor_project', models.ForeignKey(
                    null=True,
                    blank=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='local_processing_jobs',
                    to='splice.editorproject'
                )),
                ('local_engine', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='processing_jobs',
                    to='splice.localengineinstallation'
                )),
                ('media_asset', models.ForeignKey(
                    null=True,
                    blank=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='local_processing_jobs',
                    to='production_ledger.mediaasset'
                )),
            ],
            options={
                'verbose_name': 'Local Processing Job',
                'verbose_name_plural': 'Local Processing Jobs',
                'indexes': [
                    models.Index(fields=['local_engine', 'status'], name='job_eng_status'),
                    models.Index(fields=['status', 'priority'], name='job_status_prio'),
                    models.Index(fields=['editor_project'], name='job_project'),
                ],
            },
        ),

        # Create RenderPlan model
        migrations.CreateModel(
            name='RenderPlan',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('organization_uuid', models.UUIDField(db_index=True, help_text='Organization UUID for multi-tenancy')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('revision', models.PositiveIntegerField(
                    help_text='Project revision this plan renders'
                )),
                ('asset_selections', models.JSONField(
                    help_text='Selected assets as UUIDs (not paths)'
                )),
                ('operations', models.JSONField(
                    help_text='Serialized edit operations'
                )),
                ('camera_cuts', models.JSONField(
                    help_text='Camera selection by timeline'
                )),
                ('sync_offsets', models.JSONField(
                    help_text='Asset sync offsets'
                )),
                ('output_preset', models.CharField(
                    max_length=100,
                    help_text='Export preset name'
                )),
                ('canvas_width', models.PositiveIntegerField()),
                ('canvas_height', models.PositiveIntegerField()),
                ('frame_rate', models.PositiveIntegerField()),
                ('loudness_preset', models.CharField(
                    max_length=50,
                    help_text='Loudness normalization preset'
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_created',
                    to='auth.user'
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(class)s_updated',
                    to='auth.user'
                )),
                ('project', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='render_plans',
                    to='splice.editorproject'
                )),
            ],
            options={
                'verbose_name': 'Render Plan',
                'verbose_name_plural': 'Render Plans',
                'indexes': [
                    models.Index(fields=['project', 'revision'], name='plan_proj_rev'),
                ],
            },
        ),
    ]
