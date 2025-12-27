# services/score_calculation.py
import decimal
from django.db import transaction
from django.db.models import F, Func, Count
from score.models import AcademicPerformance


class ScoreCalculationService:
    """分数计算与排名服务"""

    @staticmethod
    def batch_calculate_academic_scores():
        """批量计算所有学生的学术分数"""
        try:
            # 使用批量更新提高性能
            from django.db.models import Case, When, Value, DecimalField

            print("=== 开始批量计算学术分数 ===")

            # 方法1：使用annotate和update（推荐）
            updated_count = AcademicPerformance.objects.annotate(
                calculated_score=Case(
                    When(gpa__isnull=False,
                         then=F('gpa') / decimal.Decimal('4.0') * decimal.Decimal('80.0')),
                    default=Value(0),
                    output_field=DecimalField(max_digits=5, decimal_places=2)
                )
            ).update(academic_score=F('calculated_score'))

            print(f"✅ 成功更新 {updated_count} 条学术分数记录")
            return updated_count

        except Exception as e:
            print(f"❌ 批量计算失败: {e}")
            import traceback
            traceback.print_exc()
            return 0

    @staticmethod
    def batch_calculate_total_scores():
        """批量计算所有学生的综合总分"""
        try:
            print("=== 开始批量计算综合总分 ===")

            # 确保academic_score已计算
            ScoreCalculationService.batch_calculate_academic_scores()

            # 计算综合总分
            updated_count = AcademicPerformance.objects.update(
                total_comprehensive_score=(
                        F('academic_score') +
                        F('academic_expertise_score') +
                        F('comprehensive_performance_score')
                )
            )

            print(f"✅ 成功更新 {updated_count} 条综合总分记录")
            return updated_count

        except Exception as e:
            print(f"❌ 综合总分计算失败: {e}")
            import traceback
            traceback.print_exc()
            return 0

    @staticmethod
    def batch_update_rankings(dimension='专业'):
        """批量更新指定维度的排名

        Args:
            dimension: 排名维度 ('专业', '学院', '全校')
        """
        try:
            print(f"=== 开始批量更新 {dimension} 排名 ===")

            # 根据维度分组计算排名
            from django.db.models import Window
            from django.db.models.functions import Rank, DenseRank

            # 构建查询集
            queryset = AcademicPerformance.objects.filter(
                total_comprehensive_score__isnull=False
            )

            # 添加维度过滤
            if dimension == '专业':
                queryset = queryset.order_by('user__college', 'user__major', '-total_comprehensive_score')
            elif dimension == '学院':
                queryset = queryset.order_by('user__college', '-total_comprehensive_score')
            elif dimension == '全校':
                queryset = queryset.order_by('-total_comprehensive_score')

            # 使用窗口函数计算排名（Django 2.0+）
            # 注意：这需要数据库支持窗口函数（PostgreSQL, MySQL 8.0+）
            ranked_queryset = queryset.annotate(
                rank=Window(
                    expression=DenseRank(),
                    order_by=F('total_comprehensive_score').desc(),
                    partition_by=[]  # 根据维度添加partition
                ),
                total_in_group=Window(
                    expression=Count('id'),
                    partition_by=[]  # 根据维度添加partition
                )
            )

            # 批量更新（这里简化处理，实际可能需要循环）
            updated_count = 0
            for record in ranked_queryset:
                record.current_rank = record.rank
                record.ranking_dimension = dimension
                record.total_students_in_dimension = record.total_in_group
                record.save()
                updated_count += 1

            print(f"✅ 成功更新 {updated_count} 条排名记录（维度: {dimension}）")
            return updated_count

        except Exception as e:
            print(f"❌ 排名更新失败: {e}")
            # 回退到传统排名算法
            return ScoreCalculationService.traditional_ranking_update(dimension)

    @staticmethod
    def traditional_ranking_update(dimension='专业'):
        """传统排名算法（兼容所有数据库）"""
        from collections import defaultdict
        from django.db import transaction

        try:
            with transaction.atomic():
                # 获取所有需要排名的学生
                performances = AcademicPerformance.objects.filter(
                    total_comprehensive_score__isnull=False
                ).select_related('user')

                # 按维度分组
                groups = defaultdict(list)

                for perf in performances:
                    if dimension == '专业':
                        key = f"{perf.user.college}_{perf.user.major}"
                    elif dimension == '学院':
                        key = perf.user.college
                    elif dimension == '全校':
                        key = "all"
                    else:
                        key = "unknown"

                    groups[key].append(perf)

                # 对每个组进行排名
                total_updated = 0
                for group_key, group_performances in groups.items():
                    # 按分数降序排序
                    sorted_performances = sorted(
                        group_performances,
                        key=lambda x: x.total_comprehensive_score,
                        reverse=True
                    )

                    # 处理并列排名
                    current_rank = 1
                    previous_score = None
                    same_score_count = 0

                    for idx, perf in enumerate(sorted_performances, start=1):
                        current_score = perf.total_comprehensive_score

                        if previous_score is None:
                            # 第一个学生
                            rank = 1
                        elif current_score == previous_score:
                            # 分数相同，排名不变
                            rank = current_rank
                            same_score_count += 1
                        else:
                            # 分数不同，更新排名
                            rank = idx
                            current_rank = rank

                        # 更新记录
                        perf.current_rank = rank
                        perf.ranking_dimension = dimension
                        perf.total_students_in_dimension = len(sorted_performances)
                        perf.save()

                        previous_score = current_score
                        total_updated += 1

                print(f"✅ 传统算法更新 {total_updated} 条排名记录（维度: {dimension}）")
                return total_updated

        except Exception as e:
            print(f"❌ 传统排名算法失败: {e}")
            import traceback
            traceback.print_exc()
            return 0