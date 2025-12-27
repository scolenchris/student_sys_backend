from flask import Blueprint, request, jsonify
from app.models import (
    db,
    Teacher,
    CourseAssignment,
    ClassInfo,
    Subject,
    Student,
    Score,
    ExamTask,
)

teacher_bp = Blueprint("teacher", __name__)


# --- 1. 获取当前老师的任教课程 ---
@teacher_bp.route("/my_courses/<int:user_id>", methods=["GET"])
def get_my_courses(user_id):
    # 找到该用户的教师档案
    teacher = Teacher.query.filter_by(user_id=user_id).first()
    if not teacher:
        return jsonify([]), 200  # 如果没找到教师档案，返回空列表

    # 查询关联的班级和科目
    # assignments = db.session.query(CourseAssignment, ClassInfo, Subject).join(
    #     ClassInfo, CourseAssignment.class_id == ClassInfo.id
    # ).join(
    #     Subject, CourseAssignment.subject_id == Subject.id
    # ).filter(CourseAssignment.teacher_id == teacher.id).all()
    assignments = (
        db.session.query(
            CourseAssignment.id,
            ClassInfo.id.label("class_id"),
            ClassInfo.entry_year,
            ClassInfo.class_num,
            Subject.id.label("subject_id"),
            Subject.name.label("subject_name"),
        )
        .join(ClassInfo, CourseAssignment.class_id == ClassInfo.id)
        .join(Subject, CourseAssignment.subject_id == Subject.id)
        .filter(CourseAssignment.teacher_id == teacher.id)
        .all()
    )

    # return jsonify([{
    #     "assignment_id": a.CourseAssignment.id,
    #     "class_id": a.ClassInfo.id,
    #     "grade_class": f"{a.ClassInfo.grade_display}({a.ClassInfo.class_num})班",
    #     "subject_name": a.Subject.name,
    #     "subject_id": a.Subject.id
    # } for a in assignments])
    return jsonify(
        [
            {
                "assignment_id": a.id,
                "class_id": a.class_id,
                "grade_class": f"{a.entry_year}级({a.class_num})班",
                "subject_name": a.subject_name,
                "subject_id": a.subject_id,
            }
            for a in assignments
        ]
    )


# --- 2. 获取打分列表（学生名单 + 现有分数） ---
@teacher_bp.route("/score_list", methods=["GET"])
def get_score_list():
    class_id = request.args.get("class_id")
    # subject_id = request.args.get('subject_id') # 现在主要靠 task 确定科目，但保留校验也可以
    exam_task_id = request.args.get("exam_task_id")  # 核心参数

    if not exam_task_id:
        return jsonify([])

    # 修正之前的bug：状态使用中文 '在读'
    students = Student.query.filter_by(class_id=class_id, status="在读").all()

    result = []
    for s in students:
        score_record = Score.query.filter_by(
            student_id=s.id, exam_task_id=exam_task_id
        ).first()

        result.append(
            {
                "student_id": s.id,
                "student_no": s.student_id,
                "name": s.name,
                "score": score_record.score if score_record else None,
            }
        )

    return jsonify(result)


# --- 3. 保存成绩 ---
@teacher_bp.route("/save_scores", methods=["POST"])
def save_scores():
    data = request.get_json()
    exam_task_id = data.get("exam_task_id")
    subject_id = data.get("subject_id")  # 冗余字段，可用于校验
    scores_data = data.get("scores")  # [{"student_id": 1, "score": 95}, ...]

    task = ExamTask.query.get(exam_task_id)
    if not task:
        return jsonify({"msg": "考试任务不存在"}), 404

    if not task.is_active:
        return jsonify({"msg": "该考试录入通道已关闭，无法保存"}), 403

    for item in scores_data:
        existing_score = Score.query.filter_by(
            student_id=item["student_id"], exam_task_id=exam_task_id
        ).first()

        if existing_score:
            existing_score.score = item["score"]
        else:
            new_score = Score(
                student_id=item["student_id"],
                subject_id=task.subject_id,  # 从任务中获取科目ID更安全
                exam_task_id=exam_task_id,
                score=item["score"],
                term=task.name,  # 兼容旧字段，存考试名
            )
            db.session.add(new_score)

    db.session.commit()
    return jsonify({"msg": "成绩保存成功"})


# --- 获取某班级某科目可用的考试任务 ---
@teacher_bp.route("/available_exams", methods=["GET"])
def get_available_exams():
    class_id = request.args.get("class_id", type=int)
    subject_id = request.args.get("subject_id", type=int)

    if not class_id or not subject_id:
        return jsonify([])

    # 1. 找到该班级的入学年份 (entry_year)
    cls = ClassInfo.query.get(class_id)
    if not cls:
        return jsonify([])

    # 2. 查询该年级、该科目下所有已发布的考试
    # 教师端通常只关心 is_active=True 的，或者全部显示但锁住禁录的
    tasks = (
        ExamTask.query.filter_by(entry_year=cls.entry_year, subject_id=subject_id)
        .order_by(ExamTask.create_time.desc())
        .all()
    )

    return jsonify(
        [
            {
                "id": t.id,
                "name": t.name,
                "full_score": t.full_score,
                "is_active": t.is_active,
            }
            for t in tasks
        ]
    )
