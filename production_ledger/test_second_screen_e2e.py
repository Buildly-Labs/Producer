import uuid
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from production_ledger.models import Show, Episode, Segment, Sponsor

User = get_user_model()


class SecondScreenE2ETest(TestCase):
    def setUp(self):
        self.org = uuid.uuid4()
        self.user = User.objects.create_superuser('e2etest', 'e2e@test.local', 'testpass123')
        self.show = Show.objects.create(
            organization_uuid=self.org, name='E2E Show',
            slug='e2e-show', brand_primary_color='#FF5733',
        )
        self.episode = Episode.objects.create(organization_uuid=self.org, show=self.show, title='E2E Episode')
        self.sponsor = Sponsor.objects.create(
            organization_uuid=self.org, show=self.show, name='Acme Corp',
            website_url='https://example.com/acme', ad_copy='Acme: Making Everything.',
        )
        self.seg1 = Segment.objects.create(organization_uuid=self.org, episode=self.episode, order=1, title='Intro', sponsor=self.sponsor)
        self.seg2 = Segment.objects.create(organization_uuid=self.org, episode=self.episode, order=2, title='Main Topic')
        self.client = Client()
        self.client.login(username='e2etest', password='testpass123')

    def test_control_room_shows_live_controls(self):
        r = self.client.get(f'/ledger/episodes/{self.episode.pk}/control-room/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Set Live', r.content)
        self.assertIn(b'Open Second Screen', r.content)

    def test_set_live_segment_and_second_screen_reflects_it(self):
        r2 = self.client.post(f'/ledger/episodes/{self.episode.pk}/control-room/', {
            'action': 'set_live_segment', 'segment_id': str(self.seg1.pk),
        })
        self.assertEqual(r2.status_code, 302)

        self.episode.refresh_from_db()
        self.assertEqual(self.episode.active_segment_id, self.seg1.pk)

        r3 = self.client.get(f'/ledger/episodes/{self.episode.pk}/second-screen/')
        self.assertEqual(r3.status_code, 200)
        self.assertIn(b'Acme Corp', r3.content)
        self.assertIn(b'Intro', r3.content)

        r4 = self.client.get(f'/ledger/episodes/{self.episode.pk}/second-screen/state/')
        self.assertEqual(r4.status_code, 200)
        data = r4.json()
        self.assertEqual(data['segment']['title'], 'Intro')
        self.assertEqual(data['sponsor']['name'], 'Acme Corp')
        self.assertIsNotNone(data['sponsor']['qr_code_url'])

    def test_qr_code_endpoint_returns_png(self):
        r5 = self.client.get(f'/ledger/sponsors/{self.sponsor.pk}/qr-code/')
        self.assertEqual(r5.status_code, 200)
        self.assertEqual(r5['Content-Type'], 'image/png')
        self.assertGreater(len(r5.content), 100)

    def test_clear_live_segment(self):
        self.episode.active_segment = self.seg1
        self.episode.save(update_fields=['active_segment'])

        r = self.client.post(f'/ledger/episodes/{self.episode.pk}/control-room/', {
            'action': 'set_live_segment', 'segment_id': '',
        })
        self.assertEqual(r.status_code, 302)
        self.episode.refresh_from_db()
        self.assertIsNone(self.episode.active_segment_id)

        r2 = self.client.get(f'/ledger/episodes/{self.episode.pk}/second-screen/state/')
        self.assertIsNone(r2.json()['segment'])

    def test_overlay_mode_is_transparent_and_control_room_links_it(self):
        r = self.client.get(f'/ledger/episodes/{self.episode.pk}/control-room/')
        self.assertIn(b'second-screen/?overlay=1', r.content)
        self.assertIn(b'Use in OBS Studio', r.content)

        r2 = self.client.get(f'/ledger/episodes/{self.episode.pk}/second-screen/?overlay=1')
        self.assertEqual(r2.status_code, 200)
        self.assertIn(b'class="overlay"', r2.content)
        self.assertIn(b'IS_OVERLAY = true', r2.content)

        r3 = self.client.get(f'/ledger/episodes/{self.episode.pk}/second-screen/')
        self.assertIn(b'IS_OVERLAY = false', r3.content)


class OverlayTokenAuthTest(TestCase):
    """The OBS overlay must be reachable with a valid episode token and NO
    login (OBS Browser Sources can't sign in), and rejected without one."""

    def setUp(self):
        self.org = uuid.uuid4()
        self.user = User.objects.create_superuser('tokuser', 'tok@test.local', 'testpass123')
        self.show = Show.objects.create(organization_uuid=self.org, name='Tok Show', slug='tok-show')
        self.episode = Episode.objects.create(organization_uuid=self.org, show=self.show, title='Tok Episode')
        self.sponsor = Sponsor.objects.create(
            organization_uuid=self.org, show=self.show, name='Sponsy',
            website_url='https://example.com/sponsy',
        )
        self.seg = Segment.objects.create(
            organization_uuid=self.org, episode=self.episode, order=1, title='Live Seg', sponsor=self.sponsor,
        )
        self.episode.active_segment = self.seg
        self.episode.save(update_fields=['active_segment'])
        self.token = self.episode.overlay_token
        # Anonymous client — simulates OBS with no session.
        self.client = Client()

    def test_overlay_loads_with_valid_token_no_login(self):
        url = f'/ledger/episodes/{self.episode.pk}/second-screen/?overlay=1&token={self.token}'
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Live Seg', r.content)
        self.assertIn(b'class="overlay"', r.content)

    def test_state_endpoint_with_valid_token_no_login(self):
        url = f'/ledger/episodes/{self.episode.pk}/second-screen/state/?token={self.token}'
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['segment']['title'], 'Live Seg')
        # QR URL must point at the token-authorized overlay endpoint, not the login-gated one.
        self.assertIn('overlay-qr', data['sponsor']['qr_code_url'])
        self.assertIn(f'token={self.token}', data['sponsor']['qr_code_url'])

    def test_overlay_qr_loads_with_valid_token(self):
        url = f'/ledger/episodes/{self.episode.pk}/overlay-qr/?token={self.token}'
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'image/png')

    def test_no_token_redirects_to_login(self):
        # Without a token, anonymous access falls back to login enforcement.
        r = self.client.get(f'/ledger/episodes/{self.episode.pk}/second-screen/?overlay=1')
        self.assertIn(r.status_code, (302, 403))

    def test_wrong_token_rejected(self):
        url = f'/ledger/episodes/{self.episode.pk}/second-screen/?overlay=1&token=bogus'
        r = self.client.get(url)
        self.assertIn(r.status_code, (302, 403))

    def test_regenerate_token_invalidates_old_url(self):
        old = self.episode.overlay_token
        self.episode.regenerate_overlay_token()
        self.episode.refresh_from_db()
        self.assertNotEqual(old, self.episode.overlay_token)
        r = self.client.get(f'/ledger/episodes/{self.episode.pk}/second-screen/?overlay=1&token={old}')
        self.assertIn(r.status_code, (302, 403))
