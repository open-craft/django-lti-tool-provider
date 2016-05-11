from abc import ABCMeta, abstractmethod
import logging
from django.core.urlresolvers import resolve
from six import add_metaclass


logging.getLogger("").addHandler(logging.NullHandler())


# pylint: disable=unused-argument
# This class specifies method signatures; while pylint is intelligent enough to ignore unused args in abstractmethods
# methods with default implementations are still reported. Hence we suppress unused-argument for entire class
@add_metaclass(ABCMeta)
class AbstractApplicationHookManager(object):
    """ Class that performs authentication and redirection for LTI views """
    @abstractmethod
    def authentication_hook(self, request, user_id=None, username=None, email=None, **kwargs):
        """ Hook to authenticate user from data available in LTI request """

    @abstractmethod
    def authenticated_redirect_to(self, request, lti_data):
        """ Callback to determine redirect URL for authenticated LTI request """

    def anonymous_redirect_to(self, request, lti_data):
        """ Callback to determine redirect URL for non-authenticated LTI request """
        return resolve('lti')

    def vary_by_key(self, lti_data):
        """
        Gets value for a key to vary LTI requests and responses by.
        If omitted, requests are varied by user - so only it allows for single outcome point to be used throughout
        the application.

        If specified it should be unique, but stable (i.e. not guid), string for any outcome point.

        Note that since it is directly written to the DB and participates in composite unique key, some constraints
        need to be fulfilled:

        * Non is treated as empty string - several databases (PostgreSQL, MySQL) treats NULL as not equal to any
        other NULL, it might result in unexpected behavior (e.g. creating multiple rows with NULL).
        * It should not exceed 400 symbols - the length of field in DB as unique index restrictions are stricter then
        ordinary field.
        """
        return None

    def optional_lti_parameters(self):
        """
        Return a dictionary of LTI parameters supported/required by this AuthenticationHookManager in addition
        to user_id, username and email. These parameters are passed to authentication_hook method via kwargs.

        This dictionary should have LTI parameter names (as specified by LTI specification) as keys; values are used
        as parameter names passed to authentication_hook method, i.e. it allows renaming (not always intuitive) LTI spec
        parameter names.

        Example:
            # renames lis_person_name_given -> user_first_name, lis_person_name_family -> user_lat_name
            {'lis_person_name_given': 'user_first_name', 'lis_person_name_family': 'user_lat_name'}
        """
        return {}
