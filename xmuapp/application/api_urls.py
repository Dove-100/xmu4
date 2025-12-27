from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from . import views

urlpatterns = [
    path('applications/fileupload/', views.SimpleFileUploadView.as_view(), name='file-upload'),
    path('applications/filedownload/', views.FileDownloadByHashView.as_view(), name='file-download'),
    path('applications/filedelete/', views.FileDeleteView.as_view(), name='file-delete'),
    # path('files/<uuid:file_id>/', views.FileDetailView.as_view(), name='file-detail'),
    path('applications/create/', views.ApplicationCreateView.as_view(), name='create-application'),
    path('applications/list/', views.ApplicationListView.as_view(), name='application-list'),
    path('applications/detail/', views.ApplicationDetailByQueryView.as_view(), name='application-detail'),
    path('applications/destroy/', views.ApplicationDeleteView.as_view(), name='application-destroy'),
    path('applications/update/', views.ApplicationUpdateSimpleView.as_view(), name='application-update'),
    path('applications/withdraw/', views.ApplicationRevertToDraftView.as_view(), name='application-withdraw'),

    path('reviews/pending_list/', views.get_pending_applications, name='review-list'),
    path('reviews/first_review/', views.teacher_review_application_with_score, name='review-first'),
    path('reviews/withdraw/', views.teacher_revoke_review ,name='review-withdraw'),
    path('reviews/edit/', views.teacher_update_review_with_score, name='review-edit'),
    path('reviews/history/', views.teacher_review_history, name='review-history'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    print(f"✅ 媒体文件服务已启用: {settings.MEDIA_URL} -> {settings.MEDIA_ROOT}")