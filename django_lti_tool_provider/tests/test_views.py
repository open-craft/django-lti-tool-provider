import ddt
from django.contrib.auth import login, authenticate
from mock import patch, Mock

from oauth2 import Request, Consumer, SignatureMethod_HMAC_SHA1

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test.utils import override_settings
from django.test import Client, TestCase
from django.conf import settings

from django_lti_tool_provider.models import LtiUserData
from django_lti_tool_provider.views import LTIView


@override_settings(CONSUMER_KEY='123', LTI_SECRET='456')
class LtiRequestsTestBase(TestCase):
    _data = {
        "lis_result_sourcedid": "lis_result_sourcedid",
        "context_id": "LTIX/LTI-101/now",
        "user_id": "1234567890",
        "lis_outcome_service_url": "lis_outcome_service_url",
        "resource_link_id": "resource_link_id",
        "lti_version": "LTI-1p0"
    }

    _url_base = 'http://testserver'

    @property
    def consumer(self):
        return Consumer(settings.CONSUMER_KEY, settings.LTI_SECRET)

    def _get_signed_oauth_request(self, path, method, data=None):
        data = data if data is not None else self._data
        url = self._url_base + path
        method = method if method else 'GET'
        req = Request.from_consumer_and_token(self.consumer, {}, method, url, data)
        req.sign_request(SignatureMethod_HMAC_SHA1(), self.consumer, None)
        return req

    def get_correct_lti_payload(self, path='/lti/', method='POST', data=None):
        req = self._get_signed_oauth_request(path, method, data)
        return req.to_postdata()

    def get_incorrect_lti_payload(self, path='/lti/', method='POST', data=None):
        req = self._get_signed_oauth_request(path, method, data)
        req['oauth_signature'] += '_broken'
        return req.to_postdata()

    def send_lti_request(self, payload):
        return self.client.post('/lti/', payload, content_type='application/x-www-form-urlencoded')

    def _verify_lti_created_and_redirected_to_home(self, response, user, expected_lti_data):
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self._url_base+reverse(settings.REDIRECT_AFTER_LTI))

        lti_data = LtiUserData.objects.get(user=user)
        self.assertIsNotNone(lti_data)
        for key, value in expected_lti_data.items():
            self.assertEqual(value, lti_data.edx_lti_parameters[key])


class AnonymousLtiRequestTests(LtiRequestsTestBase):
    def setUp(self):
        self.client = Client()

    def test_given_incorrect_payload_throws_bad_request(self):
        response = self.send_lti_request(self.get_incorrect_lti_payload())
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid LTI Request", response.content)

    def test_given_correct_requests_sets_session_variable(self):
        response = self.send_lti_request(self.get_correct_lti_payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self._url_base + reverse('django.contrib.auth.views.login')+'?next=lti')
        self.assertIn('lti_parameters', self.client.session)
        session_lti_params = self.client.session['lti_parameters']
        for key, value in self._data.items():
            self.assertEqual(value, session_lti_params[key])


@ddt.ddt
@patch('django_lti_tool_provider.views.Signals.LTI.received.send')
class AuthenticatedLtiRequestTests(LtiRequestsTestBase):
    fixtures = ['test_auth.yaml']

    def setUp(self):
        self.client = Client()
        self.user = User.objects.get(username='test')
        logged_in = self.client.login(username='test', password='test')
        self.assertTrue(logged_in)

    def _verify_lti_updated_signal_is_sent(self, patched_send_lti_received, expected_user):
        expected_lti_data = LtiUserData.objects.get(user=self.user)
        patched_send_lti_received.assert_called_once_with(LTIView, user=expected_user, lti_data=expected_lti_data)

    def test_no_session_given_incorrect_payload_throws_bad_request(self, _):
        response = self.send_lti_request(self.get_incorrect_lti_payload())
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid LTI Request", response.content)

    def test_no_session_correct_payload_processes_lti_request(self, patched_send_lti_received):
        with self.assertRaises(LtiUserData.DoesNotExist):
            LtiUserData.objects.get(user=self.user)  # precondition check

        response = self.send_lti_request(self.get_correct_lti_payload())

        self._verify_lti_created_and_redirected_to_home(response, self.user, self._data)
        self._verify_lti_updated_signal_is_sent(patched_send_lti_received, self.user)

    @ddt.data('GET', 'POST')
    def test_session_set_processes_lti_request(self, method, patched_send_lti_received):
        with self.assertRaises(LtiUserData.DoesNotExist):
            LtiUserData.objects.get(user=self.user)  # precondition check

        session = self.client.session
        session['lti_parameters'] = self._data
        session.save()

        if method == 'GET':
            response = self.client.get('/lti/')
        else:
            response = self.client.post('/lti/')

        self._verify_lti_created_and_redirected_to_home(response, self.user, self._data)
        self._verify_lti_updated_signal_is_sent(patched_send_lti_received, self.user)

    def test_given_session_and_lti_uses_lti(self, patched_send_lti_received):
        with self.assertRaises(LtiUserData.DoesNotExist):
            LtiUserData.objects.get(user=self.user)  # precondition check

        session = self.client.session
        session['lti_parameters'] = {}
        session.save()

        response = self.send_lti_request(self.get_correct_lti_payload())

        self._verify_lti_created_and_redirected_to_home(response, self.user, self._data)
        self._verify_lti_updated_signal_is_sent(patched_send_lti_received, self.user)


class AuthenticationHookTests(LtiRequestsTestBase):
    def setUp(self):
        self.client = Client()

    def tearDown(self):
        LTIView.authentication_hooks = []
        self.client.logout()

    def _authenticate_user(self, request):
        username = request.user.get_username()
        if not username:
            username = "test_username"
        password = "test_password"

        user = User.objects.create_user(username=username, email=username+'@test.com', password=password)
        authenticated = authenticate(username=username, password=password)
        login(request, authenticated)

        self.addCleanup(lambda: user.delete())

    def test_authentication_hook_executed_if_not_authenticated(self):
        hook = Mock()
        LTIView.register_authentication_hook(hook)
        payload = self.get_correct_lti_payload()
        self.send_lti_request(payload)
        request = hook.call_args[0][0]
        self.assertEqual(request.body, payload)
        self.assertFalse(request.user.is_authenticated())

    def test_anonymous_lti_is_processed_if_hook_does_not_authenticate_user(self):
        hook = Mock()
        LTIView.register_authentication_hook(hook)
        response = self.send_lti_request(self.get_correct_lti_payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self._url_base + reverse('django.contrib.auth.views.login')+'?next=lti')
        self.assertIn('lti_parameters', self.client.session)
        session_lti_params = self.client.session['lti_parameters']
        for key, value in self._data.items():
            self.assertEqual(value, session_lti_params[key])

    def test_authenticated_lti_is_processed_if_hook_authenticates_user(self):
        hook = Mock(side_effect=self._authenticate_user)
        LTIView.register_authentication_hook(hook)
        response = self.send_lti_request(self.get_correct_lti_payload())
        expected_user = hook.call_args[0][0].user

        self._verify_lti_created_and_redirected_to_home(response, expected_user, self._data)
