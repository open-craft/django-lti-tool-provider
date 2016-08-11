# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.db.models import Max
from django.db.models.functions import Length

def check_field_max_length_lteq_190(apps, schema_editor):
    """
    Check to see if we've got any data in the table that prevents us from
    migrating the length of the column down to 190; if so, raise an exception.
    """
    LtiUserData = apps.get_model('django_lti_tool_provider', 'LtiUserData')
    max_custom_key_length = LtiUserData.objects.aggregate(length=Max(Length('custom_key')))['length']
    if max_custom_key_length > 190:
        raise ValueError('Cannot perform migration: values of \'custom_key\' with length '
                         '{} exceed the expected length 190.'.format(max_custom_key_length))


class Migration(migrations.Migration):
    """
    Note that this migration is a no-op for instances created using the current
    state of the initial migration. However, a previous version of the initial
    migration set the maximum length of 'LtiUserData.custom_key' to 400, which is
    longer than allowed for a MySQL 5.5 CharField. Thus, this migration is intended
    to bring databases set up by the previous version of the initial migration
    into parity with databases set up by the current version.
    """

    dependencies = [
        ('django_lti_tool_provider', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            code=check_field_max_length_lteq_190
        ),
        migrations.RunSQL(
            sql=migrations.RunSQL.noop,
            state_operations=[
                # This is a shim. Django is oh-so-efficient, so if it detects
                # that the database should be in a state based on previous migrations,
                # it won't perform the operations to move to that state. This tells
                # Django "hey, I'm in this different state" without actually modifying
                # the database. This is not a reversible operation.
                migrations.AlterField(
                    model_name='ltiuserdata',
                    name='custom_key',
                    field=models.CharField(default=b'', max_length=400)
                )
            ],
        ),
        migrations.AlterField(
            model_name='ltiuserdata',
            name='custom_key',
            field=models.CharField(default=b'', max_length=190),
        ),
    ]
