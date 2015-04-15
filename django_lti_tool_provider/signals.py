import logging

from django.dispatch import Signal, receiver

from django_lti_tool_provider.models import LtiUserData


_logger = logging.getLogger(__name__)


class Signals(object):
    class Grade(object):
        updated = Signal(providing_args=["user", "new_grade"])

    class LTI(object):
        received = Signal(providing_args=["user", "lti_data"])


@receiver(Signals.Grade.updated, dispatch_uid="django_lti_grade_updated")
def grade_updated_handler(sender, **kwargs):
    user = kwargs.get('user', None)
    grade = kwargs.get('grade', None)
    _send_grade(user, grade)


def _send_grade(user, grade, strict=True):
    try:
        if user is None:
            raise ValueError(u"User is not specified")
        lti_user_data = LtiUserData.objects.get(user=user)
        lti_user_data.send_lti_grade(grade)
    except LtiUserData.DoesNotExist:
        _logger.info(
            u"No LTI parameters for user {user} stored - probably never sent an LTI request"
            .format(user=user.username)
        )
        if strict:
            raise
    except Exception:
        _logger.exception(u"Exception occurred in lti module when sending grade for user {user}.".format(user=user))
        if strict:
            raise
