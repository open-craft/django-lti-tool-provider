from django.conf.urls import url

from django_lti_tool_provider import views as lti_views


app_name = 'django_lti_tool_provider'

urlpatterns = [
    url(r'', lti_views.LTIView.as_view(), name='lti')
]
