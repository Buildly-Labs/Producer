"""
Signals for Production Ledger app.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Episode


@receiver(post_save, sender=Episode)
def seed_episode_checklist(sender, instance, created, **kwargs):
    """
    Automatically seed checklist items when an episode is created.
    """
    if created:
        instance.seed_checklist()
