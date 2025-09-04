from django.urls import path, include
from . import views

urlpatterns = [
    # Authentication
    path('', views.citizen_login, name='citizen_login'),
    path('verify/', views.verify_code, name='verify_code'),
    path('logout/', views.logout_view, name='logout'),

    
    # Citizen routes
    path('dashboard/', views.citizen_dashboard, name='citizen_dashboard'),
    path('calculator/', views.eligibility_calculator, name='eligibility_calculator'),
    path('reclamation/create/<int:possession_id>/', views.create_reclamation, name='create_reclamation'),
    path('reclamations/', views.my_reclamations, name='my_reclamations'),
    path('applications/', views.my_applications, name='my_applications'),
    path('apply/<str:program_type>/', views.create_application, name='create_application'),
    
    # Staff routes
    path('staff/', views.staff_dashboard, name='staff_dashboard'),
    path('staff/citizens/', views.manage_citizens, name='manage_citizens'),
    path('staff/citizen/<int:citizen_id>/', views.citizen_detail, name='citizen_detail'),
    path('staff/possessions/add/<int:citizen_id>/', views.add_possession, name='add_possession'),
    path('staff/reclamation/assign/<uuid:reclamation_id>/', views.assign_reclamation, name='assign_reclamation'),
    path('staff/investigation/<uuid:reclamation_id>/', views.investigate_reclamation, name='investigate_reclamation'),
    path('staff/possessions/edit/<int:possession_id>/', views.edit_possession, name='edit_possession'),
    path('staff/possessions/delete/<int:possession_id>/', views.delete_possession, name='delete_possession'),
    path('staff/applications/review/', views.review_applications, name='review_applications'),
    path('staff/application/<uuid:application_id>/review/', views.review_application, name='review_application'),
    
    # Admin routes
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('admin-panel/possession-types/', views.manage_possession_types, name='manage_possession_types'),
    path('admin-panel/audit-logs/', views.audit_logs, name='audit_logs'),
    
    # AJAX API routes
    path('api/possession-types-by-category/<int:category_id>/', views.get_possession_types_by_category, name='get_possession_types_by_category'),
    path('api/possession-types/<int:category_id>/', views.get_possession_types, name='get_possession_types'),
    path('api/calculate-score/', views.calculate_score_ajax, name='calculate_score_ajax'),
    path("__reload__/", include("django_browser_reload.urls")),

]
