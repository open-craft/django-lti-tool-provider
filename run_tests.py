#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run tests for the Problem Builder XBlock
This script is required to run our selenium tests inside the xblock-sdk workbench
because the workbench SDK's settings file is not inside any python module.
"""

import os
import sys

if __name__ == "__main__":
    from django.conf import settings
    settings.INSTALLED_APPS += ("lti_tool_provider", )

    from django.core.management import execute_from_command_line
    args = sys.argv[1:]
    paths = [arg for arg in args if arg[0] != '-']
    if not paths:
        paths = ["lti/tests/"]
    options = [arg for arg in args if arg not in paths]
    execute_from_command_line([sys.argv[0], "test"] + paths + options)