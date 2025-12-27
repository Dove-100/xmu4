# serializers.py
from rest_framework import serializers, settings
from .models import Attachment, Application
import hashlib
from rest_framework import serializers
from django.utils import timezone
from user.models import User


class SimpleFileUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(required=True)

    class Meta:
        model = Attachment
        fields = ['id', 'name', 'file', 'file_hash', 'file_size', 'uploaded_at']
        read_only_fields = ['id', 'name', 'file_hash', 'file_size', 'uploaded_at']

    def create(self, validated_data):
        file_obj = validated_data['file']

        # 🎯 修复：在保存前设置所有字段
        validated_data['name'] = file_obj.name
        validated_data['file_size'] = file_obj.size

        # 🎯 修复：在保存前计算文件哈希
        # 创建临时副本计算哈希，避免文件指针问题
        file_copy = file_obj.file
        file_obj.seek(0)  # 重置文件指针

        hash_sha256 = hashlib.sha256()
        for chunk in file_obj.chunks(chunk_size=8192):
            hash_sha256.update(chunk)
        file_obj.seek(0)  # 再次重置文件指针

        validated_data['file_hash'] = hash_sha256.hexdigest()

        # 🎯 创建附件记录
        attachment = super().create(validated_data)

        print(f"✅ 附件创建成功: ID={attachment.id}, 名称={attachment.name}")
        print(f"文件哈希: {attachment.file_hash}")
        print(f"文件大小: {attachment.file_size} bytes")

        return attachment


class ApplicationCreateSerializer(serializers.ModelSerializer):
    # 🎯 修复 Feedback 字段定义
    Feedback = serializers.CharField(
        required=False,  # 不是必填字段
        allow_blank=True,  # 允许空字符串
        allow_null=True,  # 允许 null 值
        default='',  # 默认值为空字符串
        trim_whitespace=True  # 自动去除前后空格
    )

    attachments_array = serializers.JSONField(
        required=False,
        allow_null=True,
        default=list
    )

    class Meta:
        model = Application
        fields = ['Type', 'Title', 'ApplyScore', 'Description', 'Feedback', 'extra_data', 'attachments_array']

    def validate(self, attrs):
        """全局验证"""
        # 确保extra_data是字典
        extra_data = attrs.get('extra_data', {})
        if isinstance(extra_data, str):
            try:
                import json
                attrs['extra_data'] = json.loads(extra_data)
            except json.JSONDecodeError:
                raise serializers.ValidationError({
                    "extra_data": "extra_data必须是有效的JSON格式"
                })

        # 🎯 确保 Feedback 有默认值
        if 'Feedback' not in attrs or attrs['Feedback'] is None:
            attrs['Feedback'] = ''

        # 🎯 确保 attachments_array 有默认值
        if 'attachments_array' not in attrs:
            attrs['attachments_array'] = []

        return attrs


class ApplicationListResponseSerializer(serializers.ModelSerializer):
    """申请列表响应序列化器 - 安全版本"""

    # 关键修复：使用更安全的方式处理字段
    RealScore = serializers.SerializerMethodField()
    ReviewStatus = serializers.IntegerField(source='review_status', read_only=True)
    UploadTime = serializers.IntegerField(read_only=True)
    ModifyTime = serializers.IntegerField(read_only=True)
    FeedBack = serializers.CharField(source='Feedback', read_only=True, allow_blank=True)

    # 添加附件和额外数据字段
    Attachments = serializers.SerializerMethodField()
    attachments_array = serializers.JSONField(read_only=True, required=False)
    extra_data = serializers.SerializerMethodField()

    # 添加用户信息字段
    user_name = serializers.CharField(source='user.name', read_only=True, allow_blank=True)
    user_college = serializers.CharField(source='user.college', read_only=True, allow_blank=True)

    class Meta:
        model = Application
        fields = [
            'id', 'Type', 'Title', 'ApplyScore', 'RealScore', 'ReviewStatus',
            'UploadTime', 'ModifyTime', 'Description', 'Attachments',
            'FeedBack', 'extra_data', 'user_name', 'user_college', 'attachments_array'
        ]
        extra_kwargs = {
            'ApplyScore': {'required': False},
            'Description': {'required': False, 'allow_blank': True},
        }

    def get_RealScore(self, obj):
        """安全获取RealScore"""
        try:
            if hasattr(obj, 'Real_Score') and obj.Real_Score is not None:
                return float(obj.Real_Score)
            return 0.0
        except (TypeError, ValueError):
            return 0.0

    def get_Attachments(self, obj):
        """安全获取附件列表"""
        try:
            if hasattr(obj, 'Attachments'):
                attachments = obj.Attachments.all()
                return [
                    {
                        'id': str(attachment.file_hash),
                        'name': attachment.name or '未命名文件'
                    }
                    for attachment in attachments
                ]
            return []
        except Exception as e:
            print(f"获取附件错误: {e}")
            return []

    def get_extra_data(self, obj):
        """安全获取extra_data"""
        try:
            if obj.extra_data and isinstance(obj.extra_data, (dict, list)):
                import json
                return json.dumps(obj.extra_data, ensure_ascii=False)
            return "{}"
        except Exception as e:
            print(f"处理extra_data错误: {e}")
            return "{}"


class TeacherReReviewSerializer(serializers.Serializer):
    UploadTime = serializers.IntegerField(required=True)
    real_score = serializers.FloatField(required=True, min_value=0)  # 新的给分
    comment = serializers.CharField(required=True, max_length=500)  # 新的反馈

    def validate_real_score(self, value):
        """验证分数范围"""
        if value < 0:
            raise serializers.ValidationError("分数不能为负数")
        # 可以根据业务需求设置上限
        max_score = getattr(settings, 'MAX_APPLICATION_SCORE', 100)
        if value > max_score:
            raise serializers.ValidationError(f"分数不能超过{max_score}")
        return value

    def validate(self, attrs):
        """全局验证"""
        upload_time = attrs['UploadTime']

        try:
            # 🔍 根据UploadTime查找申请记录
            application = Application.objects.get(
                UploadTime=upload_time,
                status__in=[2, 3]  # 只允许重新审核已审核的记录（通过/不通过）
            )

            # 👨‍🏫 可选：验证老师权限
            if not self._check_teacher_permission(application, self.context['request'].user):
                raise serializers.ValidationError("您没有权限重新审核此申请")

            attrs['application'] = application
            return attrs

        except Application.DoesNotExist:
            raise serializers.ValidationError(
                f"未找到已审核的申请记录（UploadTime: {upload_time}）"
            )
        except Application.MultipleObjectsReturned:
            raise serializers.ValidationError("找到多个相同UploadTime的申请记录，请联系管理员")

    def _check_teacher_permission(self, application, teacher):
        """检查老师是否有权限重新审核"""
        # 根据业务逻辑实现，如：
        # - 是否是原审核老师
        # - 同院系老师
        # - 特定权限的老师
        return True


class ApplicationChangeReviewSerializer(serializers.Serializer):
    UploadTime = serializers.IntegerField(required=True, help_text="申请上传时间戳(毫秒)")
    result = serializers.BooleanField(required=True, help_text="是否通过")
    comment = serializers.CharField(required=True, max_length=500, help_text="教师反馈")

    def validate(self, attrs):
        # 直接使用整数时间戳查找
        try:
            application = Application.objects.get(UploadTime=attrs['UploadTime'])
            attrs['application'] = application
        except Application.DoesNotExist:
            raise serializers.ValidationError("未找到对应的申请记录")

        # 验证申请状态是否为已审核状态
        if application.review_status not in [2, 3]:
            raise serializers.ValidationError("该申请当前不可更改审核")

        return attrs


class ApplicationRevokeReviewSerializer(serializers.Serializer):
    # 支持两种参数名称
    UploadTime = serializers.IntegerField(required=False)
    id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        # 🎯 兼容两种参数格式
        upload_time = attrs.get('UploadTime') or attrs.get('id')

        if not upload_time:
            raise serializers.ValidationError("请提供申请标识参数: UploadTime 或 id")

        try:
            # 查找申请记录 - 只允许撤销已审核的申请（状态2或3）
            application = Application.objects.get(
                UploadTime=upload_time,
                review_status__in=[2, 3]  # 2=通过, 3=不通过
            )

            attrs['application'] = application
            attrs['upload_time'] = upload_time
            return attrs

        except Application.DoesNotExist:
            # 尝试范围查找（处理精度问题）
            time_range_start = upload_time - 5000
            time_range_end = upload_time + 5000

            applications = Application.objects.filter(
                UploadTime__range=(time_range_start, time_range_end),
                review_status__in=[2, 3]
            )

            if applications.exists():
                application = applications.first()
                print(f"通过范围查找找到申请: {application.id}")
                attrs['application'] = application
                attrs['upload_time'] = application.UploadTime
                return attrs
            else:
                raise serializers.ValidationError(f"未找到已审核的申请记录 (id: {upload_time})")

        except Application.MultipleObjectsReturned:
            raise serializers.ValidationError("找到多个相同标识的申请记录，请联系管理员")


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
        """安全获取附件列表"""
        try:
            if hasattr(obj, 'Attachments'):
                attachments = obj.Attachments.all()
                return [
                    {
                        'id': str(attachment.file_hash),
                        'name': attachment.name or '未命名文件'
                    }
                    for attachment in attachments
                ]
            return []
        except Exception as e:
            print(f"获取附件错误: {e}")
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