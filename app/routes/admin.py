from flask import Blueprint, request, jsonify
from app.models import db, User, Teacher, Subject
from app.models import db, ClassInfo, Student
from datetime import datetime
from app.models import db, Student, Score, Subject, ClassInfo,CourseAssignment
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__)

# --- 1. 用户审核模块 ---

# 获取所有待审核用户
@admin_bp.route('/pending_users', methods=['GET'])
def get_pending_users():
    users = User.query.filter_by(is_approved=False).all()
    return jsonify([{
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "name": user.teacher_profile.name if user.teacher_profile else "管理员"
    } for user in users])

# 审核通过
@admin_bp.route('/approve_user/<int:user_id>', methods=['POST'])
def approve_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "用户不存在"}), 404
    user.is_approved = True
    db.session.commit()
    return jsonify({"msg": "审核已通过"})

# 拒绝申请（直接删除记录）
@admin_bp.route('/reject_user/<int:user_id>', methods=['DELETE'])
def reject_user(user_id):
    user = User.query.get(user_id)
    if user:
        if user.teacher_profile:
            db.session.delete(user.teacher_profile)
        db.session.delete(user)
        db.session.commit()
    return jsonify({"msg": "申请已拒绝"})

# --- 2. 教师管理模块 ---

# 获取所有正式教师列表
@admin_bp.route('/teachers', methods=['GET'])
def get_teachers():
    # 联表查询：获取已通过审核的老师
    teachers = db.session.query(Teacher, User, Subject).join(
        User, Teacher.user_id == User.id
    ).outerjoin(
        Subject, Teacher.subject_id == Subject.id
    ).filter(User.is_approved == True).all()

    return jsonify([{
        "id": t.Teacher.id,
        "username": t.User.username,
        "name": t.Teacher.name,
        "phone": t.Teacher.phone,
        "subject_name": t.Subject.name if t.Subject else "未设置",
        "subject_id": t.Teacher.subject_id
    } for t in teachers])

# 修改教师信息
@admin_bp.route('/teachers/<int:t_id>', methods=['PUT'])
def update_teacher(t_id):
    data = request.get_json()
    teacher = Teacher.query.get(t_id)
    if not teacher: return jsonify({"msg": "找不到该教师"}), 404
    
    teacher.name = data.get('name', teacher.name)
    teacher.phone = data.get('phone', teacher.phone)
    teacher.subject_id = data.get('subject_id')
    db.session.commit()
    return jsonify({"msg": "信息更新成功"})

# --- 3. 班级管理 ---

@admin_bp.route('/classes', methods=['GET'])
def get_classes():
    # 获取所有班级，并按入学年份降序排
    classes = ClassInfo.query.order_by(ClassInfo.entry_year.desc(), ClassInfo.class_num.asc()).all()
    return jsonify([{
        "id": c.id,
        "entry_year": c.entry_year,
        "class_num": c.class_num,
        "grade_name": c.grade_display  # 使用我们在 models 定义的动态计算属性
    } for c in classes])

@admin_bp.route('/classes', methods=['POST'])
def add_class():
    data = request.get_json()
    new_class = ClassInfo(entry_year=data['entry_year'], class_num=data['class_num'])
    db.session.add(new_class)
    db.session.commit()
    return jsonify({"msg": "班级创建成功"})

# --- 4. 学生学籍管理 ---

@admin_bp.route('/students', methods=['GET'])
def get_students():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    class_id = request.args.get('class_id', type=int)
    
    query = Student.query
    if class_id:
        query = query.filter_by(class_id=class_id)
    
    # 分页查询，这对老旧电脑至关重要
    pagination = query.paginate(page=page, per_page=limit, error_out=False)
    students = pagination.items
    
    return jsonify({
        "total": pagination.total,
        "data": [{
            "id": s.id,
            "student_id": s.student_id,
            "name": s.name,
            "gender": s.gender,
            "class_id": s.class_id,
            "grade_class": f"{s.current_class.grade_display}({s.current_class.class_num})班" if s.current_class else "未分配"
        } for s in students]
    })

@admin_bp.route('/students', methods=['POST'])
def add_student():
    data = request.get_json()
    if Student.query.filter_by(student_id=data['student_id']).first():
        return jsonify({"msg": "学号已存在"}), 400
        
    student = Student(
        student_id=data['student_id'],
        name=data['name'],
        gender=data.get('gender', '未知'),
        class_id=data['class_id']
    )
    db.session.add(student)
    db.session.commit()
    return jsonify({"msg": "学生添加成功"})


# --- 5. 成绩统计与排名 ---

@admin_bp.route('/stats/class_report', methods=['GET'])
def get_class_report():
    class_id = request.args.get('class_id')
    term = request.args.get('term')
    
    if not class_id or not term:
        return jsonify({"subjects": [], "report": [], "subject_averages": {}})

    subjects = Subject.query.all()
    subject_map = {s.id: s.name for s in subjects}
    students = Student.query.filter_by(class_id=class_id).all()
    
    report_data = []
    # 用于记录各科全班总分和有效考试人数，格式: {"语文": {"sum": 500, "count": 5}}
    subject_stats = {s.name: {"sum": 0, "count": 0} for s in subjects}

    for s in students:
        scores = Score.query.filter_by(student_id=s.id, term=term).all()
        score_detail = {}
        student_total = 0
        
        for sc in scores:
            sub_name = subject_map.get(sc.subject_id)
            if sub_name:
                score_detail[sub_name] = sc.score
                student_total += sc.score
                # 累加到全班科目统计中
                subject_stats[sub_name]["sum"] += sc.score
                subject_stats[sub_name]["count"] += 1
        
        report_data.append({
            "student_id": s.student_id,
            "name": s.name,
            "scores": score_detail,
            "total": round(student_total, 1)
        })

    # 计算各科全班平均分
    class_subject_averages = {}
    for sub_name, stats in subject_stats.items():
        if stats["count"] > 0:
            class_subject_averages[sub_name] = round(stats["sum"] / stats["count"], 1)
        else:
            class_subject_averages[sub_name] = "-"

    # 排序并生成排名
    report_data.sort(key=lambda x: x['total'], reverse=True)
    for index, item in enumerate(report_data):
        item['rank'] = index + 1

    return jsonify({
        "subjects": [s.name for s in subjects],
        "report": report_data,
        "subject_averages": class_subject_averages  # 新增：返回各科全班均分
    })


# --- 6. 任课分配管理 ---

@admin_bp.route('/assignments', methods=['GET'])
def get_assignments():
    # 联表查询，获取 老师名、班级名、科目名
    results = db.session.query(
        CourseAssignment.id,
        Teacher.name.label('teacher_name'),
        ClassInfo.entry_year,
        ClassInfo.class_num,
        Subject.name.label('subject_name')
    ).join(Teacher, CourseAssignment.teacher_id == Teacher.id)\
     .join(ClassInfo, CourseAssignment.class_id == ClassInfo.id)\
     .join(Subject, CourseAssignment.subject_id == Subject.id).all()

    return jsonify([{
        "id": r.id,
        "teacher_name": r.teacher_name,
        "grade_class": f"{r.entry_year}级({r.class_num})班",
        "subject_name": r.subject_name
    } for r in results])

@admin_bp.route('/assignments', methods=['POST'])
def add_assignment():
    data = request.get_json()
    # 检查是否已经存在相同的分配（同一个老师在一个班教同一门课）
    exists = CourseAssignment.query.filter_by(
        teacher_id=data['teacher_id'],
        class_id=data['class_id'],
        subject_id=data['subject_id']
    ).first()
    
    if exists:
        return jsonify({"msg": "该分配已存在"}), 400

    new_assign = CourseAssignment(
        teacher_id=data['teacher_id'],
        class_id=data['class_id'],
        subject_id=data['subject_id']
    )
    db.session.add(new_assign)
    db.session.commit()
    return jsonify({"msg": "分配成功"})

@admin_bp.route('/assignments/<int:a_id>', methods=['DELETE'])
def delete_assignment(a_id):
    assign = CourseAssignment.query.get(a_id)
    if assign:
        db.session.delete(assign)
        db.session.commit()
    return jsonify({"msg": "已取消该任课分配"})

# “选择科目”实现
@admin_bp.route('/subjects', methods=['GET'])
def get_all_subjects():
    subs = Subject.query.all()
    return jsonify([{"id": s.id, "name": s.name} for s in subs])