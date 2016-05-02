import logging

from django.db import models
from django.contrib.auth.models import User
from jsonfield import JSONField

from ims_lti_py.tool_provider import DjangoToolProvider
from django.conf import settings


_logger = logging.getLogger(__name__)


class WrongUserError(Exception):
    pass


class LtiUserData(models.Model):
    user = models.ForeignKey(User)
    edx_lti_parameters = JSONField(default={})
    custom_key = models.CharField(max_length=190, null=False, default='')

    class Meta:
        app_label = "django_lti_tool_provider"
        unique_together = (("user", "custom_key"),)

    @property
    def _required_params(self):
        return ["lis_result_sourcedid", "lis_outcome_service_url"]

    def _validate_lti_grade_request(self, grade):
        def _log_and_throw(message):
            _logger.error(message)
            raise ValueError(message)

        if not 0 <= grade <= 1:
            _log_and_throw("Grade should be in range [0..1], got {grade}".format(grade=grade))

        if not self.edx_lti_parameters:
            _log_and_throw("LTI grade parameters is not set".format(params=self._required_params))

        empty_parameters = [
            parameter for parameter in self._required_params
            if not self.edx_lti_parameters.get(parameter, '')
        ]

        if empty_parameters:
            parameters_repr = ", ".join(empty_parameters)
            _log_and_throw(
                "Following required LTI parameters are not set: {parameters}".format(parameters=parameters_repr)
            )

    def send_lti_grade(self, grade):
        """ Instantiates DjangoToolProvider using stored lti parameters and sends grade """
        self._validate_lti_grade_request(grade)
        provider = DjangoToolProvider(settings.LTI_CLIENT_KEY, settings.LTI_CLIENT_SECRET, self.edx_lti_parameters)
        outcome = provider.post_replace_result(grade)

        _logger.info(u"LTI grade request was {successful}. Description is {description}".format(
            successful="successful" if outcome.is_success() else "unsuccessful", description=outcome.description
        ))

        return outcome

    @classmethod
    def get_or_create_by_parameters(cls, user, authentication_manager, lti_params, create=True):
        """
        Gets a user's LTI user data, creating the user if they do not exist. If create is False,
        it will raise LtiUserData.DoesNotExist should no data exist for the user.

        This function also does a bit of sanity checking to make sure the current user_id matches
        the stored lti user_id, raising WrongUserError if not.
        """
        custom_key = authentication_manager.vary_by_key(lti_params)

        # implicitly tested by test_views
        if custom_key is None:
            custom_key = ''

        if create:
            lti_user_data, created = LtiUserData.objects.get_or_create(user=user, custom_key=custom_key)
        else:
            # Could omit it, but it would change the signature.
            created = False
            lti_user_data = LtiUserData.objects.get(user=user, custom_key=custom_key)

        if lti_user_data.edx_lti_parameters.get('user_id', lti_params['user_id']) != lti_params['user_id']:
            # TODO: not covered by test
            message = u"LTI parameters for user found, but anonymous user id does not match."
            _logger.error(message)
            raise WrongUserError(message)

        return lti_user_data, created

    @classmethod
    def store_lti_parameters(cls, user, authentication_manager, lti_params):
        """
        Stores LTI parameters into the DB, creating or updating record as needed
        """
        lti_user_data, created = cls.get_or_create_by_parameters(user, authentication_manager, lti_params)
        lti_user_data.edx_lti_parameters = lti_params
        if not created:
            _logger.debug(u"Replaced LTI parameters for user %s", user.username)
        lti_user_data.save()
        return lti_user_data
