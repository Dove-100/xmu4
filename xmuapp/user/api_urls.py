from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('teacher/information/', views.teacher_information, name='teacher_profile'),
    path('query/', views.AdminAccountListView.as_view(), name='query'),
    path('admin/create/teacher/', views.TeacherRegistrationView.as_view(), name='admin_create'),
    path('admin/create/student/', views.StudentRegistrationView.as_view(), name='admin_create'),
    path('admin/retrieve/', views.UserDetailView.as_view(), name='admin_retrieve'),
    path('admin/retrieve/history/', views.teacher_review_history, name='admin_retrieve_history'),
    path('admin/import_student/', views.BulkStudentRegistrationViewV2.as_view(), name='admin_import_users'),
    path('admin/download_stu_template/', views.DownloadStudentTemplateView.as_view(), name='admin_update'),
    path('admin/import_teacher/', views.BulkTeacherRegistrationView.as_view(), name='admin_import_users'),
    path('admin/download_tea_template/', views.DownloadTeacherTemplateView.as_view(), name='admin_update'),
    path('update/contact/', views.UserContactUpdateView.as_view(), name='student_update'),
    path('user/change-password/', views.ChangePasswordView.as_view(), name='user_change_password'),
    path('admin/destroy/', views.DeleteUserView.as_view(), name='admin_destroy'),
]