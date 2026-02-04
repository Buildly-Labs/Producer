"""
Production Ledger - A provider-agnostic system of record for podcast & media production.

This app manages the "Production + AI + Provenance Layer":
- Media ingestion and chain of custody
- Transcript management
- Clip markers and moments
- AI-assisted drafts with provenance and approval gates
- Human-in-the-loop auditability ("receipts")
- Export packages for publishing
"""

default_app_config = 'production_ledger.apps.ProductionLedgerConfig'
