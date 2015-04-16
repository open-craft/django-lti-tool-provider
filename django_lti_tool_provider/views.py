from django.views.generic import View
import oauth2
import logging

from django.conf import settings
from django.core.urlresolvers import reverse, NoReverseMatch
from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

from ims_lti_py.tool_provider import DjangoToolProvider

from django_lti_tool_provider.models import LtiUserData
from django_lti_tool_provider.signals import Signals


_logger = logging.getLogger(__name__)


class LTIView(View):
    authentication_hooks = []

    PASS_TO_AUTHENTICATION_HOOK = {
        'lis_person_sourcedid': 'username',
        'lis_person_contact_email_primary': 'email',
        'user_id': 'user_id'
    }

    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super(LTIView, self).dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        return self.process_request(request)

    def post(self, request, *args, **kwargs):
        return self.process_request(request)

    def process_request(self, request):
        if not request.user.is_authenticated():
            try:
                lti_parameters = self._get_lti_parameters_from_request(request)
                lti_data = {
                    hook_name: lti_parameters.get(lti_name, None)
                    for lti_name, hook_name in self.PASS_TO_AUTHENTICATION_HOOK.items()
                }
            except oauth2.Error, e:
                _logger.exception(u"Invalid LTI Request")
                return HttpResponseBadRequest("Invalid LTI Request: " + e.message)

            for hook in self.authentication_hooks:
                hook(request, lti_data)

        if request.user.is_authenticated():
            return self.process_authenticated_lti(request)
        else:
            return self.process_anonymous_lti(request)

    @classmethod
    def _get_lti_parameters_from_request(cls, request):
        provider = DjangoToolProvider(settings.CONSUMER_KEY, settings.LTI_SECRET, request.POST)
        provider.valid_request(request)
        return provider.to_params()

    @classmethod
    def _get_anonymous_redirect_url(cls, request):
        try:
            result = "{login}?next={lti_handler}".format(
                login=reverse('django.contrib.auth.views.login'),
                lti_handler=request.path.strip('/')
            )
        except NoReverseMatch:
            result = "/"
        return result

    @classmethod
    def _get_authenticated_redirect_url(cls):
        redirect_to = getattr(settings, 'REDIRECT_AFTER_LTI', '')
        try:
            result = reverse(redirect_to)
        except NoReverseMatch:
            result = "/"+redirect_to
        return result

    @classmethod
    def register_authentication_hook(cls, hook):
        """ Adds hook to pre-processing hooks list """
        cls.authentication_hooks.append(hook)

    @classmethod
    def process_anonymous_lti(cls, request):
        """
        This method handles LTI request if it was sent prior to MyDante authorization. In such a case, we need user
        authenticated first. Unfortunately, it looses POST data in the process, so when it gets back original LTI
        request is gone. So we save important parts of it into session to retrieve when OpenID authentication happened
        """
        try:
            provider = DjangoToolProvider(settings.CONSUMER_KEY, settings.LTI_SECRET, request.POST)
            provider.valid_request(request)
        except oauth2.Error, e:
            _logger.exception(u"Invalid LTI Request")
            return HttpResponseBadRequest("Invalid LTI Request: " + e.message)

        request.session['lti_parameters'] = provider.to_params()
        request.session.save()
        return HttpResponseRedirect(cls._get_anonymous_redirect_url(request))

    @classmethod
    def process_authenticated_lti(cls, request):
        """
        There are two options:
        1. This is actual LTI request made with cookies already set - need parsing and validating LTI parameters
        2. This is OpenID redirect from edx if actual LTI request was send anonymously - already validated
           LTI parameters and stored them in session - take them from session

        When lti parameters are ready (either taken from session or parsed and validated from request) store them
        in DB for later
        """
        if 'lti_parameters' in request.session and 'lis_result_sourcedid' not in request.POST:
            lti_parameters = request.session['lti_parameters']
            del request.session['lti_parameters']
        else:
            try:
                lti_parameters = cls._get_lti_parameters_from_request(request)
            except oauth2.Error, e:
                _logger.exception(u"Invalid LTI Request")
                return HttpResponseBadRequest("Invalid LTI Request: " + e.message)

        lti_data = cls._store_lti_parameters(request.user, lti_parameters)
        Signals.LTI.received.send(cls, user=request.user, lti_data=lti_data)

        return HttpResponseRedirect(cls._get_authenticated_redirect_url())

    @classmethod
    def _store_lti_parameters(cls, user, parameters):
        """
        Filters out OAuth parameters than stores LTI parameters into the DB, creating or updating record as needed
        """
        lti_params = {
            key: value
            for key, value in parameters.iteritems()
            if 'oauth' not in key
        }
        lti_user_data, created = LtiUserData.objects.get_or_create(user=user)
        if not created:
            _logger.debug("Replaced LTI parameters for user %s", user.username)
        lti_user_data.edx_lti_parameters = lti_params
        lti_user_data.save()
        return lti_user_data
