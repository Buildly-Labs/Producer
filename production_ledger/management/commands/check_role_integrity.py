"""
Management command to detect duplicate role assignments that can cause unstable
permission behavior in deployed environments.

Usage:
    python manage.py check_role_integrity
"""
from django.core.management.base import BaseCommand
from django.db.models import Count

from production_ledger.models import EpisodeRoleOverride, ShowRoleAssignment


class Command(BaseCommand):
    help = 'Detect duplicate show/episode role assignment rows and report them.'

    def handle(self, *args, **options):
        show_dupes = (
            ShowRoleAssignment.objects
            .values('show_id', 'user_id')
            .annotate(row_count=Count('id'))
            .filter(row_count__gt=1)
            .order_by('-row_count')
        )

        episode_dupes = (
            EpisodeRoleOverride.objects
            .values('episode_id', 'user_id')
            .annotate(row_count=Count('id'))
            .filter(row_count__gt=1)
            .order_by('-row_count')
        )

        if not show_dupes and not episode_dupes:
            self.stdout.write(self.style.SUCCESS('No duplicate role rows found.'))
            return

        if show_dupes:
            self.stdout.write(self.style.WARNING('\nDuplicate ShowRoleAssignment rows:'))
            for row in show_dupes:
                self.stdout.write(
                    f"  show={row['show_id']} user={row['user_id']} count={row['row_count']}"
                )

        if episode_dupes:
            self.stdout.write(self.style.WARNING('\nDuplicate EpisodeRoleOverride rows:'))
            for row in episode_dupes:
                self.stdout.write(
                    f"  episode={row['episode_id']} user={row['user_id']} count={row['row_count']}"
                )

        self.stdout.write('\nRun data cleanup for any rows listed above to enforce one role row per (scope, user).')
