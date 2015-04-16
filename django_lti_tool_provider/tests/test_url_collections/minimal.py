from django.conf.urls import patterns, url

from django_lti_tool_provider import views as lti_views

urlpatterns = patterns(
    '',
    url(r'', lti_views.LTIView.as_view(), name='home'),
    url(r'other_url', lti_views.LTIView.as_view(), name='not_a_home'),
    url(r'^lti$', lti_views.LTIView.as_view(), name='lti')
)