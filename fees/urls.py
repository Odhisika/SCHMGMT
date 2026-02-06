from django.urls import path
from . import views
from .receipt_views import download_payment_receipt

app_name = 'fees'

urlpatterns = [
    # Dashboard
    path('', views.payment_dashboard, name='dashboard'),
    
    # Admin views
    path('fees/', views.fee_structure_list, name='fee_list'),
    path('fees/add/', views.fee_structure_create, name='fee_create'),
    path('fees/<int:pk>/edit/', views.fee_structure_edit, name='fee_edit'),
    path('fees/<int:pk>/delete/', views.fee_structure_delete, name='fee_delete'),
    path('fees/<int:pk>/duplicate/', views.duplicate_fee_structure, name='fee_duplicate'),
    
    path('record/', views.record_manual_payment, name='record_payment'),
    path('record/<int:student_id>/', views.record_manual_payment, name='record_payment_student'),
    path('verify/<int:payment_id>/', views.verify_payment, name='verify_payment'),
    path('history/<int:student_id>/', views.payment_history, name='payment_history'),
    
    # Student search API
    path('api/student-search/', views.student_search_api, name='student_search_api'),
    
    # Bank account management
    path('bank-accounts/', views.bank_account_list, name='bank_account_list'),
    path('bank-accounts/add/', views.bank_account_create, name='bank_account_create'),
    path('bank-accounts/<int:pk>/edit/', views.bank_account_edit, name='bank_account_edit'),
    path('bank-accounts/<int:pk>/toggle/', views.bank_account_toggle, name='bank_account_toggle'),
    
    # Payment reference lookup
    path('reference-lookup/', views.payment_reference_lookup, name='payment_reference_lookup'),
    
    # PDF Receipt download
    path('payment/<int:payment_id>/receipt/', download_payment_receipt, name='download_receipt'),
    
    # Paystack
    path('pay/<int:assignment_id>/', views.initiate_paystack_payment, name='initiate_payment'),
    path('callback/', views.paystack_callback, name='paystack_callback'),
]
