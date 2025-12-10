import json
import logging
import os

from django.contrib.auth.hashers import check_password
from django.db import models
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, permissions
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import LoginSerializer, AdminAccountListRequestSerializer, AdminAccountListSerializer, \
    UniversalStudentDetailSerializer, SafeTeacherPendingApplicationListSerializer, UserContactUpdateSerializer, \
    ChangePasswordSerializer, BulkUserImportSerializer, StudentRegistrationSerializer, TeacherRegistrationSerializer, \
    TeacherDetailSerializer
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from django.shortcuts import get_object_or_404
from .models import User
from score.models import AcademicPerformance
from application.models import Application, Attachment
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import update_session_auth_hash

import pandas as pd
from django.db import transaction
from rest_framework.parsers import MultiPartParser, FormParser

User = get_user_model()

class LoginView(APIView):
    permission_classes = []

    def post(self, request):
        data = request.data
        print(data)
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user_id': user.id,
                'school_id': user.school_id,
                'name': user.name,
                'user_type': user.user_type,
                'college': user.college,
                'contact': user.contact,
                'email': user.email,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_information(request):
    """
    获取教师个人信息
    对应URL: /api/account/teacher/information/
    """
    try:
        # 验证教师权限
        if not hasattr(request.user, 'is_teacher') or not request.user.is_teacher:
            return Response({
                "error": "权限不足，只有教师可以访问此接口"
            }, status=status.HTTP_403_FORBIDDEN)

        user = request.user

        # 安全地获取字段值
        teacher_data = {
            "id": str(user.id),
            "school_id": getattr(user, 'school_id', '未设置'),
            "name": getattr(user, 'name', '未设置'),
            "college": getattr(user, 'college', '未设置'),
            "title": getattr(user, 'title', '未设置'),
            "contact": getattr(user, 'contact', '未设置')
        }

        # 调试信息（生产环境可以移除）
        print(f"获取教师信息: {teacher_data}")

        return Response(teacher_data)

    except AttributeError as e:
        return Response({
            "error": f"用户模型字段缺失: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({
            "error": f"获取教师信息失败: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminAccountListView(APIView):
    """
    超级管理员获取账号列表接口
    """
    permission_classes = [IsAuthenticated]

    def check_permissions(self, request):
        """检查权限 - 只有超级管理员可以访问"""
        super().check_permissions(request)

        if not request.user.is_admin:
            self.permission_denied(
                request,
                message="权限不足，只有超级管理员可以访问此接口"
            )

    def get(self, request):
        """
        获取账号列表
        """
        try:
            print("=== 管理员获取账号列表请求 ===")
            print(f"请求用户: {request.user.name} ({request.user.school_id})")
            print(f"查询参数: {request.GET}")

            # 验证请求参数
            serializer = AdminAccountListRequestSerializer(data=request.GET)
            if not serializer.is_valid():
                print(f"参数验证失败: {serializer.errors}")
                return Response({
                    "error": "参数验证失败",
                    "details": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data
            user_type = validated_data['type']  # 0-学生, 1-老师
            major_filter = validated_data['major']

            print(f"用户类型: {'学生' if user_type == 0 else '老师'}")
            print(f"专业过滤: {major_filter}")

            # 直接使用user_type作为查询条件
            queryset = User.objects.filter(user_type=user_type)

            # 专业过滤 (仅对学生有效)
            if user_type == 0:  # 学生
                if major_filter not in [-1, 4]:  # 具体专业
                    major_mapping = {
                        0: '计算机科学与技术',
                        1: '软件工程',
                        2: '人工智能',
                        3: '网络安全'
                    }
                    major_name = major_mapping.get(major_filter)
                    if major_name:
                        queryset = queryset.filter(major=major_name)

            # 预取关联数据 - 只有学生需要预取成绩
            if user_type == 0:  # 学生
                queryset = queryset.prefetch_related('academic_performance')

            # 排序
            queryset = queryset.order_by('school_id')

            print(f"查询结果数量: {queryset.count()}")

            # 使用修复后的序列化器
            account_serializer = AdminAccountListSerializer(queryset, many=True)

            # 构建响应数据
            response_data = {
                "AccountList": account_serializer.data
            }

            print(
                f"=== 查询完成: 找到 {len(response_data['AccountList'])} 个{'学生' if user_type == 0 else '老师'} ===")

            # 调试：打印第一条数据的完整结构
            if response_data['AccountList']:
                first_item = response_data['AccountList'][0]
                print(f"第一条数据完整结构: {json.dumps(first_item, ensure_ascii=False, indent=2)}")

                # 检查Score字段是否存在
                has_score = 'Score' in first_item
                print(f"Score字段是否存在: {has_score}")
                if has_score:
                    print(f"Score值: {first_item['Score']}")
                print(f"Type值: {first_item['Type']}")

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"管理员获取账号列表错误: {str(e)}")
            import traceback
            print(f"错误堆栈: {traceback.format_exc()}")

            return Response({
                "error": "获取账号列表失败",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminAccountStatisticsView(APIView):
    """
    超级管理员获取账号统计信息接口
    GET /api/admin/accounts/statistics/
    """
    permission_classes = [IsAuthenticated]

    def check_permissions(self, request):
        """检查权限 - 只有超级管理员可以访问"""
        super().check_permissions(request)

        if not request.user.is_admin:
            self.permission_denied(
                request,
                message="权限不足，只有超级管理员可以访问此接口"
            )

    def get(self, request):
        """
        获取账号统计信息
        """
        try:
            # 统计各类型用户数量
            student_count = User.objects.filter(user_type=0).count()  # 学生
            teacher_count = User.objects.filter(user_type=1).count()  # 老师
            admin_count = User.objects.filter(user_type=2).count()  # 管理员

            # 统计各专业学生数量
            major_stats = User.objects.filter(user_type=0).values('major').annotate(
                count=models.Count('id')
            )

            # 格式化专业统计
            major_mapping = {
                '计算机科学与技术': '计科',
                '软件工程': '软工',
                '人工智能': '智能',
                '网络安全': '网安'
            }

            formatted_major_stats = {}
            for stat in major_stats:
                major_name = stat['major']
                display_name = major_mapping.get(major_name, major_name)
                formatted_major_stats[display_name] = stat['count']

            # 统计各学院用户数量
            college_stats = User.objects.values('college').annotate(
                total=models.Count('id'),
                students=models.Count('id', filter=models.Q(user_type=0)),
                teachers=models.Count('id', filter=models.Q(user_type=1)),
                admins=models.Count('id', filter=models.Q(user_type=2))
            )

            return Response({
                "statistics": {
                    "total_users": student_count + teacher_count + admin_count,
                    "students": student_count,
                    "teachers": teacher_count,
                    "admins": admin_count,
                    "major_distribution": formatted_major_stats,
                    "college_distribution": list(college_stats)
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"获取账号统计信息错误: {str(e)}")
            return Response({
                "error": "获取统计信息失败",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


logger = logging.getLogger(__name__)


class UserDetailView(APIView):
    """
    超管获取用户详情接口 (GET方法)
    type=0表示学生, type=1表示老师
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """根据type和id获取用户详情 - GET方法"""
        try:
            # 从查询参数中获取type和id
            user_type = request.GET.get('type')
            user_id = request.GET.get('id')

            logger.info(f"用户详情查询请求 - type: {user_type}, id: {user_id}")

            # 参数验证
            if user_type is None or not user_id:
                return Response({
                    'success': False,
                    'message': '参数type和id均为必需',
                    'required_params': {
                        'type': '0=学生, 1=老师',
                        'id': '学号/工号'
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

            # 验证用户类型
            try:
                user_type = int(user_type)
                if user_type not in [0, 1]:
                    raise ValueError
            except (ValueError, TypeError):
                return Response({
                    'success': False,
                    'message': 'type参数必须为0(学生)或1(老师)',
                    'received_type': user_type
                }, status=status.HTTP_400_BAD_REQUEST)

            # 查找用户（使用正确的prefetch_related）
            try:
                user = User.objects.select_related(
                    'academic_performance'
                ).prefetch_related(
                    'applications'  # 使用正确的related_name
                ).get(school_id=user_id, user_type=user_type)
            except User.DoesNotExist:
                user_type_text = "学生" if user_type == 0 else "教师"
                return Response({
                    'success': False,
                    'message': f'{user_type_text}不存在: {user_id}'
                }, status=status.HTTP_404_NOT_FOUND)

            # 根据用户类型返回不同数据
            if user_type == 0:  # 学生
                serializer = UniversalStudentDetailSerializer(user)
                user_type_text = "学生"
            else:  # 教师
                serializer = TeacherDetailSerializer(user)
                user_type_text = "教师"

            logger.info(f"用户详情查询成功: {user_id} (类型: {user_type_text})")

            return Response({
                'success': True,
                'message': f'获取{user_type_text}详情成功',
                'data': {
                    'type': user_type,
                    'type_text': user_type_text,
                    **serializer.data
                }
            })

        except Exception as e:
            logger.exception(f"用户详情查询异常: {str(e)}")
            return Response({
                'success': False,
                'message': f'获取用户详情失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_review_history(request):
    """
    获取老师审核历史记录
    通过query参数中的老师id获取他的审核记录
    超管可以查看任意老师，老师只能查看自己的记录
    """
    try:
        # 获取查询参数中的老师ID
        teacher_id = request.GET.get('teacher_id')

        if not teacher_id:
            return Response({
                "error": "缺少必要参数",
                "message": "teacher_id参数为必需"
            }, status=status.HTTP_400_BAD_REQUEST)

        # 验证老师是否存在
        try:
            teacher = User.objects.get(school_id=teacher_id, user_type=1)  # user_type=1表示老师
        except User.DoesNotExist:
            return Response({
                "error": "老师不存在",
                "message": f"未找到工号为 {teacher_id} 的老师"
            }, status=status.HTTP_404_NOT_FOUND)

        # 权限检查：超管可以查看任意老师，老师只能查看自己
        if not request.user.is_admin and request.user.school_id != teacher_id:
            return Response({
                "error": "权限不足",
                "message": "只能查看自己的审核记录"
            }, status=status.HTTP_403_FORBIDDEN)

        # 查询该老师的审核记录（审核通过和不通过）
        queryset = Application.objects.filter(
            review_status__in=[2, 3],  # 审核通过和不通过
            reviewed_by=teacher  # 指定老师的审核记录
        )

        # 应用过滤器
        application_type = request.GET.get('type')
        college = request.GET.get('college')
        student_name = request.GET.get('student_name')

        if application_type is not None:
            try:
                application_type = int(application_type)
                queryset = queryset.filter(Type=application_type)
            except (ValueError, TypeError):
                return Response({
                    "error": "申请类型参数格式错误"
                }, status=status.HTTP_400_BAD_REQUEST)

        if college:
            queryset = queryset.filter(user__college=college)

        if student_name:
            queryset = queryset.filter(
                Q(user__name__icontains=student_name) |  # 修正为name字段
                Q(user__school_id__icontains=student_name)
            )

        # 预取关联数据以提高性能
        queryset = queryset.select_related('user').order_by('-reviewed_at')

        # 序列化数据
        serializer = SafeTeacherPendingApplicationListSerializer(queryset, many=True)

        return Response({
            "teacher_info": {
                "teacher_id": teacher.school_id,
                "teacher_name": teacher.name,
                "college": teacher.college
            },
            "total_count": queryset.count(),
            "review_history": serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        import traceback
        print("Error in teacher_review_history:")
        print(traceback.format_exc())

        return Response({
            "error": "获取审核历史失败",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


logger = logging.getLogger(__name__)


class TeacherRegistrationView(APIView):
    """
    超管注册教师接口 - 修复版本
    """

    permission_classes = [IsAuthenticated]

    def check_permissions(self, request):
        """检查用户是否为超级管理员"""
        super().check_permissions(request)
        if not request.user.is_admin:
            # 确保这里返回 Response 而不是 None
            return Response({
                'success': False,
                'message': '权限不足：仅超级管理员可执行此操作'
            }, status=status.HTTP_403_FORBIDDEN)
        # 如果权限检查通过，返回 None 让流程继续

    def post(self, request):
        try:
            logger.info(f"教师注册请求数据: {request.data}")
            logger.info(f"请求用户: {request.user.school_id}, 类型: {request.user.user_type}")

            # 先检查权限（确保权限检查有返回值）
            permission_check = self.check_permissions(request)
            if permission_check is not None:
                return permission_check

            serializer = TeacherRegistrationSerializer(data=request.data)

            if serializer.is_valid():
                teacher = serializer.save()

                logger.info(f"教师注册成功: {teacher.school_id}")

                response_data = {
                    'success': True,
                    'message': '教师账号创建成功',
                    'data': {
                        'school_id': teacher.school_id,
                        'name': teacher.name,
                        'department': teacher.college,  # 使用存储的 college 字段
                        'user_type': '教师',
                        'initial_password': getattr(teacher, '_generated_password', '密码已设置'),
                        'registration_time': teacher.date_joined.isoformat()
                    }
                }

                return Response(response_data, status=status.HTTP_200_OK)

            else:
                logger.error(f"数据验证失败: {serializer.errors}")
                return Response({
                    'success': False,
                    'message': '数据验证失败',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.exception(f"教师注册异常: {str(e)}")
            return Response({
                'success': False,
                'message': f'注册教师失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


logger = logging.getLogger(__name__)


class StudentRegistrationView(APIView):
    """
    学生注册视图 - 支持多种字段名格式
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        注册学生账号
        支持前端多种字段名格式
        """
        try:
            print("=== 学生注册请求 ===")
            print(f"操作者: {request.user.school_id}")
            print(f"原始数据: {request.data}")

            # 🎯 权限检查
            if request.user.user_type != 2:
                return Response({
                    'success': False,
                    'message': '只有超级管理员可以注册学生',
                    'data': None
                }, status=status.HTTP_403_FORBIDDEN)

            # 🎯 数据标准化和字段映射
            normalized_data = self.normalize_student_data(request.data)
            print(f"标准化后数据: {normalized_data}")

            # 🎯 创建序列化器实例
            serializer = StudentRegistrationSerializer(data=normalized_data)

            if not serializer.is_valid():
                print(f"❌ 数据验证失败: {serializer.errors}")
                return Response({
                    'success': False,
                    'message': '数据验证失败',
                    'errors': serializer.errors,
                    'debug': {
                        'original_data': request.data,
                        'normalized_data': normalized_data
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

            print("✅ 数据验证通过")

            # 🎯 创建学生
            student = serializer.save()

            # 🎯 获取完整的响应数据
            response_data = self.build_response_data(student)

            print(f"✅ 学生注册完成: {student.school_id}")
            return Response({
                'success': True,
                'message': '学生账号创建成功',
                'data': response_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"❌ 注册异常: {e}")
            import traceback
            print(f"堆栈: {traceback.format_exc()}")
            return Response({
                'success': False,
                'message': f'注册失败: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def normalize_student_data(self, data):
        """
        标准化学生数据
        支持多种前端字段名格式
        """
        normalized = dict(data)

        # 🎯 字段名映射表（前端字段名 -> 数据库字段名）
        field_mappings = {
            # 绩点相关字段
            'academy_score': 'gpa',
            'academyScore': 'gpa',
            'AcademyScore': 'gpa',
            '绩点': 'gpa',
            'GPA': 'gpa',

            # 四级成绩字段
            'cet4_score': 'cet4',
            'CET4': 'cet4',
            '四级成绩': 'cet4',
            '英语四级': 'cet4',

            # 六级成绩字段
            'cet6_score': 'cet6',
            'CET6': 'cet6',
            '六级成绩': 'cet6',
            '英语六级': 'cet6',

            # 其他学业字段
            'academicScore': 'academic_score',
            '学业成绩': 'academic_score',

            # 部门字段（兼容旧格式）
            'department': None,  # 特殊处理
        }

        # 🎯 应用字段映射
        for old_field, new_field in field_mappings.items():
            if old_field in normalized:
                value = normalized.pop(old_field)

                if new_field:  # 直接映射
                    normalized[new_field] = value
                    print(f"字段映射: {old_field} -> {new_field} = {value}")
                else:  # 特殊处理（如department）
                    if old_field == 'department':
                        self.parse_department_field(normalized, value)

        # 🎯 特殊处理：如果传入的是academy_score但模型是gpa
        if 'academy_score' in normalized and 'gpa' not in normalized:
            normalized['gpa'] = normalized.pop('academy_score')
            print(f"特殊映射: academy_score -> gpa = {normalized['gpa']}")

        # 🎯 设置默认值
        defaults = {
            'grade': self.extract_grade_from_school_id(normalized.get('school_id', '')),
            'password': '123456',
            'gpa': 0.0000,
            'cet4': -1,  # -1表示未参加
            'cet6': -1,
            'academic_score': 0.0000,
            'weighted_score': 0.0000,
        }

        for field, default_value in defaults.items():
            if field not in normalized:
                normalized[field] = default_value
                print(f"设置默认值: {field} = {default_value}")

        return normalized

    def parse_department_field(self, normalized, department_str):
        """
        解析department字段：学院-系-专业
        """
        print(f"解析department字段: {department_str}")
        parts = department_str.split('-')

        if len(parts) >= 1 and 'college' not in normalized:
            normalized['college'] = parts[0].strip()
            print(f"从department提取学院: {normalized['college']}")

        if len(parts) >= 3 and 'major' not in normalized:
            normalized['major'] = parts[2].strip()
            print(f"从department提取专业: {normalized['major']}")
        elif len(parts) >= 2 and 'major' not in normalized:
            normalized['major'] = parts[1].strip()
            print(f"从department提取专业: {normalized['major']}")

    def extract_grade_from_school_id(self, school_id):
        """
        从学号中提取年级
        例如：2024001001 -> 2024
        """
        if school_id and len(school_id) >= 4:
            grade = school_id[:4]
            if grade.isdigit():
                return grade
        return "2024"  # 默认年级

    def build_response_data(self, student):
        """
        构建响应数据
        """
        # 用户基本信息
        user_info = {
            'id': str(student.id),
            'school_id': student.school_id,
            'name': student.name,
            'college': student.college,
            'major': student.major,
            'grade': student.grade,
            'user_type': student.get_user_type_display(),
            'created_at': student.date_joined.isoformat() if hasattr(student, 'date_joined') else None
        }

        # 学业成绩信息
        academic_info = {}
        if hasattr(student, 'academic_performance'):
            academic = student.academic_performance
            academic_info = {
                'gpa': float(academic.gpa) if academic.gpa else 0.0,
                'cet4': academic.cet4,
                'cet6': academic.cet6,
                'academic_score': float(academic.academic_score) if academic.academic_score else 0.0,
                'weighted_score': float(academic.weighted_score) if academic.weighted_score else 0.0,
                'academic_expertise_score': float(
                    academic.academic_expertise_score) if academic.academic_expertise_score else 0.0,
                'comprehensive_performance_score': float(
                    academic.comprehensive_performance_score) if academic.comprehensive_performance_score else 0.0,
                'total_comprehensive_score': float(
                    academic.total_comprehensive_score) if academic.total_comprehensive_score else 0.0,
            }

        # 登录信息
        login_info = {
            'username': student.school_id,
            'default_password': '123456',
            'note': '请尽快修改初始密码'
        }

        return {
            'user_info': user_info,
            'academic_info': academic_info,
            'login_info': login_info,
            'registered_at': timezone.now().isoformat()
        }


class BulkUserImportView(APIView):
    """
    批量导入用户接口
    """
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated]

    def check_permissions(self, request):
        """权限验证 - 只有管理员可以导入"""
        super().check_permissions(request)
        if not request.user.is_admin:
            self.permission_denied(
                request,
                message="权限不足，只有管理员可以批量导入用户"
            )

    def post(self, request):
        """
        批量导入用户
        POST /api/admin/users/bulk-import/
        表单数据:
        - file: Excel文件
        - user_type: 0=学生, 1=老师
        """
        try:
            print("=== 批量导入用户请求 ===")
            print(
                f"用户: {request.user.name}, 文件: {request.FILES.get('file').name if request.FILES.get('file') else 'None'}")

            serializer = BulkUserImportSerializer(data=request.data)

            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': '数据验证失败',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            file = serializer.validated_data['file']
            user_type = serializer.validated_data['user_type']
            df = serializer.validated_data['dataframe']

            print(f"开始导入 {len(df)} 个{'学生' if user_type == 0 else '老师'}用户")

            # 执行批量导入
            result = self._bulk_import_users(df, user_type)

            return Response({
                'success': True,
                'message': f'批量导入完成',
                'data': result
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"批量导入异常: {str(e)}")
            import traceback
            print(traceback.format_exc())

            return Response({
                'success': False,
                'message': f'批量导入失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _bulk_import_users(self, df, user_type):
        """执行批量导入"""
        success_count = 0
        error_count = 0
        errors = []
        created_users = []

        with transaction.atomic():
            for index, row in df.iterrows():
                try:
                    row_num = index + 2

                    # 创建用户
                    user_data = {
                        'school_id': str(row['账号']).strip(),
                        'name': str(row['姓名']).strip(),
                        'college': str(row['单位']).strip(),
                        'user_type': user_type,
                        'password': '123456'  # 初始密码
                    }

                    # 学生特定字段
                    if user_type == 0:
                        user_data.update({
                            'major': str(row['专业']).strip(),
                            'grade': '',  # 可以为空
                            'class_name': ''  # 可以为空
                        })

                    # 老师特定字段
                    else:
                        user_data.update({
                            'title': ''  # 职称可以为空
                        })

                    # 创建用户
                    user = User.objects.create_user(**user_data)

                    # 为学生创建学业成绩记录
                    if user_type == 0:
                        self._create_academic_performance(user, row)

                    success_count += 1
                    created_users.append({
                        'school_id': user.school_id,
                        'name': user.name,
                        'college': user.college,
                        'user_type': '学生' if user_type == 0 else '老师'
                    })

                    print(f"✅ 创建用户: {user.school_id} - {user.name}")

                except Exception as e:
                    error_count += 1
                    school_id = str(row['账号']).strip() if '账号' in row else '未知'
                    errors.append(f"第{row_num}行 ({school_id}): {str(e)}")
                    print(f"❌ 创建用户失败 {school_id}: {str(e)}")

        return {
            'total': len(df),
            'success_count': success_count,
            'error_count': error_count,
            'errors': errors,
            'created_users': created_users
        }

    def _create_academic_performance(self, user, row):
        """为学生创建学业成绩记录"""
        try:
            # 处理绩点
            gpa = float(row['绩点']) if not pd.isna(row['绩点']) else 0.0

            # 处理四级分数
            cet4 = int(row['四级分数']) if not pd.isna(row['四级分数']) else -1

            # 处理六级分数
            cet6 = int(row['六级分数']) if not pd.isna(row['六级分数']) else -1

            # 创建学业成绩记录
            AcademicPerformance.objects.create(
                user=user,
                gpa=gpa,
                cet4=cet4,
                cet6=cet6,
                academic_score=0.0,  # 初始值
                academic_expertise_score=0.0,  # 初始值
                comprehensive_performance_score=0.0,  # 初始值
                total_comprehensive_score=0.0  # 初始值
            )

            print(f"✅ 创建学业成绩: {user.school_id} - 绩点: {gpa}")

        except Exception as e:
            print(f"❌ 创建学业成绩失败 {user.school_id}: {str(e)}")
            # 不阻断用户创建流程


class UserContactUpdateView(APIView):
    """
    用户联系方式更新接口
    PUT /api/user/contact/
    """
    permission_classes = [IsAuthenticated]

    def put(self, request):
        try:
            print("=== 用户联系方式更新请求 ===")
            print(f"用户: {request.user.school_id} ({request.user.name})")
            print(f"请求数据: {request.data}")

            # 🎯 检查当前用户的联系信息
            print(f"当前邮箱: {request.user.email}, 当前联系方式: {request.user.contact}")

            serializer = UserContactUpdateSerializer(
                instance=request.user,
                data=request.data,
                partial=False
            )

            if serializer.is_valid():
                print("✅ 数据验证通过")

                try:
                    with transaction.atomic():
                        user = serializer.save()

                        return Response({
                            "success": True,
                            "message": "联系方式更新成功",
                            "data": {
                                "email": user.email,
                                "phone": user.contact,
                                "updated_at": timezone.now().isoformat()
                            }
                        }, status=status.HTTP_200_OK)

                except Exception as e:
                    print(f"❌ 保存失败: {str(e)}")
                    import traceback
                    traceback.print_exc()

                    return Response({
                        "success": False,
                        "message": f"更新失败: {str(e)}",
                        "errors": {"system": "系统错误，请稍后重试"}
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                print(f"❌ 数据验证失败: {serializer.errors}")
                return Response({
                    "success": False,
                    "message": "数据验证失败",
                    "errors": serializer.errors,
                    "debug": {
                        "current_user": {
                            "school_id": request.user.school_id,
                            "email": request.user.email,
                            "contact": request.user.contact
                        },
                        "received_data": request.data
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print(f"❌ 接口异常: {str(e)}")
            import traceback
            traceback.print_exc()

            return Response({
                "success": False,
                "message": f"请求处理失败: {str(e)}",
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChangePasswordView(APIView):
    """
    用户修改密码接口
    PUT /api/user/change-password/
    """
    permission_classes = [IsAuthenticated]

    def put(self, request):
        """
        修改用户密码
        """
        try:
            print("=== 密码修改请求开始 ===")
            print(f"用户: {request.user.school_id}")

            # 验证请求数据
            serializer = ChangePasswordSerializer(data=request.data)

            if not serializer.is_valid():
                print("❌ 数据验证失败:", serializer.errors)
                return Response({
                    "success": False,
                    "message": "数据验证失败",
                    "errors": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            # 提取验证后的数据
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']

            print("✅ 数据验证通过")

            # 验证原密码是否正确
            user = request.user
            if not check_password(old_password, user.password):
                print("❌ 原密码验证失败")
                return Response({
                    "success": False,
                    "message": "原密码不正确",
                    "errors": {
                        'old_password': ['原密码不正确']
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

            print("✅ 原密码验证通过")

            try:
                with transaction.atomic():
                    # 更新密码
                    user.set_password(new_password)
                    user.save()

                    # 更新session认证，避免用户被登出
                    update_session_auth_hash(request, user)

                    print("✅ 密码更新成功")

                    return Response({
                        "success": True,
                        "message": "密码修改成功",
                        "data": None
                    }, status=status.HTTP_200_OK)

            except Exception as save_error:
                print(f"❌ 密码保存失败: {str(save_error)}")
                return Response({
                    "success": False,
                    "message": "密码修改失败，请稍后重试",
                    "errors": {
                        'system': ['系统错误，请稍后重试']
                    }
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            print(f"❌ 密码修改过程异常: {str(e)}")
            import traceback
            print(f"异常堆栈: {traceback.format_exc()}")

            return Response({
                "success": False,
                "message": "修改密码过程中发生错误",
                "errors": {
                    'system': ['系统错误，请稍后重试']
                }
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


import pandas as pd
import io
import re
from datetime import datetime
from decimal import Decimal


class ExcelStudentImporterV2:
    """
    Excel学生导入工具类 V2 - 支持中文列名
    """

    # 🎯 中文列名到系统字段名的映射
    CHINESE_COLUMN_MAPPING = {
        # 必需字段
        '学号': 'school_id',
        '学号/工号': 'school_id',
        'student_id': 'school_id',
        'student id': 'school_id',

        '姓名': 'name',
        '名字': 'name',
        '学生姓名': 'name',
        'name': 'name',

        '单位': 'department',
        '部门': 'department',
        '院系': 'department',
        '学院专业': 'department',
        '所属单位': 'department',

        # 成绩字段
        '绩点': 'academy_score',
        '学分绩点': 'academy_score',
        'gpa': 'academy_score',
        'GPA': 'academy_score',
        '平均绩点': 'academy_score',

        '英语四级成绩': 'cet4',
        '四级成绩': 'cet4',
        'CET4': 'cet4',
        'cet4': 'cet4',
        '英语四级': 'cet4',

        '英语六级成绩': 'cet6',
        '六级成绩': 'cet6',
        'CET6': 'cet6',
        'cet6': 'cet6',
        '英语六级': 'cet6',
    }

    REQUIRED_COLUMNS = ['school_id', 'name', 'department', 'academy_score']
    OPTIONAL_COLUMNS = ['cet4', 'cet6']

    @staticmethod
    def read_and_validate_excel(excel_file):
        """
        读取并验证Excel文件（支持中文列名）
        """
        try:
            print(f"=== 读取Excel文件 ===")
            print(f"文件名: {excel_file.name}")

            # 验证文件格式
            if not (excel_file.name.endswith('.xlsx') or excel_file.name.endswith('.xls')):
                raise ValueError("只支持.xlsx或.xls格式的Excel文件")

            # 🎯 读取Excel，尝试不同的编码
            try:
                df = pd.read_excel(excel_file)
            except Exception as e:
                print(f"第一次读取失败，尝试其他编码: {e}")
                df = pd.read_excel(excel_file, engine='openpyxl')

            print(f"Excel形状: {df.shape} (行×列)")
            print(f"原始列名: {list(df.columns)}")

            # 🎯 标准化列名：去除空格，统一大小写，应用中文映射
            df = ExcelStudentImporterV2.normalize_column_names(df)
            print(f"标准化后列名: {list(df.columns)}")

            # 🎯 验证必需列是否存在
            missing_columns = []
            for required_col in ExcelStudentImporterV2.REQUIRED_COLUMNS:
                if required_col not in df.columns:
                    missing_columns.append(required_col)

            if missing_columns:
                # 尝试提示用户可能的中文列名
                suggested_names = []
                for missing_col in missing_columns:
                    # 反向查找：系统字段名 -> 可能的中文列名
                    possible_names = []
                    for chinese_name, sys_name in ExcelStudentImporterV2.CHINESE_COLUMN_MAPPING.items():
                        if sys_name == missing_col:
                            possible_names.append(chinese_name)
                    if possible_names:
                        suggested_names.append(f"{missing_col}(可能的中文名: {', '.join(possible_names)})")

                error_msg = f"Excel缺少必需列: {missing_columns}"
                if suggested_names:
                    error_msg += f"\n建议使用以下中文列名: {', '.join(suggested_names)}"

                raise ValueError(error_msg)

            # 验证数据行数
            if len(df) == 0:
                raise ValueError("Excel文件为空")

            if len(df) > 1000:
                raise ValueError("单次导入不能超过1000个学生")

            print(f"找到 {len(df)} 个学生记录")

            return df

        except Exception as e:
            print(f"读取Excel失败: {e}")
            raise

    @staticmethod
    def normalize_column_names(df):
        """
        标准化列名：支持中文列名映射
        """
        # 创建副本
        normalized_df = df.copy()

        # 新的列名列表
        new_columns = []

        for col in normalized_df.columns:
            original_col = str(col)
            # 清理列名：去除空格、特殊字符
            cleaned_col = original_col.strip().replace(' ', '').replace('\n', '').replace('\t', '')

            # 🎯 应用映射：先尝试完整匹配，然后尝试包含匹配
            mapped_col = None

            # 1. 完整匹配
            if cleaned_col in ExcelStudentImporterV2.CHINESE_COLUMN_MAPPING:
                mapped_col = ExcelStudentImporterV2.CHINESE_COLUMN_MAPPING[cleaned_col]
                print(f"列名映射: '{original_col}' -> '{mapped_col}' (完整匹配)")

            # 2. 部分匹配（如果完整匹配失败）
            if mapped_col is None:
                for chinese_name, sys_name in ExcelStudentImporterV2.CHINESE_COLUMN_MAPPING.items():
                    if chinese_name in cleaned_col:
                        mapped_col = sys_name
                        print(f"列名映射: '{original_col}' -> '{mapped_col}' (部分匹配: 包含'{chinese_name}')")
                        break

            # 3. 默认使用原始列名（小写）
            if mapped_col is None:
                mapped_col = cleaned_col.lower()
                print(f"列名未映射: '{original_col}' -> '{mapped_col}' (使用小写)")

            new_columns.append(mapped_col)

        normalized_df.columns = new_columns

        # 🎯 检查是否有重复列名
        column_counts = {}
        for col in normalized_df.columns:
            column_counts[col] = column_counts.get(col, 0) + 1

        duplicate_columns = [col for col, count in column_counts.items() if count > 1]
        if duplicate_columns:
            print(f"警告: 发现重复列名: {duplicate_columns}")
            # 处理重复列名：添加后缀
            new_columns = []
            col_count = {}
            for col in normalized_df.columns:
                if col in col_count:
                    col_count[col] += 1
                    new_columns.append(f"{col}_{col_count[col]}")
                else:
                    col_count[col] = 1
                    new_columns.append(col)
            normalized_df.columns = new_columns

        return normalized_df

    @staticmethod
    def parse_student_data(df):
        """
        解析Excel数据为学生列表
        支持中文列名和字段转换
        """
        students_data = []
        errors = []

        print("=== 开始解析学生数据 ===")

        for index, row in df.iterrows():
            try:
                row_num = index + 2  # Excel行号（从2开始）

                print(f"\n--- 解析第{row_num}行 ---")

                # 提取基础数据
                student_data = {
                    'school_id': ExcelStudentImporterV2._extract_value(row, 'school_id', row_num, str),
                    'name': ExcelStudentImporterV2._extract_value(row, 'name', row_num, str),
                    'department': ExcelStudentImporterV2._extract_value(row, 'department', row_num, str, default=''),
                    'academy_score': ExcelStudentImporterV2._extract_value(row, 'academy_score', row_num, float),
                    '_row_num': row_num,
                }

                # 🎯 提取可选字段
                if 'cet4' in df.columns:
                    student_data['cet4'] = ExcelStudentImporterV2._extract_value(row, 'cet4', row_num, float,
                                                                                 default=-1)
                else:
                    student_data['cet4'] = -1

                if 'cet6' in df.columns:
                    student_data['cet6'] = ExcelStudentImporterV2._extract_value(row, 'cet6', row_num, float,
                                                                                 default=-1)
                else:
                    student_data['cet6'] = -1

                print(f"原始数据: {student_data}")

                # 🎯 数据清洗和验证
                student_data = ExcelStudentImporterV2.clean_student_data(student_data)

                # 🎯 解析department为college和major
                college, major = ExcelStudentImporterV2.parse_department(student_data['department'])
                student_data['college'] = college
                student_data['major'] = major

                # 🎯 从学号提取年级
                school_id = student_data['school_id']
                grade = ExcelStudentImporterV2.extract_grade_from_school_id(school_id)
                student_data['grade'] = grade

                # 🎯 字段映射：academy_score -> gpa
                student_data['gpa'] = student_data['academy_score']
                student_data['academic_score'] = 0.0000
                student_data['weighted_score'] = 0.0000
                student_data['password'] = '123456'

                students_data.append(student_data)

                print(f"✅ 行{row_num}: 解析成功 - {student_data['school_id']} {student_data['name']}")
                print(f"   学院: {college}, 专业: {major}, 绩点: {student_data['gpa']}")

            except Exception as e:
                error_msg = f"第{row_num}行数据解析失败: {str(e)}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")
                import traceback
                print(f"错误详情: {traceback.format_exc()}")

        print(f"\n=== 解析完成 ===")
        print(f"成功: {len(students_data)} 条, 失败: {len(errors)} 条")

        return students_data, errors

    @staticmethod
    def _extract_value(row, column_name, row_num, value_type, default=None):
        """
        安全提取单元格值
        """
        if column_name not in row:
            if default is not None:
                return default
            raise ValueError(f"列 '{column_name}' 不存在")

        raw_value = row[column_name]

        # 处理NaN/空值
        if pd.isna(raw_value):
            if default is not None:
                return default
            raise ValueError(f"第{row_num}行列'{column_name}'不能为空")

        try:
            # 转换为字符串清理
            str_value = str(raw_value).strip()

            if value_type == str:
                return str_value
            elif value_type == int:
                # 尝试转换为int，支持浮点数
                try:
                    return int(float(str_value))
                except:
                    return int(str_value)
            elif value_type == float:
                return float(str_value)
            else:
                return value_type(str_value)

        except Exception as e:
            raise ValueError(f"第{row_num}行列'{column_name}'值'{raw_value}'转换失败: {str(e)}")

    @staticmethod
    def clean_student_data(student_data):
        """
        清洗学生数据
        """
        cleaned = student_data.copy()

        # 1. 学号：去除空格
        cleaned['school_id'] = str(cleaned['school_id']).strip()
        if not cleaned['school_id']:
            raise ValueError("学号不能为空")

        # 2. 姓名：去除空格
        cleaned['name'] = str(cleaned['name']).strip()
        if not cleaned['name']:
            raise ValueError("姓名不能为空")

        # 3. department：去除空格
        cleaned['department'] = str(cleaned.get('department', '')).strip()

        # 4. academy_score：验证范围
        academy_score = cleaned['academy_score']
        if isinstance(academy_score, (int, float)):
            if academy_score < 0 or academy_score > 5:
                # 自动修正：如果超出范围，设为0或5
                if academy_score < 0:
                    cleaned['academy_score'] = 0.0
                else:
                    cleaned['academy_score'] = 5.0
                print(f"    警告: 绩点{academy_score}超出范围，修正为{cleaned['academy_score']}")
        else:
            cleaned['academy_score'] = 0.0

        # 5. cet4：验证范围
        cet4 = cleaned['cet4']
        if isinstance(cet4, (int, float)):
            if cet4 < 0 or cet4 > 710:
                # 如果不在有效范围，设为-1（未参加）
                cleaned['cet4'] = -1
                print(f"    警告: CET4成绩{cet4}无效，设为未参加(-1)")
        else:
            cleaned['cet4'] = -1

        # 6. cet6：验证范围
        cet6 = cleaned['cet6']
        if isinstance(cet6, (int, float)):
            if cet6 < 0 or cet6 > 710:
                cleaned['cet6'] = -1
                print(f"    警告: CET6成绩{cet6}无效，设为未参加(-1)")
        else:
            cleaned['cet6'] = -1

        return cleaned

    @staticmethod
    def parse_department(department_str):
        """
        智能解析department字段为college和major
        支持多种格式：
        1. "计算机学院" -> college="计算机学院", major="计算机学院"
        2. "计算机学院-软件工程" -> college="计算机学院", major="软件工程"
        3. "计算机学院/软件工程" -> college="计算机学院", major="软件工程"
        4. "计算机学院软件工程系" -> college="计算机学院", major="软件工程系"
        """
        if not department_str:
            return "未知学院", "未知专业"

        print(f"    解析单位字段: '{department_str}'")

        # 尝试多种分隔符
        separators = ['-', '/', '\\', '、', '，', ',', ' ', '|']

        for sep in separators:
            if sep in department_str:
                parts = [p.strip() for p in department_str.split(sep) if p.strip()]
                if len(parts) >= 2:
                    # 取第一个作为学院，最后一个作为专业
                    college = parts[0]
                    major = parts[-1]
                    print(f"    使用分隔符'{sep}': college={college}, major={major}")
                    return college, major

        # 如果没有分隔符，尝试智能分割
        # 常见学院关键词
        college_keywords = ['学院', '大学', '学校', '系', '学部', '中心']
        major_keywords = ['专业', '方向', '班', '类', '系']

        # 查找学院关键词位置
        college_end = -1
        for keyword in college_keywords:
            if keyword in department_str:
                idx = department_str.find(keyword)
                if idx != -1:
                    college_end = idx + len(keyword)
                    break

        if college_end != -1 and college_end < len(department_str):
            # 找到学院关键词，分割
            college = department_str[:college_end]
            major = department_str[college_end:].strip()
            if not major:
                major = college
            print(f"    智能分割: college={college}, major={major}")
            return college, major
        else:
            # 无法分割，整个作为学院和专业
            print(f"    无法分割，整体使用: college={department_str}, major={department_str}")
            return department_str, department_str

    @staticmethod
    def extract_grade_from_school_id(school_id):
        """
        从学号提取年级
        支持多种学号格式
        """
        school_id_str = str(school_id).strip()

        # 常见学号模式
        patterns = [
            r'^(\d{4})',  # 前4位是年级，如2024001001
            r'^(\d{2})',  # 前2位是年级（简写），如241001
            r'[A-Za-z]*(\d{4})',  # 包含字母和4位数字
        ]

        for pattern in patterns:
            match = re.search(pattern, school_id_str)
            if match:
                grade_part = match.group(1)
                if len(grade_part) == 4 and grade_part.isdigit():
                    grade_num = int(grade_part)
                    if 2000 <= grade_num <= 2030:
                        return grade_part
                elif len(grade_part) == 2 and grade_part.isdigit():
                    # 2位年份，补全为4位
                    year_num = int(grade_part)
                    if 0 <= year_num <= 99:
                        full_year = 2000 + year_num if year_num < 30 else 1900 + year_num
                        if 2000 <= full_year <= 2030:
                            return str(full_year)

        # 无法提取，使用当前年份或默认
        current_year = datetime.now().year
        return str(current_year)


@method_decorator(csrf_exempt, name='dispatch')
class BulkStudentRegistrationViewV2(APIView):
    """
    批量注册学生用户接口 V2 - 完整版本
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            print("=== 批量学生注册请求开始 ===")
            print(f"操作者: {request.user.school_id} (类型: {request.user.user_type})")
            print(f"请求方法: {request.method}")
            print(f"请求内容类型: {request.content_type}")
            print(f"请求FILES keys: {list(request.FILES.keys())}")

            # 🎯 权限验证
            if request.user.user_type != 2:
                print(f"❌ 权限拒绝: 用户 {request.user.school_id} 不是超级管理员")
                return Response({
                    'success': False,
                    'message': '只有超级管理员可以批量注册学生',
                    'data': None
                }, status=status.HTTP_403_FORBIDDEN)

            print("✅ 权限验证通过")

            # 🎯 获取Excel文件
            excel_file = None
            for field_name, file_obj in request.FILES.items():
                print(f"检查字段: '{field_name}' -> '{file_obj.name}'")
                if file_obj.name.lower().endswith(('.xlsx', '.xls')):
                    excel_file = file_obj
                    print(f"✅ 找到Excel文件")
                    break

            if not excel_file:
                print("❌ 没有找到Excel文件")
                return Response({
                    'success': False,
                    'message': '请上传Excel文件（.xlsx或.xls格式）',
                    'data': {
                        'available_files': [
                            {'field': k, 'name': v.name, 'size': v.size}
                            for k, v in request.FILES.items()
                        ]
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

            print(f"✅ 找到Excel文件: {excel_file.name} ({excel_file.size} bytes)")

            # 🎯 读取和解析Excel
            try:
                print("开始解析Excel文件...")
                df = ExcelStudentImporterV2.read_and_validate_excel(excel_file)
                students_data, parse_errors = ExcelStudentImporterV2.parse_student_data(df)
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Excel解析失败: {error_msg}")
                import traceback
                traceback.print_exc()
                return Response({
                    'success': False,
                    'message': f'Excel文件解析失败: {error_msg}',
                    'data': {
                        'error': error_msg,
                        'file_name': excel_file.name
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

            if not students_data:
                print("❌ Excel文件中没有有效的学生数据")
                return Response({
                    'success': False,
                    'message': 'Excel文件中没有有效的学生数据',
                    'data': {
                        'parse_errors': parse_errors[:5] if parse_errors else [],
                        'total_rows': len(df) if 'df' in locals() else 0
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

            print(f"✅ 解析成功，准备注册 {len(students_data)} 个学生")

            # 🎯 批量注册学生
            results = self.bulk_create_students(students_data)

            # 🎯 生成导入报告
            report = self.generate_import_report(results, parse_errors, len(students_data))

            print(f"✅ 批量注册完成: 成功 {results['success_count']} 个，失败 {results['failed_count']} 个")

            return Response({
                'success': True,
                'message': f'批量注册完成，成功 {results["success_count"]} 个，失败 {results["failed_count"]} 个',
                'data': report
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"❌ 批量注册异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'success': False,
                'message': f'批量注册失败: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def bulk_create_students(self, students_data):
        """
        批量创建学生 - 核心方法
        """
        results = {
            'success_count': 0,
            'failed_count': 0,
            'success_students': [],
            'failed_students': []
        }

        print(f"=== 开始批量创建 {len(students_data)} 个学生 ===")

        # 按学号分组，处理重复
        school_id_map = {}
        duplicate_school_ids = []

        for student_data in students_data:
            school_id = student_data['school_id']
            if school_id in school_id_map:
                duplicate_school_ids.append(school_id)
            else:
                school_id_map[school_id] = student_data

        if duplicate_school_ids:
            print(f"警告: 发现重复学号: {set(duplicate_school_ids)}")

        # 处理每个唯一学号
        for school_id, student_data in school_id_map.items():
            row_num = student_data.get('_row_num', '未知')

            try:
                with transaction.atomic():
                    # 检查学号是否已存在
                    if User.objects.filter(school_id=school_id).exists():
                        raise ValueError(f"学号 {school_id} 在系统中已存在")

                    # 准备User数据
                    user_data = {
                        'school_id': student_data['school_id'],
                        'name': student_data['name'],
                        'college': student_data['college'],
                        'major': student_data['major'],
                        'grade': student_data['grade'],
                        'user_type': 0,  # 学生
                        'password': '123456',
                    }

                    print(f"创建用户: {user_data['school_id']} - {user_data['name']}")

                    # 创建User
                    student = User.objects.create_user(**user_data)

                    # 创建AcademicPerformance
                    AcademicPerformance.objects.create(
                        user=student,
                        gpa=Decimal(str(student_data.get('gpa', 0.0000))),
                        cet4=int(student_data.get('cet4', -1)),
                        cet6=int(student_data.get('cet6', -1)),
                        academic_score=Decimal('0.0000'),
                        weighted_score=Decimal('0.0000'),
                        academic_expertise_score=Decimal('0.0000'),
                        comprehensive_performance_score=Decimal('0.0000'),
                        total_comprehensive_score=Decimal('0.0000'),
                        applications_score=[],
                        total_courses=0,
                        total_credits=Decimal('0.0000'),
                        gpa_ranking=0,
                        ranking_dimension='专业内排名',
                        failed_courses=0,
                    )

                    results['success_count'] += 1
                    results['success_students'].append({
                        'row_num': row_num,
                        'school_id': student.school_id,
                        'name': student.name,
                        'college': student.college,
                        'major': student.major,
                        'grade': student.grade,
                        'gpa': float(student_data.get('gpa', 0.0000)),
                        'cet4': student_data.get('cet4', -1),
                        'cet6': student_data.get('cet6', -1),
                    })

                    print(f"✅ 行{row_num}: 创建成功 - {student.school_id} {student.name}")

            except Exception as e:
                error_msg = str(e)
                results['failed_count'] += 1
                results['failed_students'].append({
                    'row_num': row_num,
                    'school_id': school_id,
                    'name': student_data.get('name', '未知'),
                    'error': error_msg
                })
                print(f"❌ 行{row_num}: 创建失败 - {error_msg}")

        print(f"批量创建完成: 成功 {results['success_count']} 个, 失败 {results['failed_count']} 个")
        return results

    def generate_import_report(self, results, parse_errors, total_records):
        """
        生成详细的导入报告
        """
        from django.utils import timezone

        report = {
            'summary': {
                'excel_total_records': total_records,
                'processed_records': results['success_count'] + results['failed_count'],
                'success_count': results['success_count'],
                'failed_count': results['failed_count'],
                'parse_errors_count': len(parse_errors),
                'success_rate': f"{(results['success_count'] / total_records * 100):.1f}%" if total_records > 0 else "0%",
                'import_time': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                'operator': self.request.user.school_id,
            },
            'field_mapping_info': {
                'supported_chinese_columns': [
                    '学号', '姓名', '单位', '绩点', '英语四级成绩', '英语六级成绩'
                ],
                'mapped_to': [
                    'school_id', 'name', 'department', 'academy_score', 'cet4', 'cet6'
                ],
                'note': '系统会自动识别多种中文列名变体'
            },
            'success_students_sample': results['success_students'][:20],  # 只返回前20条
            'failed_students': results['failed_students'][:50],
            'parse_errors': parse_errors[:20],
            'statistics': {
                'by_college': self._group_by_college(results['success_students']),
                'by_grade': self._group_by_grade(results['success_students']),
            },
            'notes': [
                '所有学生的初始密码均为: 123456',
                '请提醒学生首次登录后修改密码',
                '重复的学号会自动去重，只导入第一次出现的记录',
                'CET4/CET6成绩为-1表示未参加考试',
                '单位字段会自动解析为学院和专业'
            ]
        }

        return report

    def _group_by_college(self, students):
        """按学院分组统计"""
        groups = {}
        for student in students:
            college = student.get('college', '未知学院')
            groups[college] = groups.get(college, 0) + 1
        return groups

    def _group_by_grade(self, students):
        """按年级分组统计"""
        groups = {}
        for student in students:
            grade = student.get('grade', '未知年级')
            groups[grade] = groups.get(grade, 0) + 1
        return groups


class DownloadStudentTemplateView(APIView):
    """
    下载学生导入Excel模板
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        下载Excel模板
        GET /api/superadmin/students/template/
        """
        try:
            # 权限验证
            if request.user.user_type != 2:
                return Response({
                    'success': False,
                    'message': '只有超级管理员可以下载模板'
                }, status=status.HTTP_403_FORBIDDEN)

            # 创建示例数据
            sample_data = [
                {
                    '学号': '2024001001',
                    '姓名': '张三',
                    '单位': '信息学院-软件工程',
                    '绩点': 3.8,
                    '英语四级成绩': 550,
                    '英语六级成绩': 520
                },
                {
                    '学号': '2024001002',
                    '姓名': '李四',
                    '单位': '信息学院-计算机科学与技术',
                    '绩点': 3.9,
                    '英语四级成绩': 580,
                    '英语六级成绩': 540
                },
                {
                    '学号': '2024001003',
                    '姓名': '王五',
                    '单位': '信息学院',
                    '绩点': 3.5,
                    '英语四级成绩': 500,
                    '英语六级成绩': 480
                }
            ]

            # 创建DataFrame
            df = pd.DataFrame(sample_data)

            # 创建Excel文件
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='学生数据', index=False)

                # 获取worksheet进行格式设置
                worksheet = writer.sheets['学生数据']

                # 设置列宽
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 30)
                    worksheet.column_dimensions[column_letter].width = adjusted_width

            excel_buffer.seek(0)

            # 🎯 方法1：直接设置文件名（推荐）
            filename = "学生批量导入模板.xlsx"

            # 创建响应
            response = HttpResponse(
                excel_buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

            # 🎯 关键：设置Content-Disposition头部
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Cache-Control'] = 'no-cache'

            print(f"✅ 模板下载成功: {filename}")
            return response

        except Exception as e:
            print(f"❌ 下载模板失败: {e}")
            return Response({
                'success': False,
                'message': f'下载模板失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExcelTeacherImporter:
    """
    Excel教师导入工具类
    """

    # 中文列名到系统字段名的映射
    CHINESE_COLUMN_MAPPING = {
        # 必需字段
        '职工号': 'school_id',
        '工号': 'school_id',
        '教职工号': 'school_id',
        '教师工号': 'school_id',
        'teacher_id': 'school_id',

        '姓名': 'name',
        '教师姓名': 'name',
        '老师姓名': 'name',
        'teacher_name': 'name',

        '单位': 'department',
        '部门': 'department',
        '院系': 'department',
        '所属单位': 'department',
        '所在学院': 'department',
        'college': 'department',
    }

    REQUIRED_COLUMNS = ['school_id', 'name', 'department']

    @staticmethod
    def read_and_validate_excel(excel_file):
        """
        读取并验证教师Excel文件
        """
        try:
            print(f"=== 读取教师Excel文件 ===")
            print(f"文件名: {excel_file.name}")

            # 验证文件格式
            if not (excel_file.name.endswith('.xlsx') or excel_file.name.endswith('.xls')):
                raise ValueError("只支持.xlsx或.xls格式的Excel文件")

            # 读取Excel
            try:
                df = pd.read_excel(excel_file)
            except Exception as e:
                print(f"第一次读取失败，尝试其他编码: {e}")
                df = pd.read_excel(excel_file, engine='openpyxl')

            print(f"Excel形状: {df.shape} (行×列)")
            print(f"原始列名: {list(df.columns)}")

            # 标准化列名
            df = ExcelTeacherImporter.normalize_column_names(df)
            print(f"标准化后列名: {list(df.columns)}")

            # 验证必需列是否存在
            missing_columns = []
            for required_col in ExcelTeacherImporter.REQUIRED_COLUMNS:
                if required_col not in df.columns:
                    missing_columns.append(required_col)

            if missing_columns:
                # 提示可能的中文列名
                suggested_names = []
                for missing_col in missing_columns:
                    possible_names = []
                    for chinese_name, sys_name in ExcelTeacherImporter.CHINESE_COLUMN_MAPPING.items():
                        if sys_name == missing_col:
                            possible_names.append(chinese_name)
                    if possible_names:
                        suggested_names.append(f"{missing_col}(可能的中文名: {', '.join(possible_names)})")

                error_msg = f"Excel缺少必需列: {missing_columns}"
                if suggested_names:
                    error_msg += f"\n建议使用以下中文列名: {', '.join(suggested_names)}"

                raise ValueError(error_msg)

            # 验证数据行数
            if len(df) == 0:
                raise ValueError("Excel文件为空")

            if len(df) > 1000:
                raise ValueError("单次导入不能超过1000个教师")

            print(f"找到 {len(df)} 个教师记录")

            return df

        except Exception as e:
            print(f"读取Excel失败: {e}")
            raise

    @staticmethod
    def normalize_column_names(df):
        """
        标准化列名：支持中文列名映射
        """
        normalized_df = df.copy()
        new_columns = []

        for col in normalized_df.columns:
            original_col = str(col)
            cleaned_col = original_col.strip().replace(' ', '').replace('\n', '').replace('\t', '')

            mapped_col = None

            # 1. 完整匹配
            if cleaned_col in ExcelTeacherImporter.CHINESE_COLUMN_MAPPING:
                mapped_col = ExcelTeacherImporter.CHINESE_COLUMN_MAPPING[cleaned_col]
                print(f"列名映射: '{original_col}' -> '{mapped_col}' (完整匹配)")

            # 2. 部分匹配
            if mapped_col is None:
                for chinese_name, sys_name in ExcelTeacherImporter.CHINESE_COLUMN_MAPPING.items():
                    if chinese_name in cleaned_col:
                        mapped_col = sys_name
                        print(f"列名映射: '{original_col}' -> '{mapped_col}' (部分匹配: 包含'{chinese_name}')")
                        break

            # 3. 默认使用原始列名（小写）
            if mapped_col is None:
                mapped_col = cleaned_col.lower()
                print(f"列名未映射: '{original_col}' -> '{mapped_col}' (使用小写)")

            new_columns.append(mapped_col)

        normalized_df.columns = new_columns

        # 检查重复列名
        column_counts = {}
        for col in normalized_df.columns:
            column_counts[col] = column_counts.get(col, 0) + 1

        duplicate_columns = [col for col, count in column_counts.items() if count > 1]
        if duplicate_columns:
            print(f"警告: 发现重复列名: {duplicate_columns}")
            new_columns = []
            col_count = {}
            for col in normalized_df.columns:
                if col in col_count:
                    col_count[col] += 1
                    new_columns.append(f"{col}_{col_count[col]}")
                else:
                    col_count[col] = 1
                    new_columns.append(col)
            normalized_df.columns = new_columns

        return normalized_df

    @staticmethod
    def parse_teacher_data(df):
        """
        解析Excel数据为教师列表
        """
        teachers_data = []
        errors = []

        print("=== 开始解析教师数据 ===")

        for index, row in df.iterrows():
            try:
                row_num = index + 2  # Excel行号（从2开始）

                print(f"\n--- 解析第{row_num}行 ---")

                # 提取基础数据
                teacher_data = {
                    'school_id': ExcelTeacherImporter._extract_value(row, 'school_id', row_num, str),
                    'name': ExcelTeacherImporter._extract_value(row, 'name', row_num, str),
                    'department': ExcelTeacherImporter._extract_value(row, 'department', row_num, str, default=''),
                    '_row_num': row_num,
                    'password': '123456',
                    'user_type': 1,  # 教师类型
                }

                print(f"原始数据: {teacher_data}")

                # 数据清洗和验证
                teacher_data = ExcelTeacherImporter.clean_teacher_data(teacher_data)

                # 解析department为college
                college = ExcelTeacherImporter.parse_department(teacher_data['department'])
                teacher_data['college'] = college

                teachers_data.append(teacher_data)

                print(f"✅ 行{row_num}: 解析成功 - {teacher_data['school_id']} {teacher_data['name']}")
                print(f"   学院: {college}")

            except Exception as e:
                error_msg = f"第{row_num}行数据解析失败: {str(e)}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")
                import traceback
                print(f"错误详情: {traceback.format_exc()}")

        print(f"\n=== 解析完成 ===")
        print(f"成功: {len(teachers_data)} 条, 失败: {len(errors)} 条")

        return teachers_data, errors

    @staticmethod
    def _extract_value(row, column_name, row_num, value_type, default=None):
        """
        安全提取单元格值
        """
        if column_name not in row:
            if default is not None:
                return default
            raise ValueError(f"列 '{column_name}' 不存在")

        raw_value = row[column_name]

        # 处理NaN/空值
        if pd.isna(raw_value):
            if default is not None:
                return default
            raise ValueError(f"第{row_num}行列'{column_name}'不能为空")

        try:
            str_value = str(raw_value).strip()

            if value_type == str:
                return str_value
            elif value_type == int:
                try:
                    return int(float(str_value))
                except:
                    return int(str_value)
            elif value_type == float:
                return float(str_value)
            else:
                return value_type(str_value)

        except Exception as e:
            raise ValueError(f"第{row_num}行列'{column_name}'值'{raw_value}'转换失败: {str(e)}")

    @staticmethod
    def clean_teacher_data(teacher_data):
        """
        清洗教师数据
        """
        cleaned = teacher_data.copy()

        # 1. 职工号：去除空格
        cleaned['school_id'] = str(cleaned['school_id']).strip()
        if not cleaned['school_id']:
            raise ValueError("职工号不能为空")

        # 2. 姓名：去除空格
        cleaned['name'] = str(cleaned['name']).strip()
        if not cleaned['name']:
            raise ValueError("姓名不能为空")

        # 3. department：去除空格
        cleaned['department'] = str(cleaned.get('department', '')).strip()

        return cleaned

    @staticmethod
    def parse_department(department_str):
        """
        解析department字段为学院
        教师通常只有学院信息，没有专业
        """
        if not department_str:
            return "未知学院"

        print(f"    解析单位字段: '{department_str}'")

        # 尝试多种分隔符
        separators = ['-', '/', '\\', '、', '，', ',', ' ', '|']

        for sep in separators:
            if sep in department_str:
                parts = [p.strip() for p in department_str.split(sep) if p.strip()]
                if parts:
                    # 取第一个作为学院
                    college = parts[0]
                    print(f"    使用分隔符'{sep}': college={college}")
                    return college

        # 如果没有分隔符，直接使用整个字符串
        print(f"    无分隔符，整体作为学院: college={department_str}")
        return department_str


@method_decorator(csrf_exempt, name='dispatch')
class BulkTeacherRegistrationView(APIView):
    """
    批量导入教师用户接口
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        """
        批量导入教师
        POST /api/superadmin/teachers/bulk-import/
        参数: excel_file (Excel文件)
        """
        try:
            print("=== 批量教师导入请求开始 ===")
            print(f"操作者: {request.user.school_id} (类型: {request.user.user_type})")
            print(f"请求方法: {request.method}")
            print(f"请求内容类型: {request.content_type}")
            print(f"请求FILES keys: {list(request.FILES.keys())}")

            # 🎯 权限验证（只允许超级管理员）
            if request.user.user_type != 2:
                print(f"❌ 权限拒绝: 用户 {request.user.school_id} 不是超级管理员")
                return Response({
                    'success': False,
                    'message': '只有超级管理员可以批量导入教师',
                    'data': None
                }, status=status.HTTP_403_FORBIDDEN)

            print("✅ 权限验证通过")

            # 🎯 获取Excel文件
            excel_file = None
            for field_name, file_obj in request.FILES.items():
                print(f"检查字段: '{field_name}' -> '{file_obj.name}'")
                if file_obj.name.lower().endswith(('.xlsx', '.xls')):
                    excel_file = file_obj
                    print(f"✅ 找到Excel文件")
                    break

            if not excel_file:
                print("❌ 没有找到Excel文件")
                return Response({
                    'success': False,
                    'message': '请上传Excel文件（.xlsx或.xls格式）',
                    'data': {
                        'available_files': [
                            {'field': k, 'name': v.name, 'size': v.size}
                            for k, v in request.FILES.items()
                        ],
                        'expected_format': '职工号, 姓名, 单位'
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

            print(f"✅ 找到Excel文件: {excel_file.name} ({excel_file.size} bytes)")

            # 🎯 读取和解析Excel
            try:
                print("开始解析教师Excel文件...")
                df = ExcelTeacherImporter.read_and_validate_excel(excel_file)
                teachers_data, parse_errors = ExcelTeacherImporter.parse_teacher_data(df)
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Excel解析失败: {error_msg}")
                import traceback
                traceback.print_exc()
                return Response({
                    'success': False,
                    'message': f'Excel文件解析失败: {error_msg}',
                    'data': {
                        'error': error_msg,
                        'file_name': excel_file.name,
                        'supported_columns': list(ExcelTeacherImporter.CHINESE_COLUMN_MAPPING.keys())
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

            if not teachers_data:
                print("❌ Excel文件中没有有效的教师数据")
                return Response({
                    'success': False,
                    'message': 'Excel文件中没有有效的教师数据',
                    'data': {
                        'parse_errors': parse_errors[:5] if parse_errors else [],
                        'total_rows': len(df) if 'df' in locals() else 0
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

            print(f"✅ 解析成功，准备导入 {len(teachers_data)} 个教师")

            # 🎯 批量创建教师
            results = self.bulk_create_teachers(teachers_data)

            # 🎯 生成导入报告
            report = self.generate_import_report(results, parse_errors, len(teachers_data))

            print(f"✅ 批量导入完成: 成功 {results['success_count']} 个，失败 {results['failed_count']} 个")

            return Response({
                'success': True,
                'message': f'教师批量导入完成，成功 {results["success_count"]} 个，失败 {results["failed_count"]} 个',
                'data': report
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"❌ 批量导入异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'success': False,
                'message': f'批量导入失败: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def bulk_create_teachers(self, teachers_data):
        """
        批量创建教师用户
        """
        results = {
            'success_count': 0,
            'failed_count': 0,
            'success_teachers': [],
            'failed_teachers': []
        }

        print(f"=== 开始批量创建 {len(teachers_data)} 个教师 ===")

        # 按职工号分组，处理重复
        school_id_map = {}
        duplicate_school_ids = []

        for teacher_data in teachers_data:
            school_id = teacher_data['school_id']
            if school_id in school_id_map:
                duplicate_school_ids.append(school_id)
            else:
                school_id_map[school_id] = teacher_data

        if duplicate_school_ids:
            print(f"警告: 发现重复职工号: {set(duplicate_school_ids)}")

        # 处理每个唯一职工号
        for school_id, teacher_data in school_id_map.items():
            row_num = teacher_data.get('_row_num', '未知')

            try:
                with transaction.atomic():
                    # 检查职工号是否已存在
                    if User.objects.filter(school_id=school_id).exists():
                        raise ValueError(f"职工号 {school_id} 在系统中已存在")

                    # 准备User数据
                    user_data = {
                        'school_id': teacher_data['school_id'],
                        'name': teacher_data['name'],
                        'college': teacher_data['college'],
                        'user_type': 1,  # 教师类型
                        'password': '123456',
                        # 教师不需要专业和年级字段
                        'major': '',
                        'grade': '',
                    }

                    print(f"创建教师: {user_data['school_id']} - {user_data['name']}")

                    # 创建User（教师）
                    teacher = User.objects.create_user(**user_data)

                    results['success_count'] += 1
                    results['success_teachers'].append({
                        'row_num': row_num,
                        'school_id': teacher.school_id,
                        'name': teacher.name,
                        'college': teacher.college,
                        'user_type': '教师',
                    })

                    print(f"✅ 行{row_num}: 创建成功 - {teacher.school_id} {teacher.name}")

            except Exception as e:
                error_msg = str(e)
                results['failed_count'] += 1
                results['failed_teachers'].append({
                    'row_num': row_num,
                    'school_id': school_id,
                    'name': teacher_data.get('name', '未知'),
                    'error': error_msg
                })
                print(f"❌ 行{row_num}: 创建失败 - {error_msg}")

        print(f"批量创建完成: 成功 {results['success_count']} 个, 失败 {results['failed_count']} 个")
        return results

    def generate_import_report(self, results, parse_errors, total_records):
        """
        生成教师导入报告
        """
        from django.utils import timezone

        report = {
            'summary': {
                'excel_total_records': total_records,
                'processed_records': results['success_count'] + results['failed_count'],
                'success_count': results['success_count'],
                'failed_count': results['failed_count'],
                'parse_errors_count': len(parse_errors),
                'success_rate': f"{(results['success_count'] / total_records * 100):.1f}%" if total_records > 0 else "0%",
                'import_time': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                'operator': self.request.user.school_id,
            },
            'field_mapping_info': {
                'supported_chinese_columns': [
                    '职工号', '姓名', '单位'
                ],
                'mapped_to': [
                    'school_id', 'name', 'department'
                ],
                'note': '系统会自动识别多种中文列名变体'
            },
            'success_teachers_sample': results['success_teachers'][:20],
            'failed_teachers': results['failed_teachers'][:50],
            'parse_errors': parse_errors[:20],
            'statistics': {
                'by_college': self._group_by_college(results['success_teachers']),
            },
            'notes': [
                '所有教师的初始密码均为: 123456',
                '请提醒教师首次登录后修改密码',
                '重复的职工号会自动去重，只导入第一次出现的记录',
                '教师默认拥有审核学生申请的权限',
                '如需赋予管理员权限，请在系统中单独设置'
            ]
        }

        return report

    def _group_by_college(self, teachers):
        """按学院分组统计"""
        groups = {}
        for teacher in teachers:
            college = teacher.get('college', '未知学院')
            groups[college] = groups.get(college, 0) + 1
        return groups


class DownloadTeacherTemplateView(APIView):
    """
    下载学生导入Excel模板
    """
    permission_classes = []

    def get(self, request):
        """
        下载Excel模板
        GET /api/superadmin/students/template/
        """
        try:
            # 权限验证
            # if request.user.user_type != 2:
            #     return Response({
            #         'success': False,
            #         'message': '只有超级管理员可以下载模板'
            #     }, status=status.HTTP_403_FORBIDDEN)

            # 创建示例数据
            sample_data = [
                {
                    '职工号': 'T001',
                    '姓名': '张老师',
                    '单位': '信息学院',
                },
                {
                    '职工号': 'T002',
                    '姓名': '李老师',
                    '单位': '信息学院',
                },
                {
                    '职工号': 'T003',
                    '姓名': '王老师',
                    '单位': '信息学院',
                }
            ]

            # 创建DataFrame
            df = pd.DataFrame(sample_data)

            # 创建Excel文件
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='老师数据', index=False)

                # 获取worksheet进行格式设置
                worksheet = writer.sheets['老师数据']

                # 设置列宽
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 30)
                    worksheet.column_dimensions[column_letter].width = adjusted_width

            excel_buffer.seek(0)

            # 🎯 方法1：直接设置文件名（推荐）
            filename = "老师批量导入模板.xlsx"

            # 创建响应
            response = HttpResponse(
                excel_buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

            # 🎯 关键：设置Content-Disposition头部
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Cache-Control'] = 'no-cache'

            print(f"✅ 模板下载成功: {filename}")
            return response

        except Exception as e:
            print(f"❌ 下载模板失败: {e}")
            return Response({
                'success': False,
                'message': f'下载模板失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from django.db import transaction


class DeleteUserView(APIView):
    """
    删除用户接口
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, school_id=None):
        """
        删除用户
        DELETE /api/superadmin/users/delete/<user_id>/
        或
        DELETE /api/superadmin/users/delete/
        参数: user_id (可选，URL参数或请求体)
        """
        try:
            print("=== 删除用户请求开始 ===")
            print(f"操作者: {request.user.school_id} (类型: {request.user.user_type})")

            # 🎯 权限验证（仅超级管理员）
            if request.user.user_type != 2:
                print(f"❌ 权限拒绝: 用户 {request.user.school_id} 不是超级管理员")
                return Response({
                    'success': False,
                    'message': '只有超级管理员可以删除用户',
                    'data': None
                }, status=status.HTTP_403_FORBIDDEN)

            # 🎯 获取要删除的用户ID
            target_user_id = school_id or request.data.get('school_id') or request.query_params.get('school_id')

            if not target_user_id:
                print("❌ 未指定要删除的用户ID")
                return Response({
                    'success': False,
                    'message': '请提供要删除的用户ID',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)

            print(f"目标用户ID: {target_user_id}")

            # 🎯 查找目标用户
            try:
                target_user = User.objects.get(id=target_user_id)
                print(f"找到目标用户: {target_user.school_id} ({target_user.name})")
            except User.DoesNotExist:
                print(f"❌ 用户不存在: {target_user_id}")
                return Response({
                    'success': False,
                    'message': '用户不存在',
                    'data': None
                }, status=status.HTTP_404_NOT_FOUND)

            # 🎯 安全检查：不能删除自己
            if target_user.id == request.user.id:
                print("❌ 不能删除自己")
                return Response({
                    'success': False,
                    'message': '不能删除自己的账号',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)

            # 🎯 安全检查：不能删除其他管理员
            if target_user.user_type == 2 and target_user.id != request.user.id:
                print("❌ 不能删除其他超级管理员")
                return Response({
                    'success': False,
                    'message': '不能删除其他超级管理员的账号',
                    'data': None
                }, status=status.HTTP_403_FORBIDDEN)

            # 🎯 记录用户信息（用于响应和日志）
            user_info = {
                'id': str(target_user.id),
                'school_id': target_user.school_id,
                'name': target_user.name,
                'user_type': target_user.user_type,
                'user_type_display': target_user.get_user_type_display(),
                'college': target_user.college or '',
                'major': target_user.major or '',
                'grade': target_user.grade or '',
                'created_at': target_user.date_joined.isoformat() if target_user.date_joined else None,
                'last_login': target_user.last_login.isoformat() if target_user.last_login else None,
            }

            print(f"用户信息: {user_info}")

            # 🎯 检查用户相关数据
            related_data = self.check_user_related_data(target_user)
            print(f"相关数据统计: {related_data}")

            # 🎯 确认删除（如果需要二次确认）
            confirm = request.data.get('confirm', False)
            if not confirm and related_data['total_count'] > 0:
                # 如果用户有相关数据，需要二次确认
                print("⚠️ 用户有相关数据，需要二次确认")
                return Response({
                    'success': False,
                    'message': '用户有相关数据，请确认删除',
                    'data': {
                        'user_info': user_info,
                        'related_data': related_data,
                        'requires_confirmation': True,
                        'warning': f"该用户有 {related_data['total_count']} 条相关数据，删除后将无法恢复"
                    }
                }, status=status.HTTP_200_OK)  # 返回200，让前端处理确认

            # 🎯 执行删除操作（使用事务）
            try:
                with transaction.atomic():
                    # 记录操作日志
                    self.log_deletion_operation(request.user, target_user, related_data)

                    # 执行删除
                    deleted_info = self.delete_user_with_related_data(target_user)

                    print(f"✅ 用户删除成功: {target_user.school_id}")

                    return Response({
                        'success': True,
                        'message': f'用户 {target_user.name}({target_user.school_id}) 删除成功',
                        'data': {
                            'deleted_user': user_info,
                            'related_data_deleted': deleted_info,
                            'deleted_at': timezone.now().isoformat(),
                            'operator': request.user.school_id
                        }
                    }, status=status.HTTP_200_OK)

            except Exception as e:
                print(f"❌ 删除操作失败: {e}")
                return Response({
                    'success': False,
                    'message': f'删除失败: {str(e)}',
                    'data': None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            print(f"❌ 删除用户异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'success': False,
                'message': f'删除过程中发生错误: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def check_user_related_data(self, user):
        """
        检查用户相关数据
        """
        related_data = {
            'applications_count': 0,
            'attachments_count': 0,
            'academic_performance': False,
            'total_count': 0
        }

        try:
            # 1. 检查申请记录
            if hasattr(user, 'application_set'):
                applications = user.application_set.all()
                related_data['applications_count'] = applications.count()

            # 2. 检查附件（通过申请间接关联）
            # 注意：附件可能被多个申请共享，需要特别处理

            # 3. 检查学业成绩
            if hasattr(user, 'academic_performance'):
                related_data['academic_performance'] = True

            # 4. 检查其他可能的关系
            # 可以根据实际模型添加

            # 计算总数
            total = related_data['applications_count']
            if related_data['academic_performance']:
                total += 1
            related_data['total_count'] = total

        except Exception as e:
            print(f"检查相关数据异常: {e}")

        return related_data

    def delete_user_with_related_data(self, user):
        """
        删除用户及其相关数据
        """
        deleted_info = {
            'user_deleted': True,
            'applications_deleted': 0,
            'academic_performance_deleted': False,
            'attachments_handled': 0
        }

        user_school_id = user.school_id

        try:
            # 1. 先处理申请记录
            if hasattr(user, 'application_set'):
                applications = user.application_set.all()
                application_ids = list(applications.values_list('id', flat=True))

                # 处理申请相关的附件
                attachments_handled = self.handle_application_attachments(applications)
                deleted_info['attachments_handled'] = attachments_handled

                # 删除申请记录
                applications.delete()
                deleted_info['applications_deleted'] = len(application_ids)
                print(f"删除 {len(application_ids)} 条申请记录")

            # 2. 删除学业成绩
            if hasattr(user, 'academic_performance'):
                user.academic_performance.delete()
                deleted_info['academic_performance_deleted'] = True
                print("删除学业成绩记录")

            # 3. 删除用户Token（如果使用DRF Token）
            try:
                from rest_framework.authtoken.models import Token
                Token.objects.filter(user=user).delete()
                print("删除用户Token")
            except:
                pass

            # 4. 最后删除用户
            user.delete()
            deleted_info['user_deleted'] = True

            print(f"✅ 用户 {user_school_id} 及其相关数据已删除")

        except Exception as e:
            print(f"删除相关数据异常: {e}")
            raise

        return deleted_info

    def handle_application_attachments(self, applications):
        """
        处理申请相关的附件
        策略：如果附件只被当前用户的申请引用，则删除；否则保留
        """
        attachments_handled = 0

        try:


            # 收集所有附件ID
            all_attachment_ids = []
            for application in applications:
                if hasattr(application, 'Attachments'):
                    attachment_ids = application.Attachments.all().values_list('id', flat=True)
                    all_attachment_ids.extend(attachment_ids)

            # 去重
            unique_attachment_ids = list(set(all_attachment_ids))

            if not unique_attachment_ids:
                return 0

            print(f"处理 {len(unique_attachment_ids)} 个附件")

            # 检查每个附件的引用次数
            for attachment_id in unique_attachment_ids:
                try:
                    attachment = Attachment.objects.get(id=attachment_id)

                    # 检查附件被多少申请引用
                    if hasattr(attachment, 'applications'):
                        reference_count = attachment.applications.count()
                    else:
                        # 使用反向查询
                        reference_count = attachment.application_set.count()

                    # 如果只被当前用户的申请引用，删除附件
                    if reference_count <= 1:  # 只有当前申请引用
                        # 删除物理文件
                        if attachment.file and hasattr(attachment.file, 'path'):
                            import os
                            file_path = attachment.file.path
                            if os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                    print(f"删除物理文件: {file_path}")
                                except:
                                    pass

                        # 删除数据库记录
                        attachment.delete()
                        attachments_handled += 1
                        print(f"删除附件: {attachment.name}")
                    else:
                        print(f"保留附件（被 {reference_count} 个申请引用）: {attachment.name}")

                except Attachment.DoesNotExist:
                    continue
                except Exception as e:
                    print(f"处理附件异常: {e}")

        except Exception as e:
            print(f"处理附件异常: {e}")

        return attachments_handled

    def log_deletion_operation(self, operator, target_user, related_data):
        """
        记录删除操作日志
        """
        try:
            log_message = (
                f"超级管理员 {operator.school_id}({operator.name}) "
                f"于 {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} "
                f"删除了用户 {target_user.school_id}({target_user.name})"
            )

            if related_data['total_count'] > 0:
                log_message += f"，同时删除了 {related_data['total_count']} 条相关数据"

            print(f"📝 操作日志: {log_message}")

            # 可以保存到数据库日志表
            # OperationLog.objects.create(
            #     operator=operator,
            #     target_user=target_user,
            #     action_type='delete_user',
            #     description=log_message,
            #     related_data_count=related_data['total_count']
            # )

        except Exception as e:
            print(f"记录操作日志异常: {e}")