import hashlib
import time
import uuid

from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import FileField
from django.utils import timezone

from user.models import User

from score.models import AcademicPerformance


class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, blank=True, verbose_name='附件名称')
    file = models.FileField(
        upload_to='applications/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name='附件文件',
        validators=[FileExtensionValidator(
            allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'pdf', 'doc', 'docx']
        )]
    )
    # 新增哈希字段
    file_hash = models.CharField(
        max_length=64,  # SHA-256哈希值长度
        blank=True,
        null=True,
        verbose_name='文件哈希值',
        help_text='文件的SHA-256哈希值，用于文件完整性验证'
    )
    file_size = models.BigIntegerField(
        default=0,
        verbose_name='文件大小(字节)'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'attachment'
        verbose_name = '附件'
        verbose_name_plural = '附件'
        # 添加哈希值索引
        indexes = [
            models.Index(fields=['file_hash']),
        ]

    def __str__(self):
        return self.name or f"附件_{self.id}"

    def calculate_file_hash(self):
        """计算文件的SHA-256哈希值"""
        if not self.file:
            return None

        try:
            hash_sha256 = hashlib.sha256()
            # 分块读取文件计算哈希，避免大文件内存溢出
            for chunk in self.file.chunks(chunk_size=8192):
                hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            print(f"计算文件哈希错误: {e}")
            return None

    def save(self, *args, **kwargs):
        """重写save方法，自动计算哈希值"""
        if self.file and not self.file_hash:
            self.file_hash = self.calculate_file_hash()
            self.file_size = self.file.size
        super().save(*args, **kwargs)

class ReviewMixin(models.Model):
    """审核混入类"""
    REVIEW_STATUS = [
        (0, '草稿'),
        (1, '待审核'),
        (2, '审核通过'),
        (3, '审核不通过'),
    ]

    # 一审相关字段
    first_reviewer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='first_reviewed_%(class)s',
        verbose_name='一审老师'
    )
    first_review_comment = models.TextField(blank=True, null=True, verbose_name='一审意见')
    first_reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='一审时间')

    # 审核状态
    review_status = models.IntegerField(
        choices=REVIEW_STATUS,
        default=0,
        verbose_name='审核状态'
    )

    # 审核结果和加分（所有申请类型共用）
    result = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='审核结果'
    )

    Real_Score = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=0,
        verbose_name='加分'
    )

    class Meta:
        abstract = True






class Application(ReviewMixin):
    """统一的申请表"""

    # 申请类型
    APPLICATION_TYPES = [
        (0, '学术竞赛成绩'),
        (1, '创新训练成绩'),
        (2, '学术研究成绩'),
        (3, '荣誉称号成绩'),
        (4, '社会工作成绩'),
        (5, '志愿服务成绩'),
        (6, '国际实习成绩'),
        (7, '参军入伍成绩'),
        (8, '体育项目成绩')
    ]

    # 论文类别
    PAPER_CATEGORIES = [
        ('A', 'A类论文'),
        ('B', 'B类论文'),
        ('C', 'C类论文')
    ]

    PAPER_AUTHORS = [
        ('first_author', '第一作者'),
        ('second_author', '第二作者'),
        ('both_first', '共同一作'),
        ('independent', '独立作者')
    ]

    # 专利作者类型
    PATENT_AUTHOR_TYPES = [
        ('independent', '独立作者'),
        ('first_author', '第一作者')
    ]

    # 竞赛级别
    COMPETITION_LEVELS = [
        ('A_PLUS', 'A+级'),
        ('A', 'A级'),
        ('A_MINUS', 'A-级'),
    ]

    # 竞赛等级
    COMPETITION_GRADES = [
        ('national', '国家级'),
        ('provincial', '省级')
    ]

    # 奖项等级
    AWARD_LEVELS = [
        ('first', '一等奖'),
        ('second', '二等奖'),
        ('third', '三等奖')
    ]

    # 团队角色
    TEAM_ROLES = [
        ('captain', '队长'),
        ('member_2_3', '2-3人队员'),
        ('member_4_5', '4-5人队员'),
        ('individual', '个人')
    ]

    # CCF认证排名
    CCF_RANKINGS = [
        ('A', '前0.2%'),
        ('B', '前1.5%'),
        ('C', '前3%')
    ]

    # 创新训练级别
    INNOVATION_LEVELS = [
        ('national', '国家级'),
        ('provincial', '省级'),
        ('university', '校级')
    ]

    # 创新训练角色
    INNOVATION_ROLES = [
        ('leader', '组长'),
        ('member', '组员')
    ]

    # 实习时长
    INTERNSHIP_DURATIONS = [
        ('full_year', '一学年'),
        ('less_than_year', '少于一学年')
    ]

    # 兵役时长
    MILITARY_SERVICE_DURATIONS = [
        ('1_2_years', '1-2年'),
        ('over_2_years', '2年以上')
    ]

    # 志愿服务表彰级别
    VOLUNTEER_AWARD_LEVELS = [
        ('national', '国家级'),
        ('provincial', '省级'),
        ('university', '校级')
    ]

    # 荣誉称号级别
    HONOR_TITLE_LEVELS = [
        ('national', '国家级'),
        ('provincial', '省级'),
        ('university', '校级')
    ]

    # 体育比赛级别
    SPORTS_COMPETITION_LEVELS = [
        ('international', '国际级'),
        ('national', '国家级')
    ]

    # 体育比赛名次
    SPORTS_RANKS = [
        ('champion', '冠军'),
        ('runner_up', '亚军'),
        ('third_place', '季军'),
        ('four_to_eight', '四到八名')
    ]

    # 体育比赛类型
    SPORTS_TYPES = [
        ('team', '团体'),
        ('individual', '个人')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications', verbose_name='用户')

    # 申请基本信息
    Type = models.IntegerField(
        choices=APPLICATION_TYPES,
        verbose_name='申请类型'
    )
    Title = models.CharField(max_length=200, verbose_name='申请标题', help_text='例如：论文标题、竞赛名称等')
    ApplyScore = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        verbose_name='申请分数'
    )
    Description = models.TextField(blank=True, null=True, verbose_name='详细描述')
    Attachments = models.ManyToManyField(
        Attachment,
        blank=True,
        verbose_name='附件列表'
    )

    attachments_array = models.JSONField(
        verbose_name='附件ID数组',
        default=list,
        blank=True,
        help_text='存储附件ID的字符串数组，用于快速访问'
    )

    Feedback = models.CharField(max_length=200, verbose_name='反馈')

    #额外数据包
    extra_data = models.JSONField(
        verbose_name='扩展数据',
        default=dict,  # 或 default=list
        blank=True,
        null=True
    )

    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_applications',
        verbose_name='审核老师'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='审核时间')

    # 方法1：使用整数默认值
    UploadTime = models.BigIntegerField(
        default=0,  # 初始值为0，在save方法中设置
        verbose_name='上传时间戳',
        help_text='毫秒时间戳'
    )
    ModifyTime = models.BigIntegerField(
        default=0,  # 初始值为0，在save方法中设置
        verbose_name='修改时间戳',
        help_text='毫秒时间戳'
    )

    def save(self, *args, **kwargs):
        # 如果是新对象，设置上传时间
        if not self.UploadTime or self.UploadTime == 0:
            self.UploadTime = int(time.time() * 1000)

        # 总是更新修改时间
        self.ModifyTime = int(time.time() * 1000)

        # 调用父类保存
        super().save(*args, **kwargs)

        # 🎯 关键修复：保存后立即同步附件数组（如果ManyToMany关系已建立）
        # 使用post_save信号或延迟同步，避免循环

    def sync_attachments_array(self, force=False):
        """
        同步附件ID到数组字段
        force: 是否强制保存
        """
        try:
            # 🎯 获取所有关联的附件哈希
            if hasattr(self, 'Attachments'):
                # 方法1: 使用values_list获取所有关联附件的哈希
                attachment_hashes = list(self.Attachments.all().values_list('file_hash', flat=True))

                # 方法2: 确保获取到的是列表
                if isinstance(attachment_hashes, list):
                    # 过滤掉None或空值
                    valid_hashes = [h for h in attachment_hashes if h]

                    # 去重
                    unique_hashes = list(set(valid_hashes))

                    # 按关联时间排序（如果有created_at字段）
                    try:
                        # 如果有中间表，可以按创建时间排序
                        attachments = self.Attachments.all().order_by('applicationattachment__created_at')
                        unique_hashes = [a.file_hash for a in attachments if a.file_hash]
                    except:
                        pass

                    print(f"同步附件数组: 找到 {len(unique_hashes)} 个附件")
                    print(f"附件哈希列表: {unique_hashes}")

                    # 只有在有变化时才更新
                    if unique_hashes != self.attachments_array:
                        self.attachments_array = unique_hashes
                        if force:
                            # 避免递归调用save()
                            Application.objects.filter(id=self.id).update(attachments_array=unique_hashes)
                            print(f"✅ 已更新附件数组到数据库")
                        return True
                    else:
                        print("附件数组没有变化，无需更新")
                else:
                    print(f"⚠️ 附件哈希不是列表类型: {type(attachment_hashes)}")
            else:
                print("⚠️ Application对象没有Attachments属性")

        except Exception as e:
            print(f"❌ 同步附件数组失败: {e}")
            import traceback
            print(f"错误堆栈: {traceback.format_exc()}")

        return False

    class Meta:
        db_table = 'application'
        verbose_name = '统一申请'
        verbose_name_plural = '统一申请'
        indexes = [
            models.Index(fields=['user', 'review_status']),
            models.Index(fields=['review_status', 'Type', 'UploadTime']),
        ]

    def get_review_info(self):
        """获取审核信息"""
        if self.reviewed_by and self.reviewed_at:
            return {
                "reviewer": self.reviewed_by.name,
                "reviewed_at": self.reviewed_at.timestamp(),
                "feedback": self.Feedback
            }
        return None

    # def can_be_reviewed(self):
    #     """检查申请是否可以被审核"""
    #     return self.review_status == 1  # 只有待审核状态可以审核
