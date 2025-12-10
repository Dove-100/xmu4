# score/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class StudentScoreSerializer(serializers.ModelSerializer):
    # 基础信息字段
    id = serializers.CharField(read_only=True)
    school_id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    college = serializers.CharField(read_only=True)
    major = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(source='date_joined', format='%Y-%m-%d %H:%M:%S', read_only=True)

    # 学业成绩字段 - 从AcademicPerformance关联模型获取
    gpa = serializers.SerializerMethodField()
    weighted_score = serializers.SerializerMethodField()
    total_courses = serializers.SerializerMethodField()
    total_credits = serializers.SerializerMethodField()
    gpa_ranking = serializers.SerializerMethodField()
    ranking_dimension = serializers.SerializerMethodField()
    failed_courses = serializers.SerializerMethodField()
    academic_score = serializers.SerializerMethodField()
    academic_expertise_score = serializers.SerializerMethodField()
    comprehensive_performance_score = serializers.SerializerMethodField()
    total_comprehensive_score = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()

    # 英语成绩字段
    cet4 = serializers.SerializerMethodField()
    cet6 = serializers.SerializerMethodField()

    # 各类申请分数数组
    applications_score = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'school_id', 'name', 'gpa', 'college', 'major',
            'weighted_score', 'total_courses', 'total_credits',
            'gpa_ranking', 'ranking_dimension', 'failed_courses',
            'academic_score', 'academic_expertise_score',
            'comprehensive_performance_score', 'total_comprehensive_score',
            'created_at', 'updated_at', 'cet4', 'cet6', 'applications_score'
        ]

    def _get_academic_performance(self, obj):
        """获取关联的学业成绩对象 - 修复字段名"""
        # 使用 academic_performance 而不是 academicperformance
        if hasattr(obj, 'academic_performance'):
            return obj.academic_performance
        return None

    def get_gpa(self, obj):
        academic_perf = self._get_academic_performance(obj)
        return getattr(academic_perf, 'gpa', 0.0) if academic_perf else 0.0

    def get_weighted_score(self, obj):
        academic_perf = self._get_academic_performance(obj)
        return getattr(academic_perf, 'weighted_score', 0.0) if academic_perf else 0.0

    def get_total_courses(self, obj):
        academic_perf = self._get_academic_performance(obj)
        return getattr(academic_perf, 'total_courses', 0) if academic_perf else 0

    def get_total_credits(self, obj):
        academic_perf = self._get_academic_performance(obj)
        return getattr(academic_perf, 'total_credits', 0.0) if academic_perf else 0.0

    def get_gpa_ranking(self, obj):
        academic_perf = self._get_academic_performance(obj)
        return getattr(academic_perf, 'gpa_ranking', 0) if academic_perf else 0

    def get_ranking_dimension(self, obj):
        academic_perf = self._get_academic_performance(obj)
        return getattr(academic_perf, 'ranking_dimension', '') if academic_perf else ''

    def get_failed_courses(self, obj):
        academic_perf = self._get_academic_performance(obj)
        return getattr(academic_perf, 'failed_courses', 0) if academic_perf else 0

    def get_academic_score(self, obj):
        academic_perf = self._get_academic_performance(obj)
        return getattr(academic_perf, 'academic_score', 0.0) if academic_perf else 0.0

    def get_academic_expertise_score(self, obj):
        academic_perf = self._get_academic_performance(obj)
        return getattr(academic_perf, 'academic_expertise_score', 0.0) if academic_perf else 0.0

    def get_comprehensive_performance_score(self, obj):
        academic_perf = self._get_academic_performance(obj)
        return getattr(academic_perf, 'comprehensive_performance_score', 0.0) if academic_perf else 0.0

    def get_total_comprehensive_score(self, obj):
        academic_perf = self._get_academic_performance(obj)
        return getattr(academic_perf, 'total_comprehensive_score', 0.0) if academic_perf else 0.0

    def get_updated_at(self, obj):
        academic_perf = self._get_academic_performance(obj)
        if academic_perf and hasattr(academic_perf, 'updated_at'):
            return academic_perf.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        return obj.date_joined.strftime('%Y-%m-%d %H:%M:%S')

    def get_cet4(self, obj):
        """获取四级成绩"""
        academic_perf = self._get_academic_performance(obj)
        if academic_perf:
            return getattr(academic_perf, 'cet4', -1)
        return -1

    def get_cet6(self, obj):
        """获取六级成绩"""
        academic_perf = self._get_academic_performance(obj)
        if academic_perf:
            return getattr(academic_perf, 'cet6', -1)
        return -1

    def get_applications_score(self, obj):
        """获取9类申请分数数组"""
        academic_perf = self._get_academic_performance(obj)
        if not academic_perf:
            return [0] * 9

        # 使用原有模型的get_score方法获取各类申请分数
        scores = []
        for score_type in range(9):  # 0-8 共9类申请
            try:
                score = academic_perf.get_score(score_type)
                scores.append(score)
            except (AttributeError, ValueError):
                scores.append(0.0)

        return scores