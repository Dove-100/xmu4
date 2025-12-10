import hashlib
import secrets
import uuid
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

