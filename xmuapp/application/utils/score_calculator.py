from django.db import transaction
from decimal import Decimal
from score.models import AcademicPerformance


def update_academic_performance_score(application):
    """
    更新学生学业成绩中的申请项目分数
    """
    try:
        with transaction.atomic():
            # 获取学生和学业成绩记录
            student = application.user
            academic_perf, created = AcademicPerformance.objects.get_or_create(
                user=student
            )

            # 获取申请类型和实际得分
            application_type = application.Type
            real_score = getattr(application, 'RealScore', getattr(application, 'Real_Score', 0))

            print(f"更新学业成绩: 学生={student.name}, 申请类型={application_type}, 得分={real_score}")

            # 根据申请类型更新对应的成绩字段
            if application_type in AcademicPerformance.SCORE_TYPES:
                score_type_name = AcademicPerformance.SCORE_TYPES[application_type]
                academic_perf.set_score(application_type, real_score)

                print(f"设置 {score_type_name}[{application_type}] = {real_score}")

                # 重新计算总分
                recalculate_total_scores(academic_perf)

                academic_perf.save()
                print(f"学业成绩更新完成")
            else:
                print(f"未知的申请类型: {application_type}")

    except Exception as e:
        print(f"更新学业成绩失败: {str(e)}")
        raise


def recalculate_total_scores(academic_perf):
    """
    重新计算学业专长成绩和总分
    """
    try:
        # 计算学术专长成绩（前4项，满分15分）
        academic_expertise_scores = []
        for i in range(4):  # 0-3: 学术竞赛、创新训练、学术研究、荣誉称号
            if i < len(academic_perf.applications_score):
                score = academic_perf.applications_score[i]
                academic_expertise_scores.append(min(float(score), 5.0))  # 每项最高5分

        academic_expertise_total = sum(academic_expertise_scores)
        academic_perf.academic_expertise_score = Decimal(str(min(academic_expertise_total, 15.0)))  # 满分15分

        # 计算综合表现成绩（后5项，满分5分）
        comprehensive_scores = []
        for i in range(4, 9):  # 4-8: 社会工作、志愿服务、国际实习、参军入伍、体育项目
            if i < len(academic_perf.applications_score):
                score = academic_perf.applications_score[i]
                comprehensive_scores.append(min(float(score), 1.0))  # 每项最高1分

        comprehensive_total = sum(comprehensive_scores)
        academic_perf.comprehensive_performance_score = Decimal(str(min(comprehensive_total, 5.0)))  # 满分5分

        # 计算总分（学业成绩 + 学术专长 + 综合表现）
        total_score = (
                academic_perf.academic_score +
                academic_perf.academic_expertise_score +
                academic_perf.comprehensive_performance_score
        )
        academic_perf.total_comprehensive_score = Decimal(str(min(total_score, 100.0)))  # 满分100分

        print(f"重新计算总分: 学业={academic_perf.academic_score}, "
              f"学术专长={academic_perf.academic_expertise_score}, "
              f"综合表现={academic_perf.comprehensive_performance_score}, "
              f"总分={academic_perf.total_comprehensive_score}")

    except Exception as e:
        print(f"重新计算总分失败: {str(e)}")
        raise