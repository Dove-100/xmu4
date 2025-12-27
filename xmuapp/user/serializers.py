import re
import secrets

from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User, Feedback

from score.models import AcademicPerformance
from application.models import Application
# serializers.py
from rest_framework import serializers
from django.core.exceptions import ValidationError
from .models import User

from rest_framework import serializers
import qrcode
import base64
from io import BytesIO
from django.contrib.auth import authenticate
from .models import User


class TwoFactorSetupSerializer(serializers.Serializer):
    """2FA设置序列化器"""
    secret = serializers.CharField(read_only=True)
    qr_code = serializers.CharField(read_only=True)

    def to_representation(self, instance):
        """生成2FA设置信息"""
        user = instance

        # 生成或获取密钥
        secret = user.secret_key
        if not secret:
            secret = user.generate_2fa_secret()

        # 生成二维码
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )

        # 生成OTP URI
        otp_uri = f"otpauth://totp/XMUGraduate:{user.school_id}?secret={secret}&issuer=XMUGraduate"
        qr.add_data(otp_uri)
        qr.make(fit=True)

        # 创建二维码图片
        img = qr.make_image(fill_color="black", back_color="white")

        # 转换为base64
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
        qr_data_url = f"data:image/png;base64,{qr_base64}"

        return {
            'secret': secret,
            'qr_code': qr_data_url,
            'message': '请使用身份验证器应用（如Google Authenticator、Microsoft Authenticator等）扫描二维码，然后输入生成的6位验证码完成设置。'
        }


class Verify2FASerializer(serializers.Serializer):
    """验证2FA序列化器"""
    code = serializers.CharField(write_only=True, max_length=8)

    def validate(self, data):
        user = self.context['user']
        code = data.get('code')

        if not user.verify_totp(code):
            raise serializers.ValidationError("验证码无效")

        # 验证成功后启用2FA
        if not user.is_2fa_enabled:
            user.enable_2fa()

        return data


class LoginSerializer(serializers.Serializer):
    school_id = serializers.CharField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    user_type = serializers.CharField()
    code = serializers.CharField(required=False, allow_blank=True, max_length=8)

    def validate(self, data):
        school_id = data.get('school_id')
        password = data.get('password')
        user_type = data.get('user_type')
        code = data.get('code', '')

        print(f"=== 登录验证 ===")
        print(f"学号: {school_id}")
        print(f"用户类型: {user_type}")

        if school_id and password:
            # 🎯 第一步：先验证用户名和密码
            user = authenticate(username=school_id, password=password)

            if not user:
                print(f"❌ 用户名或密码错误: {school_id}")
                raise serializers.ValidationError("学号/工号或密码错误")

            # 🎯 第二步：验证用户类型是否匹配
            print(f"数据库用户类型: {user.user_type}, 请求用户类型: {user_type}")

            # 用户类型映射
            user_type_mapping = {
                'student': 0,
                'teacher': 1,
                'super': 2
            }

            expected_type = user_type_mapping.get(user_type.lower())
            if expected_type is None:
                print(f"❌ 无效的用户类型: {user_type}")
                raise serializers.ValidationError("无效的用户类型")

            if user.user_type != expected_type:
                print(f"❌ 用户类型不匹配: 期望{expected_type}({user_type}), 实际{user.user_type}")
                raise serializers.ValidationError("用户类型不匹配，请选择正确的登录入口")

            # 🎯 第三步：检查用户状态
            if not user.is_active:
                print(f"❌ 用户已被禁用: {school_id}")
                raise serializers.ValidationError("账号已被禁用")

            print(f"✅ 基础验证通过: {school_id} ")
            print(f"2FA状态: enabled={user.is_2fa_enabled}, required={user.is_2fa_required}")

            # 如果用户没有启用2FA，检查是否需要强制设置
            if not user.is_2fa_enabled:
                print(f"✅ 不需要2FA，直接登录")
                data['user'] = user
                data['requires_2fa'] = False
                return data

            # 🎯 第五步：用户已启用2FA，需要验证code
            print(f"用户已启用2FA，验证验证码...")

            if not code or not code.strip():
                print(f"❌ 需要2FA验证码但未提供")
                raise serializers.ValidationError(
                    "需要双因素认证验证码",
                    code='requires_2fa_code'
                )

            # 验证2FA验证码
            if user.verify_totp(code.strip()):
                print(f"✅ 2FA验证通过")
                data['user'] = user
                data['requires_2fa'] = True
                data['code_valid'] = True
                return data
            else:
                print(f"❌ 2FA验证码无效: {code}")
                raise serializers.ValidationError(
                    "双因素认证验证码无效",
                    code='invalid_2fa_code'
                )

            print(f"✅ 登录验证通过: {school_id} ({user.name})")
            data['user'] = user
            return data
        else:
            raise serializers.ValidationError("请提供学号/工号和密码")



class VerifyLogin2FASerializer(serializers.Serializer):
    """登录时验证2FA序列化器"""
    school_id = serializers.CharField()
    code = serializers.CharField(max_length=8)


class Request2FAResetSerializer(serializers.Serializer):
    """请求重置2FA序列化器"""
    school_id = serializers.CharField()
    user_type = serializers.CharField()

    def validate(self, data):
        school_id = data.get('school_id')
        user_type = data.get('user_type')

        try:
            user = User.objects.get(school_id=school_id)
        except User.DoesNotExist:
            raise serializers.ValidationError("用户不存在")

        # 验证用户类型
        user_type_mapping = {
            'student': 0,
            'teacher': 1,
            'super': 2
        }

        expected_type = user_type_mapping.get(user_type.lower())
        if expected_type is None:
            raise serializers.ValidationError("无效的用户类型")

        if user.user_type != expected_type:
            raise serializers.ValidationError("用户类型不匹配")

        # 检查用户是否启用了2FA
        if not user.is_2fa_enabled:
            raise serializers.ValidationError("您的账户未启用双因素认证")

        data['user'] = user
        return data


class AdminAccountListSerializer(serializers.ModelSerializer):
    """管理员账号列表序列化器 - 根据用户类型动态返回字段"""
    ID = serializers.CharField(source='school_id', read_only=True)
    Name = serializers.CharField(source='name', read_only=True)
    Score = serializers.SerializerMethodField(read_only=True)

    # 学生和老师共有的字段
    Grade = serializers.CharField(source='grade', read_only=True, allow_null=True)
    Major = serializers.CharField(source='major', read_only=True, allow_null=True)
    Class = serializers.CharField(source='class_name', read_only=True, allow_null=True)
    College = serializers.CharField(source='college', read_only=True)
    Type = serializers.IntegerField(source='user_type', read_only=True)  # 直接返回user_type字段

    class Meta:
        model = User
        fields = ['ID', 'Name', 'Score', 'Grade', 'Major', 'Class', 'College', 'Type']

    def get_Score(self, obj):
        """动态返回分数：只有学生有分数，老师返回None"""
        if obj.user_type == 0:  # 学生
            try:
                academic_perf = AcademicPerformance.objects.filter(user=obj).first()
                if academic_perf and academic_perf.total_comprehensive_score:
                    return float(academic_perf.total_comprehensive_score)
                else:
                    return 0.0  # 学生但没有成绩记录，返回0
            except Exception as e:
                print(f"获取学生 {obj.school_id} 成绩失败: {e}")
                return 0.0
        else:
            # 老师返回 None，前端会忽略这个字段
            return None

    def to_representation(self, instance):
        """重写此方法，动态控制返回的字段"""
        data = super().to_representation(instance)

        # 如果是老师，移除Score字段
        if instance.user_type == 1:  # 老师
            data.pop('Score', None)

        return data


# serializers.py
class AdminAccountListRequestSerializer(serializers.Serializer):
    """管理员获取账号列表请求参数序列化器"""
    type = serializers.CharField(  # 改为CharField接收字符串
        required=True,
        help_text="用户类型: '0'-学生, '1'-老师 或 'false'-学生, 'true'-老师"
    )
    major = serializers.IntegerField(
        required=True,
        min_value=-1,
        max_value=4,
        help_text="专业: 对于老师传-1(全部), 对于学生: 0-计科, 1-软工, 2-智能, 3-网安, 4-全部专业"
    )

    def validate_type(self, value):
        """转换type参数为整数"""
        print(f"原始type参数: {value}, 类型: {type(value)}")

        # 支持多种格式
        if value in ['0', 'false', 'False']:
            return 0  # 学生
        elif value in ['1', 'true', 'True']:
            return 1  # 老师
        else:
            try:
                # 尝试直接转换为整数
                int_value = int(value)
                if int_value in [0, 1]:
                    return int_value
                else:
                    raise serializers.ValidationError("type参数必须是0或1")
            except (ValueError, TypeError):
                raise serializers.ValidationError("type参数格式错误，支持: 0/false(学生) 或 1/true(老师)")

    def validate(self, attrs):
        """验证参数逻辑"""
        user_type = attrs['type']  # 已经是整数: 0-学生, 1-老师
        major = attrs['major']

        print(f"验证后参数 - type: {user_type}, major: {major}")

        # 如果是老师，major必须为-1
        if user_type == 1 and major != -1:
            raise serializers.ValidationError({
                "major": "当查询老师时，major参数必须为-1"
            })

        # 如果是学生，major必须在-1到4范围内
        if user_type == 0 and major not in [-1, 0, 1, 2, 3, 4]:
            raise serializers.ValidationError({
                "major": "当查询学生时，major参数必须在-1到4范围内"
            })

        return attrs


# serializers.py - 修正版本
class UniversalStudentDetailSerializer(serializers.ModelSerializer):
    school_id = serializers.CharField()
    name = serializers.CharField()
    department = serializers.SerializerMethodField()
    phone = serializers.CharField(source='contact')
    email = serializers.SerializerMethodField()
    rank = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    academy_score = serializers.SerializerMethodField()
    cet4 = serializers.SerializerMethodField()
    cet6 = serializers.SerializerMethodField()
    applications_score = serializers.SerializerMethodField()
    applications_approved = serializers.SerializerMethodField()
    applications_rejected = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'school_id', 'name', 'department', 'phone', 'email',
            'rank', 'score', 'academy_score', 'cet4', 'cet6',
            'applications_score', 'applications_approved', 'applications_rejected'
        ]

    def get_department(self, obj):
        """构建学院-系-专业格式"""
        college = obj.college or ""
        major = obj.major or ""
        return f"{college}-{major}".rstrip('-')

    def get_email(self, obj):
        return f"{obj.email}"

    def get_rank(self, obj):
        """获取排名信息"""
        try:
            performance = obj.academic_performance
            return [performance.gpa_ranking or 0, 0]  # 专业总人数需要根据实际情况获取
        except:
            return [0, 0]

    def get_score(self, obj):
        """获取综测分数"""
        try:
            return obj.academic_performance.total_comprehensive_score
        except:
            return 0

    def get_academy_score(self, obj):
        """获取绩点"""
        try:
            return obj.academic_performance.gpa
        except:
            return 0

    def get_cet4(self, obj):
        """获取四级成绩"""
        try:
            return obj.academic_performance.cet4
        except:
            return 0

    def get_cet6(self, obj):
        """获取六级成绩"""
        try:
            return obj.academic_performance.cet6
        except:
            return 0

    def get_applications_score(self, obj):
        """获取9类申请得分 - 修正版本"""
        try:
            # 使用正确的related_name: 'applications'
            applications = obj.applications.all()
            scores = [0] * 9

            for app in applications:
                if 0 <= app.Type <= 8:
                    scores[app.Type] = float(app.ApplyScore or 0)
            return scores
        except Exception as e:
            print(f"获取申请得分错误: {e}")
            return [0] * 9

    def get_applications_approved(self, obj):
        """通过申请数 - 修正版本"""
        try:
            # 审核通过状态为2
            return obj.applications.filter(review_status=2).count()
        except:
            return 0

    def get_applications_rejected(self, obj):
        """拒绝申请数 - 修正版本"""
        try:
            # 审核不通过状态为3
            return obj.applications.filter(review_status=3).count()
        except:
            return 0


# serializers.py - 教师序列化器
class TeacherDetailSerializer(serializers.ModelSerializer):
    name = serializers.CharField()
    department = serializers.CharField(source='college')
    phone = serializers.CharField(source='contact')
    email = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['name','department', 'phone', 'email']

    def get_email(self, obj):
        return f"{obj.email}"


class SafeTeacherPendingApplicationListSerializer(serializers.ModelSerializer):
    """超级安全的老师待审核申请列表序列化器 - 修复版本"""

    # 关键修复：确保字段映射正确
    RealScore = serializers.DecimalField(
        source='Real_Score',
        max_digits=7,
        decimal_places=4,
        read_only=True
    )
    ReviewStatus = serializers.IntegerField(source='review_status', read_only=True)
    UploadTime = serializers.IntegerField(read_only=True)
    ModifyTime = serializers.IntegerField(read_only=True)
    FeedBack = serializers.CharField(source='Feedback', read_only=True)

    # 添加用户信息
    user_name = serializers.CharField(source='user.name', read_only=True)
    user_college = serializers.CharField(source='user.college', read_only=True)
    user_school_id = serializers.CharField(source='user.school_id', read_only=True)

    # 添加附件和额外数据
    Attachments = serializers.SerializerMethodField()
    extra_data = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            'id', 'Type', 'Title', 'ApplyScore', 'RealScore', 'ReviewStatus',
            'UploadTime', 'ModifyTime', 'Description', 'Attachments',
            'FeedBack', 'extra_data', 'user_name', 'user_college', 'user_school_id'
        ]

    def get_Attachments(self, obj):
        """获取附件列表"""
        try:
            attachments = obj.Attachments.all()
            return [
                {
                    'id': str(attachment.id),
                    'name': attachment.name
                }
                for attachment in attachments
            ]
        except Exception as e:
            return []

    def get_extra_data(self, obj):
        """安全获取extra_data"""
        try:
            if obj.extra_data:
                import json
                return json.dumps(obj.extra_data, ensure_ascii=False)
            return "{}"
        except Exception as e:
            return "{}"


# serializers.py - 修正验证规则
class TeacherRegistrationSerializer(serializers.ModelSerializer):
    department = serializers.CharField(write_only=True, required=True, label="部门")
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['school_id', 'name', 'department', 'password']
        extra_kwargs = {
            'school_id': {'required': True, 'error_messages': {'required': '工号是必需的'}},
            'name': {'required': True, 'error_messages': {'required': '姓名是必需的'}},
            'department': {'required': True, 'error_messages': {'required': '部门是必需的'}}
        }

    def validate_school_id(self, value):
        if not value or value.strip() == "":
            raise serializers.ValidationError("工号不能为空")
        if User.objects.filter(school_id=value).exists():
            raise serializers.ValidationError(f"工号 {value} 已被注册")
        return value.strip()

    def validate_name(self, value):
        if not value or value.strip() == "":
            raise serializers.ValidationError("姓名不能为空")
        return value.strip()

    def validate_department(self, value):
        """放宽部门格式验证"""
        if not value or value.strip() == "":
            raise serializers.ValidationError("部门不能为空")

        # 允许单独的学院名称，不强制要求包含系
        return value.strip()

    def create(self, validated_data):
        """创建教师用户"""
        department = validated_data.pop('department')
        password = validated_data.pop('password', None)

        password = validated_data.pop('password', '123456')

        try:
            # 创建教师用户 - 将department存储到college字段
            teacher = User.objects.create_user(
                school_id=validated_data['school_id'],
                name=validated_data['name'],
                college=department,  # 将部门信息存储到college字段
                user_type=1,  # 教师类型
                password=password
            )

            # 保存生成的密码用于响应
            teacher._generated_password = password
            return teacher

        except Exception as e:
            raise serializers.ValidationError(f"创建教师账号失败: {str(e)}")


from django.db import transaction


class StudentRegistrationSerializer(serializers.ModelSerializer):
    """
    学生注册序列化器 - 修复版本
    """
    # User模型字段
    college = serializers.CharField(required=True, label="学院")
    major = serializers.CharField(required=True, label="专业")
    grade = serializers.CharField(required=False, label="年级", allow_blank=True)
    password = serializers.CharField(
        write_only=True,
        required=False,
        label="密码",
        allow_blank=True
    )

    # AcademicPerformance模型字段
    gpa = serializers.DecimalField(
        max_digits=7,
        decimal_places=4,
        required=False,  # 🎯 修复：改为 required=False
        label="学分绩点",
        min_value=0,
        max_value=5
    )
    cet4 = serializers.IntegerField(
        required=False,  # 🎯 修复：改为 required=False
        label="大学英语四级",
        min_value=-1,
        max_value=710
    )
    cet6 = serializers.IntegerField(
        required=False,  # 🎯 修复：改为 required=False
        label="大学英语六级",
        min_value=-1,
        max_value=710
    )

    # 其他学业字段
    academic_score = serializers.DecimalField(
        max_digits=7,
        decimal_places=4,
        required=False,
        label="学业成绩(满分80分)",
        min_value=0,
        max_value=80
    )
    weighted_score = serializers.DecimalField(
        max_digits=7,
        decimal_places=4,
        required=False,
        label="加权分数",
        min_value=0
    )

    class Meta:
        model = User
        fields = [
            'school_id', 'name', 'college', 'major', 'grade', 'password',
            'gpa', 'cet4', 'cet6', 'academic_score', 'weighted_score'
        ]
        extra_kwargs = {
            'school_id': {'required': True, 'trim_whitespace': True},
            'name': {'required': True, 'trim_whitespace': True},
            'college': {'required': True, 'trim_whitespace': True},
            'major': {'required': True, 'trim_whitespace': True},
        }

    def __init__(self, *args, **kwargs):
        """初始化时设置默认值"""
        super().__init__(*args, **kwargs)

        # 设置默认值
        self.fields['grade'].default = '2024'
        self.fields['password'].default = '123456'
        self.fields['gpa'].default = 0.0000
        self.fields['cet4'].default = -1
        self.fields['cet6'].default = -1
        self.fields['academic_score'].default = 0.0000
        self.fields['weighted_score'].default = 0.0000

    def validate(self, attrs):
        """全局验证并设置默认值"""
        print("=== 开始全局验证 ===")

        # 🎯 设置默认值（如果字段缺失）
        defaults = {
            'grade': '2024',
            'password': '123456',
            'gpa': 0.0000,
            'cet4': -1,
            'cet6': -1,
            'academic_score': 0.0000,
            'weighted_score': 0.0000,
        }

        for field, default_value in defaults.items():
            if field not in attrs:
                attrs[field] = default_value
                print(f"设置默认值: {field} = {default_value}")

        # 验证学号唯一性
        school_id = attrs.get('school_id', '').strip()
        if User.objects.filter(school_id=school_id).exists():
            raise serializers.ValidationError({
                'school_id': f"学号 {school_id} 已被注册"
            })

        # 验证学分绩点范围
        gpa = attrs.get('gpa', 0.0000)
        if gpa < 0 or gpa > 5:
            raise serializers.ValidationError({
                'gpa': "学分绩点应在0-5之间"
            })

        # 验证四级成绩
        cet4 = attrs.get('cet4', -1)
        if cet4 != -1 and (cet4 < 0 or cet4 > 710):
            raise serializers.ValidationError({
                'cet4': "四级成绩应在0-710之间（-1表示未参加）"
            })

        # 验证六级成绩
        cet6 = attrs.get('cet6', -1)
        if cet6 != -1 and (cet6 < 0 or cet6 > 710):
            raise serializers.ValidationError({
                'cet6': "六级成绩应在0-710之间（-1表示未参加）"
            })

        # 验证学业成绩
        academic_score = attrs.get('academic_score', 0.0000)
        if academic_score < 0 or academic_score > 80:
            raise serializers.ValidationError({
                'academic_score': "学业成绩应在0-80之间"
            })

        print("✅ 全局验证通过")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """
        创建学生用户并初始化学业成绩表
        """
        try:
            print("=== 开始创建学生 ===")
            print(f"验证后的数据: {validated_data}")

            # 🎯 提取AcademicPerformance数据
            academic_data = {
                'gpa': validated_data.pop('gpa', 0.0000),
                'cet4': validated_data.pop('cet4', -1),
                'cet6': validated_data.pop('cet6', -1),
                'academic_score': validated_data.pop('academic_score', 0.0000),
                'weighted_score': validated_data.pop('weighted_score', 0.0000),
                # 其他默认字段
                'academic_expertise_score': 0.0000,
                'comprehensive_performance_score': 0.0000,
                'total_comprehensive_score': 0.0000,
                'applications_score': [],
                'total_courses': 0,
                'total_credits': 0.0000,
                'gpa_ranking': 0,
                'ranking_dimension': '专业内排名',
                'failed_courses': 0,
            }

            # 🎯 提取密码
            password = validated_data.pop('password', '123456')

            # 🎯 设置用户类型为学生
            validated_data['user_type'] = 0

            print(f"User创建参数: {validated_data}")
            print(f"AcademicPerformance创建参数: {academic_data}")

            # 🎯 创建User记录
            try:
                student = User.objects.create_user(
                    **validated_data,
                    password=password
                )
                print(f"✅ User创建成功: {student.school_id}")
            except Exception as user_error:
                print(f"❌ User创建失败: {user_error}")
                raise serializers.ValidationError(f"创建用户失败: {str(user_error)}")

            # 🎯 创建AcademicPerformance记录
            try:
                academic_performance = AcademicPerformance.objects.create(
                    user=student,
                    **academic_data
                )
                print(f"✅ AcademicPerformance创建成功")
                print(
                    f"成绩信息: GPA={academic_data['gpa']}, CET4={academic_data['cet4']}, CET6={academic_data['cet6']}")

            except Exception as academic_error:
                print(f"❌ AcademicPerformance创建失败: {academic_error}")
                import traceback
                print(f"错误详情: {traceback.format_exc()}")
                raise serializers.ValidationError(f"创建学业成绩失败: {str(academic_error)}")

            return student

        except Exception as e:
            print(f"❌ 创建学生异常: {str(e)}")
            import traceback
            print(f"错误堆栈: {traceback.format_exc()}")
            raise serializers.ValidationError(f"创建学生账号失败: {str(e)}")


# serializers.py - 添加批量导入序列化器
from rest_framework import serializers
import pandas as pd


class BulkUserImportSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    user_type = serializers.ChoiceField(
        choices=[(0, '学生'), (1, '老师')],
        required=True,
        help_text='用户类型：0=学生，1=老师'
    )

    def validate_file(self, value):
        """验证文件格式"""
        if not value.name.endswith(('.xlsx', '.xls')):
            raise serializers.ValidationError("只支持Excel文件 (.xlsx, .xls)")
        return value

    def validate(self, attrs):
        """全局验证"""
        file = attrs['file']
        user_type = attrs['user_type']

        try:
            # 读取Excel文件
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file, engine='openpyxl')
            else:
                df = pd.read_excel(file)

            # 验证列名
            if user_type == 1:  # 老师
                required_columns = ['账号', '姓名', '单位']
            else:  # 学生
                required_columns = ['账号', '姓名', '单位', '专业', '绩点', '四级分数', '六级分数']

            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise serializers.ValidationError(f"缺少必要列: {', '.join(missing_columns)}")

            # 验证数据
            errors = self._validate_data(df, user_type)
            if errors:
                raise serializers.ValidationError({"data_errors": errors})

            attrs['dataframe'] = df
            return attrs

        except Exception as e:
            raise serializers.ValidationError(f"文件解析失败: {str(e)}")

    def _validate_data(self, df, user_type):
        """验证数据有效性"""
        errors = []

        for index, row in df.iterrows():
            row_num = index + 2  # Excel行号（从2开始，第1行是标题）

            # 检查必填字段
            if pd.isna(row['账号']) or str(row['账号']).strip() == '':
                errors.append(f"第{row_num}行: 账号不能为空")
                continue

            if pd.isna(row['姓名']) or str(row['姓名']).strip() == '':
                errors.append(f"第{row_num}行: 姓名不能为空")
                continue

            if pd.isna(row['单位']) or str(row['单位']).strip() == '':
                errors.append(f"第{row_num}行: 单位不能为空")
                continue

            # 检查账号是否已存在
            school_id = str(row['账号']).strip()
            if User.objects.filter(school_id=school_id).exists():
                errors.append(f"第{row_num}行: 账号 '{school_id}' 已存在")
                continue

            # 学生特定验证
            if user_type == 0:
                if pd.isna(row['专业']) or str(row['专业']).strip() == '':
                    errors.append(f"第{row_num}行: 专业不能为空")
                    continue

                # 验证绩点
                try:
                    gpa = float(row['绩点']) if not pd.isna(row['绩点']) else 0.0
                    if gpa < 0 or gpa > 4.0:
                        errors.append(f"第{row_num}行: 绩点必须在0-4.0之间")
                except (ValueError, TypeError):
                    errors.append(f"第{row_num}行: 绩点格式错误")

                # 验证四级分数
                try:
                    cet4 = int(row['四级分数']) if not pd.isna(row['四级分数']) else -1
                    if cet4 != -1 and (cet4 < 0 or cet4 > 710):
                        errors.append(f"第{row_num}行: 四级分数必须在0-710之间或为空")
                except (ValueError, TypeError):
                    errors.append(f"第{row_num}行: 四级分数格式错误")

                # 验证六级分数
                try:
                    cet6 = int(row['六级分数']) if not pd.isna(row['六级分数']) else -1
                    if cet6 != -1 and (cet6 < 0 or cet6 > 710):
                        errors.append(f"第{row_num}行: 六级分数必须在0-710之间或为空")
                except (ValueError, TypeError):
                    errors.append(f"第{row_num}行: 六级分数格式错误")

        return errors



from rest_framework import serializers
from django.core.validators import EmailValidator, validate_email


class UserContactUpdateSerializer(serializers.ModelSerializer):
    email = serializers.CharField(
        max_length=100,
        required=True,  # 必需字段
        label="邮箱"
    )
    phone = serializers.CharField(
        max_length=100,
        required=True,
        label="手机号",
        write_only=True  # 只用于写入，不用于读取
    )

    class Meta:
        model = User
        fields = ['email', 'phone']
        read_only_fields = ['id', 'school_id', 'name']

    def validate_phone(self, value):
        """验证手机号"""
        value = value.strip()
        if not value:
            raise serializers.ValidationError("手机号不能为空")

        # 验证手机号格式（简单版本）
        if not re.match(r'^1[3-9]\d{9}$', value):
            raise serializers.ValidationError("请输入有效的11位手机号")

        return value

    def validate_email(self, value):
        """验证邮箱"""
        value = value.strip().lower()
        if not value:
            raise serializers.ValidationError("邮箱不能为空")

        try:
            validate_email(value)
        except ValidationError:
            raise serializers.ValidationError("请输入有效的邮箱地址")

        return value

    def update(self, instance, validated_data):
        """更新用户联系信息"""
        print(f"=== 更新用户联系信息 ===")
        print(f"用户: {instance.school_id} ({instance.name})")
        print(f"原始邮箱: {instance.email}, 原始联系方式: {instance.contact}")
        print(f"新邮箱: {validated_data.get('email')}, 新手机号: {validated_data.get('phone')}")

        # 🎯 直接更新字段
        instance.email = validated_data.get('email', instance.email)
        instance.contact = validated_data.get('phone', instance.contact)

        instance.save()

        print(f"✅ 更新成功: 邮箱={instance.email}, 联系方式={instance.contact}")
        return instance


from rest_framework import serializers
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError


class ChangePasswordSerializer(serializers.Serializer):
    """
    修改密码序列化器
    """
    old_password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=1,
        error_messages={
            'required': '请输入原密码',
            'blank': '原密码不能为空'
        }
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=6,
        error_messages={
            'required': '请输入新密码',
            'min_length': '新密码至少需要6位',
            'blank': '新密码不能为空'
        }
    )
    confirm_password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=6,
        error_messages={
            'required': '请再次输入新密码',
            'min_length': '确认密码至少需要6位',
            'blank': '确认密码不能为空'
        }
    )

    def validate_old_password(self, value):
        """验证原密码"""
        if not value.strip():
            raise serializers.ValidationError("原密码不能为空")
        return value

    def validate_new_password(self, value):
        """验证新密码"""
        if not value.strip():
            raise serializers.ValidationError("新密码不能为空")

        # 密码强度验证（可根据需求调整）
        if len(value) < 6:
            raise serializers.ValidationError("新密码至少需要6位")

        # 可以添加更多密码强度规则
        # if not any(char.isdigit() for char in value):
        #     raise serializers.ValidationError("密码必须包含至少一个数字")
        # if not any(char.isalpha() for char in value):
        #     raise serializers.ValidationError("密码必须包含至少一个字母")

        return value

    def validate(self, data):
        """交叉验证"""
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')

        # 验证新旧密码不能相同
        if old_password and new_password and old_password == new_password:
            raise serializers.ValidationError({
                'new_password': '新密码不能与原密码相同'
            })

        # 验证两次输入的新密码是否一致
        if new_password != confirm_password:
            raise serializers.ValidationError({
                'confirm_password': '两次输入的密码不一致'
            })

        return data




class CreateFeedbackSerializer(serializers.Serializer):
    """创建反馈序列化器"""
    content = serializers.CharField(
        max_length=2000,
        min_length=1,
        error_messages={
            'required': '反馈内容不能为空',
            'min_length': '反馈内容至少需要1个字符',
            'max_length': '反馈内容不能超过2000个字符'
        }
    )

    def validate_content(self, value):
        """验证反馈内容"""
        content = value.strip()
        if not content:
            raise serializers.ValidationError("反馈内容不能为空")

        return content


class FeedbackListSerializer(serializers.ModelSerializer):
    """序列化器：后端小写 -> 前端大写"""
    Status = serializers.SerializerMethodField()  # 前端字段名（大写）
    UploadTime = serializers.SerializerMethodField()
    ID = serializers.SerializerMethodField()
    Identity = serializers.SerializerMethodField()
    Name = serializers.SerializerMethodField()
    Content = serializers.SerializerMethodField()

    class Meta:
        model = Feedback
        fields = ['Status', 'UploadTime', 'ID', 'Identity', 'Name', 'Content']  # 不在Meta中定义，完全自定义

    def get_Status(self, obj):
        """将后端的status映射到前端的Status"""
        # obj.status 是后端字段（小写）
        return obj.status

    def get_UploadTime(self, obj):
        """将后端的uploadtime映射到前端的UploadTime"""
        return int(obj.uploadtime.timestamp() * 1000)

    def get_ID(self, obj):
        """将后端的school_id映射到前端的ID"""
        return obj.school_id

    def get_Identity(self, obj):
        """将后端的identity映射到前端的Identity"""
        return obj.identity

    def get_Name(self, obj):
        """将后端的name映射到前端的Name"""
        return obj.name

    def get_Content(self, obj):
        """将后端的content映射到前端的Content"""
        return obj.content

class AdminFeedbackSerializer(serializers.ModelSerializer):
    """管理员查看反馈详情序列化器"""

    class Meta:
        model = Feedback
        fields = [
            'id', 'content', 'status', 'uploadtime'
        ]

    def get_upload_time_str(self, obj):
        """格式化上传时间"""
        return obj.uploadtime.strftime('%Y-%m-%d %H:%M:%S') if obj.uploadtime else ''


class ProcessFeedbackSerializer(serializers.Serializer):
    """处理反馈序列化器"""
    feedback_id = serializers.UUIDField()

    def validate_feedback_id(self, value):
        """验证反馈ID是否存在"""
        try:
            feedback = Feedback.objects.get(id=value, is_deleted=False)
        except Feedback.DoesNotExist:
            raise serializers.ValidationError("反馈不存在")

        return feedback
