from flask import Blueprint, request, jsonify
from app.models import db, Teacher, CourseAssignment, ClassInfo, Subject, Student, Score

teacher_bp = Blueprint('teacher', __name__)

# --- 1. 获取当前老师的任教课程 ---
@teacher_bp.route('/my_courses/<int:user_id>', methods=['GET'])
def get_my_courses(user_id):
    # 找到该用户的教师档案
    teacher = Teacher.query.filter_by(user_id=user_id).first()
    if not teacher:
        return jsonify([]), 200 # 如果没找到教师档案，返回空列表
    
    # 查询关联的班级和科目
    # assignments = db.session.query(CourseAssignment, ClassInfo, Subject).join(
    #     ClassInfo, CourseAssignment.class_id == ClassInfo.id
    # ).join(
    #     Subject, CourseAssignment.subject_id == Subject.id
    # ).filter(CourseAssignment.teacher_id == teacher.id).all()
    assignments = db.session.query(
        CourseAssignment.id,
        ClassInfo.id.label('class_id'),
        ClassInfo.entry_year,
        ClassInfo.class_num,
        Subject.id.label('subject_id'),
        Subject.name.label('subject_name')
    ).join(ClassInfo, CourseAssignment.class_id == ClassInfo.id)\
     .join(Subject, CourseAssignment.subject_id == Subject.id)\
     .filter(CourseAssignment.teacher_id == teacher.id).all()

    # return jsonify([{
    #     "assignment_id": a.CourseAssignment.id,
    #     "class_id": a.ClassInfo.id,
    #     "grade_class": f"{a.ClassInfo.grade_display}({a.ClassInfo.class_num})班",
    #     "subject_name": a.Subject.name,
    #     "subject_id": a.Subject.id
    # } for a in assignments])
    return jsonify([{
        "assignment_id": a.id,
        "class_id": a.class_id,
        "grade_class": f"{a.entry_year}级({a.class_num})班",
        "subject_name": a.subject_name,
        "subject_id": a.subject_id
    } for a in assignments])

# --- 2. 获取打分列表（学生名单 + 现有分数） ---
@teacher_bp.route('/score_list', methods=['GET'])
def get_score_list():
    class_id = request.args.get('class_id')
    subject_id = request.args.get('subject_id')
    term = request.args.get('term', "2024-2025-1") # 默认当前学期

    # 获取该班级所有在读学生
    students = Student.query.filter_by(class_id=class_id, status='active').all()
    
    result = []
    for s in students:
        # 查找该生该科目在该学期的成绩
        score_record = Score.query.filter_by(
            student_id=s.id, 
            subject_id=subject_id, 
            term=term
        ).first()
        
        result.append({
            "student_id": s.id,
            "student_no": s.student_id,
            "name": s.name,
            "score": score_record.score if score_record else None
        })
    
    return jsonify(result)

# --- 3. 批量提交/修改成绩 ---
@teacher_bp.route('/save_scores', methods=['POST'])
def save_scores():
    data = request.get_json()
    subject_id = data.get('subject_id')
    term = data.get('term')
    scores_data = data.get('scores') # 格式: [{"student_id": 1, "score": 95}, ...]

    for item in scores_data:
        # 查找是否已有记录
        existing_score = Score.query.filter_by(
            student_id=item['student_id'],
            subject_id=subject_id,
            term=term
        ).first()

        if existing_score:
            existing_score.score = item['score']
        else:
            new_score = Score(
                student_id=item['student_id'],
                subject_id=subject_id,
                score=item['score'],
                term=term
            )
            db.session.add(new_score)
            
    db.session.commit()
    return jsonify({"msg": "成绩保存成功"})