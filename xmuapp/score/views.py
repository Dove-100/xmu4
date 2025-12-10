# score/views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model

User = get_user_model()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_student_scores(request):
    """
    学生获取个人成绩接口
    """
    from .serializers import StudentScoreSerializer

    if not request.user.is_student:
        return Response({
            "error": "权限不足，只有学生可以查看个人成绩"
        }, status=status.HTTP_403_FORBIDDEN)

    try:
        # 修复字段名：academic_performance 而不是 academicperformance
        user = User.objects.select_related('academic_performance').get(id=request.user.id)
        serializer = StudentScoreSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except User.DoesNotExist:
        return Response({
            "error": "用户不存在"
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            "error": "获取成绩信息失败",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)