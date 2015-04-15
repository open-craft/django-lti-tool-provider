from django.views.generic import View
import oauth2
import logging

from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.core.urlresolvers import reverse
from django.conf import settings

from ims_lti_py.tool_provider import DjangoToolProvider

from django_lti_tool_provider.models import LtiUserData
from django_lti_tool_provider.signals import Signals


_logger = logging.getLogger(__name__)


class LTIView(View):
    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super(LTIView, self).dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        return self.process_request(request)

    def post(self, request, *args, **kwargs):
        return self.process_request(request)

    def process_request(self, request):
        if request.user.is_authenticated():
            return self.process_authenticated_lti(request)
        else:
            return self.process_anonymous_lti(request)

    def process_anonymous_lti(self, request):
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
        return HttpResponseRedirect(
            "{login}?next={lti_handler}".format(
                login=reverse('django.contrib.auth.views.login'),
                lti_handler=request.path.strip('/')
            )
        )

    def process_authenticated_lti(self, request):
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
                provider = DjangoToolProvider(settings.CONSUMER_KEY, settings.LTI_SECRET, request.POST)
                provider.valid_request(request)
                lti_parameters = provider.to_params()
            except oauth2.Error, e:
                _logger.exception(u"Invalid LTI Request")
                return HttpResponseBadRequest("Invalid LTI Request: " + e.message)

        lti_data = self._store_lti_parameters(request.user, lti_parameters)
        Signals.LTI.received.send(self.__class__, user=request.user, lti_data=lti_data)

        return HttpResponseRedirect(reverse(settings.REDIRECT_AFTER_LTI))

    def _store_lti_parameters(self, user, parameters):
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
