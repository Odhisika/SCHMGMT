from django.urls import path
from .views import (
    add_score,
    add_score_for,
    grade_result,
    assessment_result,
    course_registration_form,
    result_sheet_pdf_view,
    report_card_pdf_view,
    report_cards,
    create_promotion,
    result_amendment_requests,
    # New views
    manage_scores_dashboard,
    enter_scores,
    save_scores,
)


urlpatterns = [
    path("manage-score/", add_score, name="add_score"),
    path("manage-score/<int:id>/", add_score_for, name="add_score_for"),
    path("manage-score/requests/", result_amendment_requests, name="result_amendment_requests"),
    
    # New Teacher Score Entry System
    path("manage-scores/", manage_scores_dashboard, name="manage_scores"),
    path("enter-scores/<str:level>/", enter_scores, name="enter_scores"),
    path("save-scores/", save_scores, name="save_scores"),

    path("grade/", grade_result, name="grade_results"),
    path("assessment/", assessment_result, name="ass_results"),
    path("result/print/<int:id>/", result_sheet_pdf_view, name="result_sheet_pdf_view"),
    path("report-card/<int:pk>/pdf/", report_card_pdf_view, name="report_card_pdf"),
    path("report-cards/", report_cards, name="report_cards"),
    path("promotion/", create_promotion, name="create_promotion"),
    path(
        "registration/form/", course_registration_form, name="course_registration_form"
    ),
]
