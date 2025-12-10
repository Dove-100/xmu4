# create_test_data.py
import os
import django
import random
from datetime import datetime, timedelta

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xmuapp.settings')
django.setup()

from django.contrib.auth import get_user_model
from user.models import User
from score.models import AcademicPerformance
from application.models import Application, Attachment
from django.utils import timezone


def create_test_users():
    """创建测试用户"""
    print("开始创建测试用户...")

    # 创建管理员
    try:
        admin = User.objects.create_user(
            school_id='A0001',
            name='系统管理员',
            college='教务处',
            user_type=2,
            password='123456'
        )
        print(f"创建管理员: {admin.name} ({admin.school_id})")
    except:
        admin = User.objects.get(school_id='A001')
        print(f"管理员已存在: {admin.name}")

    # 创建5个老师
    teachers = []
    teacher_data = [
        {'id': 'T0001', 'name': '张教授', 'college': '信息学院'},
        {'id': 'T0002', 'name': '李副教授', 'college': '计算机学院'},
        {'id': 'T0003', 'name': '王老师', 'college': '软件学院'},
        {'id': 'T0004', 'name': '赵讲师', 'college': '网络空间安全学院'},
        {'id': 'T0005', 'name': '刘教授', 'college': '人工智能学院'}
    ]

    for teacher_info in teacher_data:
        try:
            teacher = User.objects.create_user(
                school_id=teacher_info['id'],
                name=teacher_info['name'],
                college=teacher_info['college'],
                user_type=1,
                password='123456',
                contact=f'138{random.randint(1000, 9999)}{random.randint(1000, 9999)}'
            )
            teachers.append(teacher)
            print(f"创建老师: {teacher.name} ({teacher.school_id})")
        except:
            teacher = User.objects.get(school_id=teacher_info['id'])
            teachers.append(teacher)
            print(f"老师已存在: {teacher.name}")

    # 创建10个学生
    students = []
    student_data = [
        {'id': '2024001001', 'name': '张三三', 'college': '信息学院', 'major': '计算机科学与技术', 'grade': '2024'},
        {'id': '2024001002', 'name': '李四四', 'college': '计算机学院', 'major': '软件工程', 'grade': '2024'},
        {'id': '2024001003', 'name': '王五五', 'college': '软件学院', 'major': '网络工程', 'grade': '2024'},
        {'id': '2024001004', 'name': '赵六六', 'college': '信息学院', 'major': '人工智能', 'grade': '2024'},
        {'id': '2024001005', 'name': '钱七七', 'college': '计算机学院', 'major': '数据科学', 'grade': '2024'},
        {'id': '2024001006', 'name': '孙八八', 'college': '软件学院', 'major': '信息安全', 'grade': '2024'},
        {'id': '2024001007', 'name': '周九九', 'college': '信息学院', 'major': '物联网工程', 'grade': '2024'},
        {'id': '2024001008', 'name': '吴十', 'college': '计算机学院', 'major': '计算机应用', 'grade': '2021'},
        {'id': '2024001009', 'name': '郑十一', 'college': '软件学院', 'major': '数字媒体技术', 'grade': '2021'},
        {'id': '2024001010', 'name': '王十二', 'college': '信息学院', 'major': '智能科学与技术', 'grade': '2021'}
    ]

    for student_info in student_data:
        try:
            student = User.objects.create_user(
                school_id=student_info['id'],
                name=student_info['name'],
                college=student_info['college'],
                user_type=0,
                password='123456',
                major=student_info['major'],
                grade=student_info['grade'],
                class_name=f"{student_info['major'][:2]}1班",
                contact=f'139{random.randint(1000, 9999)}{random.randint(1000, 9999)}'
            )
            students.append(student)
            print(f"创建学生: {student.name} ({student.school_id})")
        except:
            student = User.objects.get(school_id=student_info['id'])
            students.append(student)
            print(f"学生已存在: {student.name}")

    return admin, teachers, students


def create_academic_performance(students):
    """创建学业成绩"""
    print("开始创建学业成绩...")

    for student in students:
        try:
            performance, created = AcademicPerformance.objects.get_or_create(
                user=student,
                defaults={
                    'gpa': round(random.uniform(3.0, 4.0), 2),
                    'weighted_score': round(random.uniform(80, 95), 2),
                    'total_courses': random.randint(30, 50),
                    'total_credits': round(random.uniform(120, 160), 1),
                    'gpa_ranking': random.randint(1, 50),
                    'ranking_dimension': '专业内排名',
                    'failed_courses': random.randint(0, 2),
                    'cet4': random.randint(450, 650),
                    'cet6': random.randint(400, 600),
                    'applications_score': [0] * 9,
                    'academic_score': round(random.uniform(70, 80), 2),
                    'academic_expertise_score': round(random.uniform(10, 15), 2),
                    'comprehensive_performance_score': round(random.uniform(3, 5), 2),
                    'total_comprehensive_score': round(random.uniform(85, 95), 2)
                }
            )
            if created:
                print(f"创建学业成绩: {student.name}")
        except Exception as e:
            print(f"创建学业成绩失败 {student.name}: {e}")


def create_applications(students, teachers):
    """为每个学生创建10项不同的申请"""
    print("开始创建申请记录...")

    # 申请类型配置
    application_configs = {
        # 0: 学术研究成绩 - 论文
        0: {
            'titles': ['基于深度学习的图像识别研究', '人工智能在医疗诊断中的应用', '大数据分析算法优化'],
            'extra_data_options': [
                {'paper_categorie': ['A'], 'paper_author': ['first_author']},
                {'paper_categorie': ['B'], 'paper_author': ['second_author']},
                {'paper_categorie': ['C'], 'paper_author': ['both_first']},
                {'paper_categorie': ['A', 'B'], 'paper_author': ['independent', 'first_author']}
            ]
        },
        # 1: 学术研究成绩 - 专利
        1: {
            'titles': ['一种新型人工智能算法专利', '计算机软件著作权', '实用新型专利'],
            'extra_data_options': [
                {'patent_aothor_type': ['independent']},
                {'patent_aothor_type': ['first_author']},
                {'patent_aothor_type': ['independent', 'first_author']}
            ]
        },
        # 2: 学术竞赛成绩 - 竞赛
        2: {
            'titles': ['全国大学生程序设计竞赛', '数学建模大赛', '机器人设计大赛'],
            'extra_data_options': [
                {'competition_level': ['A_PLUS'], 'competition_grade': ['national'], 'award_level': ['first'],
                 'team_role': ['captain']},
                {'competition_level': ['A'], 'competition_grade': ['national'], 'award_level': ['second'],
                 'team_role': ['member_2_3']},
                {'competition_level': ['A_MINUS'], 'competition_grade': ['provincial'], 'award_level': ['first'],
                 'team_role': ['member_4_5']},
                {'competition_level': ['A'], 'competition_grade': ['provincial'], 'award_level': ['second'],
                 'team_role': ['individual']}
            ]
        },
        # 3: 学术竞赛成绩 - CCF认证
        3: {
            'titles': ['CCF认证程序设计竞赛', 'CCF大学生计算机系统与程序设计竞赛'],
            'extra_data_options': [
                {'ccf_ranking': ['A']},
                {'ccf_ranking': ['B']},
                {'ccf_ranking': ['C']}
            ]
        },
        # 4: 创新训练成绩
        4: {
            'titles': ['大学生创新创业训练计划', '科研训练项目', '创新实验项目'],
            'extra_data_options': [
                {'innovation_level': ['national'], 'innovation_role': ['leader']},
                {'innovation_level': ['national'], 'innovation_role': ['member']},
                {'innovation_level': ['provincial'], 'innovation_role': ['leader']},
                {'innovation_level': ['university'], 'innovation_role': ['member']}
            ]
        },
        # 5: 国际实习成绩
        5: {
            'titles': ['微软亚洲研究院实习', '谷歌暑期实习', '海外高校科研实习'],
            'extra_data_options': [
                {'internship_duration': ['full_year'], 'score': [8.0]},
                {'internship_duration': ['less_than_year'], 'score': [5.0]},
                {'internship_duration': ['full_year'], 'score': [7.5]}
            ]
        },
        # 6: 参军入伍成绩
        6: {
            'titles': ['义务兵役服务', '军校学员经历'],
            'extra_data_options': [
                {'military_service_duration': ['1_2_years'], 'score': [10.0]},
                {'military_service_duration': ['over_2_years'], 'score': [15.0]},
                {'military_service_duration': ['1_2_years'], 'score': [12.0]}
            ]
        },
        # 7: 志愿服务成绩
        7: {
            'titles': ['社区志愿服务', '支教活动', '大型活动志愿者'],
            'extra_data_options': [
                {'volunteer_time': [120], 'score': [5.0]},
                {'volunteer_award_level': ['national'], 'role': ['leader'], 'score': [8.0]},
                {'volunteer_award_level': ['provincial'], 'role': ['member'], 'score': [6.0]},
                {'volunteer_award_level': ['university'], 'role': ['individual'], 'score': [4.0]}
            ]
        },
        # 8: 荣誉称号成绩
        8: {
            'titles': ['三好学生', '优秀学生干部', '国家奖学金'],
            'extra_data_options': [
                {'honor_title_level': ['national'], 'score': [10.0]},
                {'honor_title_level': ['provincial'], 'score': [8.0]},
                {'honor_title_level': ['university'], 'score': [6.0]},
                {'honor_title_level': ['national', 'provincial'], 'score': [12.0]}
            ]
        },
        # 9: 体育比赛成绩
        9: {
            'titles': ['全国大学生运动会', '省级体育竞赛', '校运会比赛'],
            'extra_data_options': [
                {'sport_competition_level': ['international'], 'sport_rank': ['first'], 'sport_type': ['individual']},
                {'sport_competition_level': ['national'], 'sport_rank': ['second'], 'sport_type': ['team']},
                {'sport_competition_level': ['national'], 'sport_rank': ['third'], 'sport_type': ['individual']},
                {'sport_competition_level': ['national'], 'sport_rank': ['rank4_8'], 'sport_type': ['team']}
            ]
        },
        # 10: 社会工作成绩
        10: {
            'titles': ['学生会主席', '班级班长', '社团负责人'],
            'extra_data_options': [
                {'social_title': ['学生会主席'], 'score': [8.0]},
                {'social_title': ['班级班长'], 'score': [6.0]},
                {'social_title': ['社团部长'], 'score': [5.0]},
                {'social_title': ['团支部书记'], 'score': [7.0]}
            ]
        }
    }

    # 为每个学生创建申请
    for student in students:
        application_count = 0
        used_types = set()

        while application_count < 10 and len(used_types) < len(application_configs):
            # 随机选择申请类型（确保不重复）
            app_type = random.choice(list(application_configs.keys()))
            if app_type in used_types:
                continue

            used_types.add(app_type)
            config = application_configs[app_type]

            # 随机选择配置
            title = random.choice(config['titles'])
            extra_data = random.choice(config['extra_data_options'])

            # 随机审核状态和分数
            review_status = random.choice([0, 1, 2, 3])  # 草稿、待审核、通过、不通过
            apply_score = round(random.uniform(5.0, 15.0), 2)
            real_score = apply_score if review_status == 2 else 0  # 只有审核通过才有实际加分

            # 随机选择审核老师（如果是已审核状态）
            reviewed_by = None
            reviewed_at = None
            if review_status in [2, 3]:  # 审核通过或不通过
                reviewed_by = random.choice(teachers)
                reviewed_at = timezone.now() - timedelta(days=random.randint(1, 30))

            try:
                application = Application.objects.create(
                    user=student,
                    Type=app_type,
                    Title=title,
                    ApplyScore=apply_score,
                    Description=f"这是{student.name}同学的{title}申请，详细描述申请内容。",
                    Feedback="审核意见：符合加分标准" if review_status == 2 else "审核意见：不符合加分标准" if review_status == 3 else "",
                    extra_data=extra_data,
                    review_status=review_status,
                    Real_Score=real_score,
                    reviewed_by=reviewed_by,
                    reviewed_at=reviewed_at
                )
                application_count += 1
                print(f"为 {student.name} 创建申请: {title} (类型: {app_type})")
            except Exception as e:
                print(f"创建申请失败 {student.name} - {title}: {e}")

        print(f"完成 {student.name} 的申请创建，共 {application_count} 项")


def main():
    """主函数"""
    print("开始创建测试数据...")

    try:
        # 创建用户
        admin, teachers, students = create_test_users()

        # 创建学业成绩
        create_academic_performance(students)

        # 创建申请记录
        create_applications(students, teachers)

        print("\n" + "=" * 50)
        print("测试数据创建完成！")
        print("=" * 50)
        print(f"管理员: 1个 (A001/123456)")
        print(f"老师: 5个 (T001-T005/123456)")
        print(f"学生: 10个 (2021001001-2021001010/123456)")
        print(f"每个学生: 10项不同的申请")
        print("\n登录信息:")
        print("管理员: A001 / 123456")
        print("老师: T001 / 123456")
        print("学生: 2021001001 / 123456")

    except Exception as e:
        print(f"创建测试数据时发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()