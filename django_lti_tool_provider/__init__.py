from abc import ABCMeta, abstractmethod
import logging
from django.core.urlresolvers import resolve
from six import add_metaclass


logging.getLogger("").addHandler(logging.NullHandler())


@add_metaclass(ABCMeta)
class AbstractApplicationHookManager(object):
    """ Class that performs authentication and redirection for LTI views """
    @abstractmethod
    def authentication_hook(self, request, user_id=None, username=None, email=None):
        """ Hook to authenticate user from data available in LTI request """

    @abstractmethod
    def authenticated_redirect_to(self, request, lti_data):
        """ Callback to determine redirect URL for authenticated LTI request """

    def anonymous_redirect_to(self, request, lti_data):
        """ Callback to determine redirect URL for non-authenticated LTI request """
        return resolve('lti')

    def vary_by_key(self, request, lti_data):
        """
        Gets value for a key to vary LTI requests and responses by.
        If omitted, requests are varied by user - so only it allows for single outcome point to be used throughout
        the application.

        If specified it should be unique, but stable (i.e. not guid), string for any outcome point.
        """
        pass