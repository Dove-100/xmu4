from django.urls import path
from . import views

# urls.py
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # 登录相关
    path('login/', views.LoginView.as_view(), name='login'),
    path('2fa/setup/', views.TwoFactorSetupView.as_view(), name='2fa_setup'),
    path('2fa/confirm/', views.VerifyAndEnable2FAView.as_view(), name='2fa_confirm'),
    path('admin/reset2fa/', views.Reset2faView.as_view(), name='admin_reset2fa'),
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
    path('admin/reset_password/', views.AdminResetPasswordView.as_view(), name='admin_reset_password'),
    path('admin/export-users/', views.ExportUsersView.as_view(), name='export-users'),

    path('feedback/create/', views.CreateFeedbackView.as_view(), name='feedback_list'),
    path('feedback/list/', views.ListFeedbacksView.as_view(), name='feedback_update'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    print(f"✅ 媒体文件服务已启用: {settings.MEDIA_URL} -> {settings.MEDIA_ROOT}")