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


# views.py - 添加分数计算和排名API
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import time


@method_decorator(csrf_exempt, name='dispatch')
class CalculateScoresView(APIView):
    """计算分数API"""

    permission_classes = [IsAuthenticated]

    def put(self, request):
        """批量计算分数"""
        print("=== 批量计算分数请求 ===")
        print(f"👤 请求用户: {request.user.school_id}")

        # 权限验证（仅超管）
        if request.user.user_type != 2:
            return Response({'error': '权限不足'}, status=403)

        try:
            # 获取参数
            dimension = request.data.get('dimension', '专业')
            action = request.data.get('action', 'all')  # all, academic, total, ranking

            start_time = time.time()
            results = {}

            # 执行计算
            from services.score_calculation import ScoreCalculationService

            if action in ['all', 'academic']:
                academic_count = ScoreCalculationService.batch_calculate_academic_scores()
                results['academic_score_updated'] = academic_count

            if action in ['all', 'total']:
                total_count = ScoreCalculationService.batch_calculate_total_scores()
                results['total_score_updated'] = total_count

            if action in ['all', 'ranking']:
                ranking_count = ScoreCalculationService.batch_update_rankings(dimension)
                results['ranking_updated'] = ranking_count

            elapsed_time = time.time() - start_time

            return Response({
                'success': True,
                'message': f'分数计算完成，耗时{elapsed_time:.2f}秒',
                'results': results,
                'dimension': dimension,
                'action': action
            })

        except Exception as e:
            print(f"❌ 分数计算API错误: {e}")
            import traceback
            traceback.print_exc()
            return Response({
                'error': f'计算失败: {str(e)}'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class StudentRankingView(APIView):
    """学生排名查询API"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """查询学生排名"""
        print("=== 学生排名查询 ===")

        school_id = request.query_params.get('school_id')
        dimension = request.query_params.get('dimension', '专业')

        try:
            if school_id:
                # 查询特定学生
                from user.models import User
                user = User.objects.get(school_id=school_id)

                # 安全获取成绩记录
                try:
                    academic = user.academic_performance
                except:
                    return Response({
                        'error': f'学生 {school_id} 无成绩记录'
                    }, status=404)

                # 如果未计算排名，则计算
                if academic.current_rank is None:
                    academic.update_ranking(dimension)

                return Response({
                    'school_id': user.school_id,
                    'name': user.name,
                    'college': user.college,
                    'major': user.major,
                    'gpa': float(academic.gpa) if academic.gpa else 0,
                    'academic_score': float(academic.academic_score) if academic.academic_score else 0,
                    'total_comprehensive_score': float(
                        academic.total_comprehensive_score) if academic.total_comprehensive_score else 0,
                    'rank': academic.current_rank,
                    'ranking_dimension': academic.ranking_dimension,
                    'total_in_dimension': academic.total_students_in_dimension
                })
            else:
                # 查询排名列表
                from .models import AcademicPerformance

                page = int(request.query_params.get('page', 1))
                page_size = min(int(request.query_params.get('page_size', 50)), 100)

                # 构建查询
                queryset = AcademicPerformance.objects.filter(
                    total_comprehensive_score__isnull=False
                ).select_related('user')

                # 维度过滤
                if dimension == '专业':
                    # 这里可以根据需要添加专业过滤
                    pass
                elif dimension == '学院':
                    college = request.query_params.get('college')
                    if college:
                        queryset = queryset.filter(user__college=college)

                # 排序
                queryset = queryset.order_by('-total_comprehensive_score')

                # 分页
                total = queryset.count()
                start = (page - 1) * page_size
                end = start + page_size

                rankings = []
                for idx, perf in enumerate(queryset[start:end], start=start + 1):
                    rankings.append({
                        'rank': idx,
                        'school_id': perf.user.school_id,
                        'name': perf.user.name,
                        'college': perf.user.college,
                        'major': perf.user.major,
                        'gpa': float(perf.gpa) if perf.gpa else 0,
                        'academic_score': float(perf.academic_score) if perf.academic_score else 0,
                        'total_comprehensive_score': float(
                            perf.total_comprehensive_score) if perf.total_comprehensive_score else 0
                    })

                return Response({
                    'page': page,
                    'page_size': page_size,
                    'total': total,
                    'total_pages': (total + page_size - 1) // page_size,
                    'dimension': dimension,
                    'rankings': rankings
                })

        except User.DoesNotExist:
            return Response({'error': '用户不存在'}, status=404)
        except Exception as e:
            print(f"❌ 排名查询错误: {e}")
            return Response({'error': str(e)}, status=500)