import hashlib
import secrets
import uuid

import pyotp
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    def create_user(self, school_id=None, name=None, college=None, user_type=0, password=None, **extra_fields):
        if user_type==0:
            if not school_id:
                raise ValueError('请提供学号')
            identifier = school_id
        elif user_type in [1, 2]:
            if not school_id:
                raise ValueError('请提供工号')
            identifier = school_id
        else:
            raise ValueError('无效的用户类型')

        if not name:
            raise ValueError('请提供姓名')
        if not college:
            raise ValueError('请提供学院名称')

        user = self.model(
            school_id=identifier,
            name=name,
            college=college,
            user_type=user_type,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user


# 0=学生，1=教师，2=超管
class User(AbstractBaseUser, PermissionsMixin):
    USER_TYPES = [
        (0, '学生'),
        (1, '老师'),
        (2, '超级管理员'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school_id = models.CharField(max_length=20, unique=True, verbose_name='学号或工号')
    name = models.CharField(max_length=50, verbose_name='姓名')
    college = models.CharField(max_length=100, verbose_name='学院')

    user_type = models.IntegerField(
        choices=USER_TYPES,
        default=0,
        verbose_name='用户类型'
    )

    # 学生字段
    grade = models.CharField(max_length=20, blank=True, null=True, verbose_name='年级')
    major = models.CharField(max_length=100, blank=True, null=True, verbose_name='专业')
    class_name = models.CharField(max_length=50, blank=True, null=True, verbose_name='班级')
    # 保研相关字段
    has_postgraduate_qualification = models.BooleanField(default=False, verbose_name='是否有保研资格')
    is_applying_postgraduate = models.BooleanField(default=False, verbose_name='是否申请保研')

    # 老师字段
    title = models.CharField(max_length=50, blank=True, null=True, verbose_name='职称')

    # 通用字段
    contact = models.CharField(max_length=100, blank=True, null=True, verbose_name='联系方式')
    email = models.CharField(max_length=100, blank=True, null=True, verbose_name='邮箱')

    # 2FA相关字段
    is_2fa_enabled = models.BooleanField(default=False, verbose_name='是否启用双因素认证')
    secret_key = models.CharField(max_length=32, blank=True, null=True, verbose_name='2FA密钥')
    is_2fa_required = models.BooleanField(default=False, verbose_name='是否强制要求2FA')
    last_2fa_setup_time = models.DateTimeField(null=True, blank=True, verbose_name='上次设置2FA时间')

    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD = 'school_id'
    REQUIRED_FIELDS = ['name', 'college', 'user_type']

    class Meta:
        db_table = 'user'
        verbose_name = '用户'
        verbose_name_plural = '用户'


    def __str__(self):
        return f"{self.name} ({self.school_id})"

    @property
    def is_student(self):
        return self.user_type == 0

    @property
    def is_teacher(self):
        return self.user_type == 1

    @property
    def is_admin(self):
        return self.user_type == 2

    def generate_2fa_secret(self):
        """生成新的2FA密钥和备份码"""
        if not self.secret_key:
            self.secret_key = pyotp.random_base32()

        self.is_2fa_enabled = False  # 需要验证后才能启用
        self.save()
        return self.secret_key

    def verify_totp(self, code):
        """验证TOTP验证码"""
        if not self.secret_key:
            return False

        # 验证TOTP
        totp = pyotp.TOTP(self.secret_key)
        return totp.verify(code.strip(), valid_window=1)

    def enable_2fa(self):
        """启用2FA"""
        self.is_2fa_enabled = True
        self.last_2fa_setup_time = timezone.now()
        self.save()

    def disable_2fa(self):
        """禁用2FA"""
        self.is_2fa_enabled = False
        self.secret_key = None
        self.save()

    def reset2fa(self):
        self.is_2fa_enabled = False
        self.is_2fa_required = False
        self.secret_key = None
        self.last_2fa_setup_time = None
        self.save()



class Feedback(models.Model):
    STATUS_CHOICES = [
        (0, '未处理'),
        (1, '已处理')
    ]

    IDENTITY_CHOICES = [
        (0, '学生'),
        (1, '老师')
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school_id = models.CharField(max_length=50)#school_id
    uploadtime = models.DateTimeField(default=timezone.now)
    content = models.TextField()
    status = models.IntegerField(choices=STATUS_CHOICES, default=0)
    identity = models.IntegerField(choices=IDENTITY_CHOICES, default=0)
    name = models.CharField(max_length=50, default='未知用户')
    class Meta:
        db_table = 'feedback'
        verbose_name = '用户反馈'
        verbose_name_plural = '用户反馈'
        ordering = ['-uploadtime']  # 按时间倒序排列

    def mark_as_processed(self):
        """标记为已处理"""
        self.status = 1
        self.save()

    def mark_as_unprocessed(self):
        """标记为未处理"""
        self.status = 0
        self.save()