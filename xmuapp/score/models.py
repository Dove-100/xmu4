import decimal
import uuid

from django.db import models

from user.models import User
from django.db.models import F, Window
from django.db.models.functions import Rank

class AcademicPerformance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='academic_performance',
                                verbose_name='用户')

    # 基础学业信息
    gpa = models.DecimalField(default=0.0, max_digits=7, decimal_places=4, verbose_name='学分绩点')
    weighted_score = models.DecimalField(default=0.0, max_digits=7, decimal_places=4, verbose_name='加权分数')
    total_courses = models.IntegerField(default=0, verbose_name='总课程门数')
    total_credits = models.DecimalField(default=0.0, max_digits=7, decimal_places=4, verbose_name='总学分数')
    gpa_ranking = models.IntegerField(default=0, verbose_name='绩点排名')
    ranking_dimension = models.CharField(max_length=100, default='专业内排名', verbose_name='排名维度')  # 如：专业排名、年级排名等
    failed_courses = models.IntegerField(default=0, verbose_name='不及格门数')
    current_rank = models.IntegerField(null=True, blank=True)
    total_students_in_dimension = models.IntegerField(null=True, blank=True)

    # 各项成绩
    cet4 = models.IntegerField(default=-1, verbose_name='大学英语四级')
    cet6 = models.IntegerField(default=-1, verbose_name='大学英语六级')
    applications_score = models.JSONField(verbose_name='各类申请加分', default=list)

    # 定义成绩索引和名称的映射
    SCORE_TYPES = {
        0: 'academic_competitions',  # 学术竞赛成绩
        1: 'innovation_projects',  # 创新训练成绩
        2: 'academic_study',  # 学术研究成绩
        3: 'honorary_titles',  # 荣誉称号成绩
        4: 'social_works',  # 社会工作成绩
        5: 'volunteer_services',  # 志愿服务成绩
        6: 'international_internships',  # 国际实习成绩
        7: 'military_services',  # 参军入伍成绩
        8: 'sports_competitions',  # 体育项目成绩
    }

    academic_score = models.DecimalField(max_digits=7, decimal_places=4, verbose_name='学业成绩(满分80分)', default=0)
    academic_expertise_score = models.DecimalField(max_digits=7, decimal_places=4,
                                                   verbose_name='学术专长成绩(满分15分)', default=0)
    comprehensive_performance_score = models.DecimalField(max_digits=7, decimal_places=4,
                                                          verbose_name='综合表现成绩(满分5分)', default=0)
    total_comprehensive_score = models.DecimalField(max_digits=7, decimal_places=4, verbose_name='综合成绩(满分100分)',
                                                    default=0)

    # 时间戳
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'academic_performance'
        verbose_name = '学业成绩'
        verbose_name_plural = '学业成绩'

    def __str__(self):
        return f"{self.user.name}的学业成绩"

    # 反向映射：名称->索引
    SCORE_INDEX = {v: k for k, v in SCORE_TYPES.items()}

    def get_score(self, score_type):
        """获取指定类型的成绩"""
        if isinstance(score_type, str):
            index = self.SCORE_INDEX.get(score_type)
        else:
            index = score_type

        if index is not None and len(self.applications_score) > index:
            return self.applications_score[index]
        return 0

    def set_score(self, score_type, value):
        """设置指定类型的成绩"""
        if isinstance(score_type, str):
            index = self.SCORE_INDEX.get(score_type)
        else:
            index = score_type

        if index is not None:
            # 确保数组足够长
            while len(self.applications_score) <= index:
                self.applications_score.append(0)
            self.applications_score[index] = float(value)

    def calculate_academic_score(self):
        """计算学术分数：GPA / 4 × 80"""
        if self.gpa is None:
            return decimal.Decimal('0.00')

        try:
            # 确保gpa是Decimal类型
            gpa_decimal = decimal.Decimal(str(self.gpa))
            academic_score = (gpa_decimal / decimal.Decimal('4.0')) * decimal.Decimal('80.0')
            # 保留两位小数
            academic_score = academic_score.quantize(decimal.Decimal('0.00'))

            # 更新字段
            self.academic_score = academic_score
            return academic_score
        except (ValueError, decimal.InvalidOperation) as e:
            print(f"❌ GPA计算错误: {e}, GPA值: {self.gpa}")
            return decimal.Decimal('0.00')

    def calculate_total_comprehensive_score(self):
        """计算综合总分"""
        # 确保academic_score已计算
        if self.academic_score is None:
            self.calculate_academic_score()

        # 获取其他分数（默认为0）
        academic_expertise = self.academic_expertise_score or decimal.Decimal('0.00')
        comprehensive_performance = self.comprehensive_performance_score or decimal.Decimal('0.00')

        # 计算总分
        total_score = (
                self.academic_score +
                academic_expertise +
                comprehensive_performance
        )

        # 保留两位小数
        total_score = total_score.quantize(decimal.Decimal('0.00'))

        # 更新字段
        self.total_comprehensive_score = total_score
        return total_score

    def update_ranking(self, dimension='专业'):
        """更新指定维度的排名

        Args:
            dimension: 排名维度 ('专业', '学院', '全校')
        """
        from django.db.models import Count

        # 确定筛选条件
        user = self.user
        filter_kwargs = {}

        if dimension == '专业':
            filter_kwargs = {
                'user__major': user.major,
                'user__college': user.college
            }
        elif dimension == '学院':
            filter_kwargs = {'user__college': user.college}
        elif dimension == '全校':
            filter_kwargs = {}

        # 获取该维度所有学生的成绩记录
        queryset = AcademicPerformance.objects.filter(
            **filter_kwargs,
            total_comprehensive_score__isnull=False
        ).order_by('-total_comprehensive_score')

        # 计算排名（并列排名处理）
        current_score = self.total_comprehensive_score
        rank = 1
        same_score_count = 0

        for idx, record in enumerate(queryset, start=1):
            if idx == 1:
                previous_score = record.total_comprehensive_score

            if record.total_comprehensive_score == current_score:
                same_score_count += 1
                if record.id == self.id:
                    # 找到当前学生
                    break
            elif record.total_comprehensive_score < current_score:
                # 如果当前学生分数更高，应该已经找到了
                pass

        # 更新排名信息
        self.current_rank = rank
        self.ranking_dimension = dimension
        self.total_students_in_dimension = queryset.count()

        return {
            'rank': rank,
            'total': queryset.count(),
            'dimension': dimension
        }

    def save(self, *args, **kwargs):
        """重写save方法，自动计算分数"""
        # 计算学术分数
        self.calculate_academic_score()

        # 计算综合总分
        self.calculate_total_comprehensive_score()

        # 调用父类保存
        super().save(*args, **kwargs)