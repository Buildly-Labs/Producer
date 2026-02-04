from django.apps import AppConfig


class ProductionLedgerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'production_ledger'
    verbose_name = 'Production Ledger'

    def ready(self):
        # Import signals when the app is ready
        import production_ledger.signals  # noqa
