from django.contrib.auth import logout
from django.core.exceptions import ImproperlyConfigured
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import View
import oauth2
import logging

from django.conf import settings
from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

from ims_lti_py.tool_provider import DjangoToolProvider

from django_lti_tool_provider.models import LtiUserData
from django_lti_tool_provider.signals import Signals


_logger = logging.getLogger(__name__)


class LTIView(View):
    """ View handling LTI requests """
    authentication_manager = None

    PASS_TO_AUTHENTICATION_HOOK = {
        'lis_person_sourcedid': 'username',
        'lis_person_contact_email_primary': 'email',
        'user_id': 'user_id'
    }

    SESSION_KEY = 'lti_parameters'

    @method_decorator(csrf_exempt)
    @method_decorator(xframe_options_exempt)
    def dispatch(self, *args, **kwargs):
        if self.authentication_manager is None:
            raise ImproperlyConfigured(u"AuthenticationManager is not set")

        return super(LTIView, self).dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        return self.process_request(request)

    def post(self, request, *args, **kwargs):
        return self.process_request(request)

    def process_request(self, request):
        if request.user.is_authenticated():
            try:
                lti_parameters = self._get_lti_parameters_from_request(request)
                if not self._right_user(request.user, lti_parameters):
                    _logger.debug(u"Logging out user %s in favor of new LTI session.", request.user.username)
                    logout(request)
            except (oauth2.Error, AttributeError):
                # Not a new visit, or better to keep existing auth.
                pass
        if not request.user.is_authenticated():
            try:
                lti_parameters = self._get_lti_parameters_from_request(request)
            except oauth2.Error as e:
                _logger.exception(u"Invalid LTI Request")
                return HttpResponseBadRequest(u"Invalid LTI Request: " + e.message)

            lti_data = {
                hook_name: lti_parameters.get(lti_name, None)
                for lti_name, hook_name in self.PASS_TO_AUTHENTICATION_HOOK.items()
            }

            _logger.debug(u"Executing authentication hook with parameters {params}", lti_data)

            self.authentication_manager.authentication_hook(request, **lti_data)

        if request.user.is_authenticated():
            return self.process_authenticated_lti(request)
        else:
            return self.process_anonymous_lti(request)

    @classmethod
    def lti_param_filter(cls, parameters):
        return {
            key: value
            for key, value in parameters.iteritems()
            if 'oauth' not in key
        }

    @classmethod
    def _right_user(cls, user, lti_parameters):
        try:
            info, created = LtiUserData.get_or_create_by_parameters(
                user, cls.authentication_manager, cls.lti_param_filter(lti_parameters)
            )
            if created:
                # If this is the first time the user's data is being created, that means
                # that the user predated the LTI request.
                return False
            return True
        except ValueError:
            return False

    @classmethod
    def _get_lti_parameters_from_request(cls, request):
        provider = DjangoToolProvider(settings.LTI_CLIENT_KEY, settings.LTI_CLIENT_SECRET, request.POST)
        provider.valid_request(request)
        return provider.to_params()

    @classmethod
    def register_authentication_manager(cls, manager):
        """ Registers authentication manager """
        cls.authentication_manager = manager

    @classmethod
    def process_anonymous_lti(cls, request):
        """
        This method handles LTI request if it was sent prior to tool authorization. In such a case, we need user
        authenticated first. Unfortunately, it looses POST data in the process, so when it gets back original LTI
        request is gone. So we save important parts of it into session to retrieve when authentication happens
        """
        try:
            lti_parameters = cls._get_lti_parameters_from_request(request)
        except oauth2.Error, e:
            _logger.exception(u"Invalid LTI Request")
            return HttpResponseBadRequest(u"Invalid LTI Request: " + e.message)

        request.session[cls.SESSION_KEY] = lti_parameters
        request.session.save()
        return HttpResponseRedirect(cls.authentication_manager.anonymous_redirect_to(request, lti_parameters))

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
        if cls.SESSION_KEY in request.session and not cls._is_new_lti_request(request):
            lti_parameters = request.session[cls.SESSION_KEY]
            del request.session[cls.SESSION_KEY]
        else:
            try:
                lti_parameters = cls._get_lti_parameters_from_request(request)
            except oauth2.Error, e:
                _logger.exception(u"Invalid LTI Request")
                return HttpResponseBadRequest(u"Invalid LTI Request: " + e.message)

        lti_data = LtiUserData.store_lti_parameters(
            request.user, cls.authentication_manager, cls.lti_param_filter(lti_parameters)
        )
        Signals.LTI.received.send(cls, user=request.user, lti_data=lti_data)

        return HttpResponseRedirect(cls.authentication_manager.authenticated_redirect_to(request, lti_parameters))

    @classmethod
    def _is_new_lti_request(cls, request):
        return 'lis_result_sourcedid' in request.POST
