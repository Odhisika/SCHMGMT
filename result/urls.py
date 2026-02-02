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
)


urlpatterns = [
    path("manage-score/", add_score, name="add_score"),
    path("manage-score/<int:id>/", add_score_for, name="add_score_for"),
    path("grade/", grade_result, name="grade_results"),
    path("assessment/", assessment_result, name="ass_results"),
    path("result/print/<int:id>/", result_sheet_pdf_view, name="result_sheet_pdf_view"),
    path("report-card/<int:pk>/pdf/", report_card_pdf_view, name="report_card_pdf"),
    path("report-cards/", report_cards, name="report_cards"),
    path(
        "registration/form/", course_registration_form, name="course_registration_form"
    ),
]
