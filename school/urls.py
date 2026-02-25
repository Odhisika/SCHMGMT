from django.urls import path
from .views import (
    SchoolListView,
    SchoolCreateView,
    SchoolUpdateView,
    school_onboarding,
    school_switch,
    # Settings views
    school_settings,
    school_settings_identity,
    school_settings_grading,
    school_settings_promotion,
    promotion_requests_list,
    promotion_request_review,
    submit_promotion_request,
    run_promotion_engine,
)

urlpatterns = [
    # Legacy school management (superuser only)
    path("list/", SchoolListView.as_view(), name="school_list"),
    path("add/", SchoolCreateView.as_view(), name="add_school"),
    path("onboard/", school_onboarding, name="school_onboarding"),
    path("update/<int:pk>/", SchoolUpdateView.as_view(), name="edit_school"),
    path("switch/<str:school_slug>/", school_switch, name="school_switch"),

    # School Settings Hub (school admin)
    path("settings/", school_settings, name="school_settings"),
    path("settings/identity/", school_settings_identity, name="school_settings_identity"),
    path("settings/grading/", school_settings_grading, name="school_settings_grading"),
    path("settings/promotion/", school_settings_promotion, name="school_settings_promotion"),

    # Promotion Requests
    path("settings/promotions/", promotion_requests_list, name="promotion_requests_list"),
    path("settings/promotions/<int:pk>/review/", promotion_request_review, name="promotion_request_review"),
    path("settings/promotions/run/", run_promotion_engine, name="run_promotion_engine"),
    path("settings/promotions/request/<int:result_pk>/", submit_promotion_request, name="submit_promotion_request"),
]
