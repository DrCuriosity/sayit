import os
import tempfile
import shutil
import datetime

from django.test.utils import override_settings
from django.conf import settings

from instances.tests import InstanceTestCase

import speeches
from speeches.models import Speech, Speaker, Section

TEMP_MEDIA_ROOT = tempfile.mkdtemp()

@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class SpeechTests(InstanceTestCase):

    @classmethod
    def setUpClass(cls):
        cls._in_fixtures = os.path.join(os.path.abspath(speeches.__path__[0]), 'fixtures', 'test_inputs')

    def tearDown(self):
        # Clear the speeches folder if it exists
        speeches_folder = os.path.join(settings.MEDIA_ROOT, 'speeches')
        if(os.path.exists(speeches_folder)):
            shutil.rmtree(speeches_folder)

    def test_add_speech_page_exists(self):
        # Test that the page exists and has the right title
        resp = self.client.get('/speech/add')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue('add a new speech' in resp.content)

    def test_add_speech_fails_on_empty_form(self):
        # Test that the form won't submit if empty
        resp = self.client.post('/speech/add')
        self.assertFormError(resp, 'form', None, 'You must provide either text or some audio')

    def test_add_speech_without_speaker(self):
        # Test form without speaker
        resp = self.client.post('/speech/add', {
            'text': 'This is a speech'
        })
        speech = Speech.objects.order_by('-id')[0]
        self.assertRedirects(resp, '/speech/%d' % speech.id)
        self.assertEqual(speech.text, 'This is a speech')

    def test_add_speech_and_add_another(self):
        # Test form with 'add_another' but without a section
        # (client JS will prevent this case from happening, in general)
        resp = self.client.post('/speech/add', {
            'text': 'This is a speech',
            'add_another': 1,
        })
        speech = Speech.objects.order_by('-id')[0]
        self.assertEqual(speech.text, 'This is a speech')
        self.assertRedirects(resp, '/speech/add')

        section = Section.objects.create(title='Test', instance=self.instance)
        resp = self.client.post('/speech/add', {
            'text': 'This is a speech',
            'section': section.id,
            'add_another': 1,
        })
        speech = Speech.objects.order_by('-id')[0]
        self.assertEqual(speech.text, 'This is a speech')
        self.assertEqual(speech.section_id, section.id)
        self.assertRedirects(resp, '/speech/add?section=%d' % section.id)

    def test_add_speech_with_speaker(self):
        # Test form with speaker, we need to add a speaker first
        speaker = Speaker.objects.create(name='Steve', instance=self.instance)

        resp = self.client.post('/speech/add', {
            'text': 'This is a Steve speech',
            'speaker': speaker.id
        })
        # Check in db
        speech = Speech.objects.get(speaker=speaker.id)
        self.assertEqual(speech.text, 'This is a Steve speech')

    def test_add_speech_with_audio(self):
        # Load the mp3 fixture
        audio = open(os.path.join(self._in_fixtures, 'lamb.mp3'), 'rb')

        resp = self.client.post('/speech/add', {
            'audio': audio
        })
        # Assert that it uploads and we're told to wait
        speech = Speech.objects.order_by('-id')[0]
        resp = self.client.get('/speech/%d' % speech.id)
        self.assertTrue('Please wait' in resp.content)

        # Assert that it's in the model
        self.assertIsNotNone(speech.audio)

    def test_add_speech_with_audio_and_text(self):
        # Load the mp3 fixture
        audio = open(os.path.join(self._in_fixtures, 'lamb.mp3'), 'rb')
        text = 'This is a speech with some text'

        resp = self.client.post('/speech/add', {
            'audio': audio,
            'text': text
        })

        # Assert that it uploads and we see it straightaway
        speech = Speech.objects.order_by('-id')[0]
        resp = self.client.get('/speech/%d' % speech.id)
        self.assertFalse('Please wait' in resp.content)
        self.assertTrue(text in resp.content)

        # Test edit page
        resp = self.client.get('/speech/%d/edit' % speech.id)

    def test_add_speech_fails_with_unsupported_audio(self):
        # Load the .aiff fixture
        audio = open(os.path.join(self._in_fixtures, 'lamb.aiff'), 'rb')

        resp = self.client.post('/speech/add', {
            'audio': audio
        })

        # Assert that it fails and gives us an error
        self.assertFormError(resp, 'form', 'audio', 'That file does not appear to be an audio file')

    def test_add_speech_creates_celery_task(self):
        # Load the mp3 fixture
        audio = open(os.path.join(self._in_fixtures, 'lamb.mp3'), 'rb')
        resp = self.client.post('/speech/add', {
            'audio': audio
        })

        # Assert that a celery task id is in the model
        speech = Speech.objects.order_by('-id')[0]
        self.assertIsNotNone(speech.celery_task_id)

    def test_add_speech_with_text_does_not_create_celery_task(self):
        # Load the mp3 fixture
        audio = open(os.path.join(self._in_fixtures, 'lamb.mp3'), 'rb')
        text = 'This is a speech with some text'

        resp = self.client.post('/speech/add', {
            'audio': audio,
            'text': text
        })

        # Assert that a celery task id is in the model
        speech = Speech.objects.order_by('-id')[0]
        self.assertIsNone(speech.celery_task_id)

    def test_speech_displayed_when_celery_task_finished(self):
        # Load the mp3 fixture
        audio = open(os.path.join(self._in_fixtures, 'lamb.mp3'), 'rb')
        text = 'This is a speech with some text'

        resp = self.client.post('/speech/add', {
            'audio': audio
        })

        # Assert that a celery task id is in the model
        speech = Speech.objects.order_by('-id')[0]
        self.assertIsNotNone(speech.celery_task_id)

        # Remove the celery task
        speech.celery_task_id = None
        speech.text = text
        speech.save()

        # Check the page doesn't show "Please wait" but shows our text instead
        resp = self.client.get('/speech/%d' % speech.id)
        self.assertFalse('Please wait' in resp.content)
        self.assertTrue(text in resp.content)

    def test_add_speech_with_dates_only(self):
        # Test form with dates (but not times)
        resp = self.client.post('/speech/add', {
            'text': 'This is a speech',
            'start_date': '01/01/2000',
            'end_date': '01/01/2000'
        })
        speech = Speech.objects.order_by('-id')[0]
        self.assertRedirects(resp, '/speech/%d' % speech.id)
        self.assertEqual(speech.start_date, datetime.date(year=2000, month=1, day=1))
        self.assertIsNone(speech.start_time)
        self.assertEqual(speech.end_date, datetime.date(year=2000, month=1, day=1))
        self.assertIsNone(speech.end_time)

    def test_add_speech_with_dates_and_times(self):
        # Test form with dates (but not times)
        resp = self.client.post('/speech/add', {
            'text': 'This is a speech',
            'start_date': '01/01/2000',
            'start_time': '12:45',
            'end_date': '01/01/2000',
            'end_time': '17:53'
        })
        speech = Speech.objects.order_by('-id')[0]
        self.assertRedirects(resp, '/speech/%d' % speech.id)
        self.assertEqual(speech.start_date, datetime.date(year=2000, month=1, day=1))
        self.assertEqual(speech.start_time, datetime.time(hour=12, minute=45))
        self.assertEqual(speech.end_date, datetime.date(year=2000, month=1, day=1))
        self.assertEqual(speech.end_time, datetime.time(hour=17, minute=53))

    def test_add_speech_fails_with_times_only(self):
        # Test form with dates (but not times)
        resp = self.client.post('/speech/add', {
            'text': 'This is a speech',
            'start_time': '12:45',
            'end_time': '17:53'
        })
        self.assertFormError(resp, 'form', 'start_time', 'If you provide a start time you must give a start date too')
        self.assertFormError(resp, 'form', 'end_time', 'If you provide an end time you must give an end date too')

    def test_add_speech_with_audio_encodes_to_mp3(self):
        # Load the wav fixture
        audio = open(os.path.join(self._in_fixtures, 'lamb_stereo.wav'), 'rb')

        resp = self.client.post('/speech/add', {
            'audio': audio
        })

        # Assert that it uploads and we're told to wait
        print(resp.content)

        speech = Speech.objects.order_by('-id')[0]
        resp = self.client.get('/speech/%d' % speech.id)
        self.assertTrue('Please wait' in resp.content)

        self.assertIsNotNone(speech.audio)
        self.assertTrue(".mp3" in speech.audio.path)

    def test_visible_speeches(self):
        section = Section.objects.create(title='Test', instance=self.instance)
        speeches = []
        for i in range(3):
            s = Speech.objects.create( text='Speech %d' % i, section=section, instance=self.instance, public=(i==2) )
            speeches.append(s)

        resp = self.client.get('/sections/%d' % section.id)
        self.assertEquals( [ x.public for x in resp.context['speech_list'] ], [ False, False, True ] )
        self.assertContains( resp, 'Invisible', count=2 )

        self.client.logout()
        resp = self.client.get('/speech/%d' % speeches[2].id)
        self.assertContains( resp, 'Speech 2' )
        resp = self.client.get('/speech/%d' % speeches[0].id)
        self.assertContains( resp, 'Not Found', status_code=404 )

    def test_speech_datetime_line(self):
        section = Section.objects.create(title='Test', instance=self.instance)
        Speech.objects.create( text='Speech', section=section, instance=self.instance,
            public=True, start_date=datetime.date(2000, 1, 1), end_date=datetime.date(2000, 1, 2)
        )

        resp = self.client.get('/sections/%d' % section.id)
        self.assertRegexpMatches( resp.content, '>\s+1 Jan 2000\s+&ndash;\s+2 Jan 2000\s+<' )
