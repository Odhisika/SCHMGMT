from django.urls import path
from .views import (
    SchoolListView, 
    SchoolCreateView, 
    SchoolUpdateView, 
    school_onboarding,
    school_switch
)

urlpatterns = [
    path("list/", SchoolListView.as_view(), name="school_list"),
    path("add/", SchoolCreateView.as_view(), name="add_school"),
    path("onboard/", school_onboarding, name="school_onboarding"),
    path("update/<int:pk>/", SchoolUpdateView.as_view(), name="edit_school"),
    path("switch/<str:school_slug>/", school_switch, name="school_switch"),
]
