import uuid
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from production_ledger.models import Show, Episode, Segment, SegmentTemplate, Sponsor

User = get_user_model()


class SegmentReuseE2ETest(TestCase):
    def setUp(self):
        self.org = uuid.uuid4()
        self.user = User.objects.create_superuser('reusetest', 'reuse@test.local', 'testpass123')
        self.show = Show.objects.create(organization_uuid=self.org, name='Reuse Show', slug='reuse-show')
        self.episode = Episode.objects.create(organization_uuid=self.org, show=self.show, title='Episode A')
        self.other_episode = Episode.objects.create(organization_uuid=self.org, show=self.show, title='Episode B')
        self.sponsor = Sponsor.objects.create(organization_uuid=self.org, show=self.show, name='Acme', website_url='https://example.com')
        self.template = SegmentTemplate.objects.create(
            organization_uuid=self.org, show=self.show, title='Lightning Round',
            purpose='Quick fire questions', timebox_minutes=7, sponsor=self.sponsor,
        )
        self.client = Client()
        self.client.login(username='reusetest', password='testpass123')

    def test_segments_tab_shows_template_picker(self):
        r = self.client.get(f'/ledger/episodes/{self.episode.pk}/segments/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Use an Existing Segment', r.content)
        self.assertIn(b'Lightning Round', r.content)

    def test_use_template_creates_independent_copy(self):
        r = self.client.post(f'/ledger/episodes/{self.episode.pk}/segments/', {
            'action': 'use_template', 'template': str(self.template.pk),
        })
        self.assertEqual(r.status_code, 302)

        segment = Segment.objects.get(episode=self.episode)
        self.assertEqual(segment.title, 'Lightning Round')
        self.assertEqual(segment.timebox_minutes, 7)
        self.assertEqual(segment.sponsor_id, self.sponsor.pk)
        self.assertEqual(segment.source_template_id, self.template.pk)

        # Editing the copy must not touch the template or other episodes.
        segment.title = 'Lightning Round (special)'
        segment.save(update_fields=['title'])
        self.template.refresh_from_db()
        self.assertEqual(self.template.title, 'Lightning Round')

        r2 = self.client.post(f'/ledger/episodes/{self.other_episode.pk}/segments/', {
            'action': 'use_template', 'template': str(self.template.pk),
        })
        self.assertEqual(r2.status_code, 302)
        other_segment = Segment.objects.get(episode=self.other_episode)
        self.assertEqual(other_segment.title, 'Lightning Round')
        self.assertNotEqual(other_segment.pk, segment.pk)

    def test_template_picker_scoped_to_show(self):
        other_show = Show.objects.create(organization_uuid=uuid.uuid4(), name='Other Show', slug='other-show')
        other_template = SegmentTemplate.objects.create(
            organization_uuid=other_show.organization_uuid, show=other_show, title='Not Visible Here',
        )
        r = self.client.get(f'/ledger/episodes/{self.episode.pk}/segments/')
        self.assertNotIn(b'Not Visible Here', r.content)

    def test_segment_library_crud(self):
        r = self.client.get(f'/ledger/shows/{self.show.pk}/segment-templates/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Lightning Round', r.content)

        r2 = self.client.post(f'/ledger/shows/{self.show.pk}/segment-templates/', {
            'title': 'Cold Open', 'timebox_minutes': 3, 'owner_role': 'host',
            'purpose': '', 'bullet_prompts': '', 'key_questions': '', 'sponsor': '',
        })
        self.assertEqual(r2.status_code, 302)
        self.assertTrue(SegmentTemplate.objects.filter(show=self.show, title='Cold Open').exists())
