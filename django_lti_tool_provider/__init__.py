from abc import ABCMeta, abstractmethod
import logging
from django.core.urlresolvers import resolve
from six import add_metaclass


logging.getLogger("").addHandler(logging.NullHandler())


@add_metaclass(ABCMeta)
class AbstractAuthenticationManager(object):
    """ Class that performs authentication and redirection for LTI views """

    @abstractmethod
    def authentication_hook(self, request, user_id=None, username=None, email=None):
        """ Hook to authenticate user from data available in LTI request """

    def anonymous_redirect_to(self, request, lti_data):
        """ Callback to determine redirect URL for non-authenticated LTI request """
        return resolve('lti')

    @abstractmethod
    def authenticated_redirect_to(self, request, lti_data):
        """ Callback to determine redirect URL for authenticated LTI request """