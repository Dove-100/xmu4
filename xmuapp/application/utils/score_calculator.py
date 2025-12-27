from django.db import transaction
from decimal import Decimal
from score.models import AcademicPerformance


def update_academic_performance_score(self, application, original_score):
    """
    更新学生学业成绩中的申请项目分数
    """
    try:
        from score.models import AcademicPerformance
        from decimal import Decimal

        student = application.user
        application_type = getattr(application, 'Type', getattr(application, 'application_type', None))

        if application_type is None:
            return False

        try:
            academic_perf = AcademicPerformance.objects.get(user=student)
        except AcademicPerformance.DoesNotExist:
            return False

        score_list = list(academic_perf.applications_score)

        while len(score_list) <= application_type:
            score_list.append(0.0)

        current_type_score = float(score_list[application_type]) if isinstance(score_list[application_type],
                                                                               (int, float, Decimal)) else 0.0
        original_app_score = float(original_score)
        new_score = max(0.0, current_type_score - original_app_score)
        score_list[application_type] = new_score

        processed_score_list = []
        for score in score_list:
            if isinstance(score, Decimal):
                processed_score_list.append(float(score))
            elif isinstance(score, (int, float)):
                processed_score_list.append(score)
            else:
                try:
                    processed_score_list.append(float(score))
                except:
                    processed_score_list.append(0.0)

        academic_perf.applications_score = processed_score_list
        self.recalculate_total_scores(academic_perf)
        academic_perf.save()

        return True

    except Exception as e:
        return False


def recalculate_total_scores(self, academic_perf):
    """
    重新计算学业专长成绩和总分
    """
    try:
        from decimal import Decimal

        if not isinstance(academic_perf.applications_score, list):
            academic_perf.applications_score = [0.0] * 9

        score_list = []
        for item in academic_perf.applications_score:
            if isinstance(item, Decimal):
                score_list.append(float(item))
            elif isinstance(item, (int, float)):
                score_list.append(item)
            else:
                try:
                    score_list.append(float(item))
                except:
                    score_list.append(0.0)

        while len(score_list) < 9:
            score_list.append(0.0)

        academic_expertise_scores = []
        for i in range(4):
            score = score_list[i]
            academic_expertise_scores.append(min(score, 5.0))

        academic_expertise_total = sum(academic_expertise_scores)
        academic_perf.academic_expertise_score = Decimal(str(min(academic_expertise_total, 15.0)))

        comprehensive_scores = []
        for i in range(4, 9):
            score = score_list[i]
            comprehensive_scores.append(min(score, 1.0))

        comprehensive_total = sum(comprehensive_scores)
        academic_perf.comprehensive_performance_score = Decimal(str(min(comprehensive_total, 5.0)))

        academic_score = float(getattr(academic_perf, 'academic_score', 0.0))
        total_score = (
                Decimal(str(academic_score)) +
                academic_perf.academic_expertise_score +
                academic_perf.comprehensive_performance_score
        )

        academic_perf.total_comprehensive_score = Decimal(str(min(float(total_score), 100.0)))

    except Exception as e:
        raise