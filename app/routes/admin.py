from flask import Blueprint, request, jsonify
import pandas as pd
import os
from app.models import (
    db,
    User,
    Teacher,
    Subject,
    ClassInfo,
    CourseAssignment,
    Student,
    Score,
)
from app.models import (
    HeadTeacherAssignment,
    GradeLeaderAssignment,
    SubjectGroupLeaderAssignment,
    PrepGroupLeaderAssignment,
)
from datetime import datetime
import re  # 引入正则模块用于校验

admin_bp = Blueprint("admin", __name__)

# --- 1. 用户审核模块 ---


# 获取所有待审核用户
@admin_bp.route("/pending_users", methods=["GET"])
def get_pending_users():
    users = User.query.filter_by(is_approved=False).all()
    return jsonify(
        [
            {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "name": user.teacher_profile.name if user.teacher_profile else "管理员",
            }
            for user in users
        ]
    )


# 审核通过
@admin_bp.route("/approve_user/<int:user_id>", methods=["POST"])
def approve_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "用户不存在"}), 404
    user.is_approved = True
    db.session.commit()
    return jsonify({"msg": "审核已通过"})


# 拒绝申请（直接删除记录）
@admin_bp.route("/reject_user/<int:user_id>", methods=["DELETE"])
def reject_user(user_id):
    user = User.query.get(user_id)
    if user:
        if user.teacher_profile:
            db.session.delete(user.teacher_profile)
        db.session.delete(user)
        db.session.commit()
    return jsonify({"msg": "申请已拒绝"})


# --- 2. 教师管理模块 ---
@admin_bp.route("/teachers", methods=["GET"])
def get_teachers():
    teachers = (
        db.session.query(Teacher, User)
        .join(User, Teacher.user_id == User.id)
        .filter(User.is_approved == True)
        .all()
    )

    result = []
    for t, u in teachers:
        # 1. 班主任信息聚合
        ht_list = [
            h.class_info.full_name for h in t.head_teacher_assigns if h.class_info
        ]
        ht_str = "、".join(ht_list) if ht_list else "否"

        # 2. 级长信息聚合
        gl_list = [g.grade_name for g in t.grade_leader_assigns]
        gl_str = "、".join(gl_list) if gl_list else "否"

        # 3. 科组长信息聚合
        sgl_list = [s.subject.name for s in t.subject_group_assigns if s.subject]
        sgl_str = "、".join(sgl_list) if sgl_list else "否"

        # 4. 备课组长信息聚合
        pgl_list = [
            f"{p.grade_name}{p.subject.name}" for p in t.prep_group_assigns if p.subject
        ]
        pgl_str = "、".join(pgl_list) if pgl_list else "否"

        # 5. 任教信息聚合 (任教级、任教班、任教学科)
        courses = t.course_assignments
        teaching_grades = sorted(
            list(set([c.class_info.grade_display for c in courses if c.class_info]))
        )
        teaching_classes = sorted(
            list(set([c.class_info.full_name for c in courses if c.class_info]))
        )
        teaching_subjects = sorted(
            list(set([c.subject.name for c in courses if c.subject]))
        )

        # 构造职务显示字符串
        # 简单的逻辑：如果有具体职务，显示职务名，否则显示“科任”
        duty_parts = []
        if ht_list:
            duty_parts.append("班主任")
        if gl_list:
            duty_parts.append("级长")
        if sgl_list:
            duty_parts.append("科组长")
        if pgl_list:
            duty_parts.append("备课组长")
        if not duty_parts:
            duty_parts.append("科任")  # 默认

        result.append(
            {
                "id": t.id,
                "username": u.username,
                "name": t.name,
                "gender": t.gender,
                "ethnicity": t.ethnicity,
                "status": t.status,
                "job_duty_display": "、".join(
                    duty_parts
                ),  # 职务概要 (如: 班主任、级长)
                "job_title": t.job_title,
                "education": t.education,
                "major": t.major,
                "phone": t.phone,
                # 详细职务描述 (用于Tooltip或详情)
                "head_teacher_desc": ht_str,
                "grade_leader_desc": gl_str,
                "subject_group_desc": sgl_str,
                "prep_group_desc": pgl_str,
                # 供编辑回显用的ID列表
                "head_teacher_ids": [h.class_id for h in t.head_teacher_assigns],
                "grade_leader_years": [g.entry_year for g in t.grade_leader_assigns],
                "subject_group_ids": [s.subject_id for s in t.subject_group_assigns],
                # 备课组长比较复杂，存对象结构
                "prep_group_data": [
                    {"entry_year": p.entry_year, "subject_id": p.subject_id}
                    for p in t.prep_group_assigns
                ],
                # 教学情况
                "teaching_grades": (
                    "、".join(teaching_grades) if teaching_grades else "-"
                ),
                "teaching_classes": (
                    "、".join(teaching_classes) if teaching_classes else "未分配"
                ),
                "teaching_subjects": (
                    "、".join(teaching_subjects) if teaching_subjects else "-"
                ),
                "remarks": t.remarks,
            }
        )
    return jsonify(result)


@admin_bp.route("/teachers/<int:t_id>", methods=["PUT"])
def update_teacher(t_id):
    data = request.get_json()
    teacher = Teacher.query.get(t_id)
    if not teacher:
        return jsonify({"msg": "找不到该教师"}), 404

    # 1. 更新基础信息
    teacher.name = data.get("name", teacher.name)
    teacher.gender = data.get("gender", teacher.gender)
    teacher.ethnicity = data.get("ethnicity", teacher.ethnicity)
    teacher.phone = data.get("phone", teacher.phone)
    teacher.status = data.get("status", teacher.status)
    teacher.job_title = data.get("job_title", teacher.job_title)
    teacher.education = data.get("education", teacher.education)
    teacher.major = data.get("major", teacher.major)
    teacher.remarks = data.get("remarks", teacher.remarks)

    # 2. 更新班主任 (全删全加策略，简单可靠)
    # 前端传 head_teacher_ids: [1, 2]
    HeadTeacherAssignment.query.filter_by(teacher_id=teacher.id).delete()
    if "head_teacher_ids" in data:
        for cid in data["head_teacher_ids"]:
            db.session.add(HeadTeacherAssignment(teacher_id=teacher.id, class_id=cid))

    # 3. 更新级长
    # 前端传 grade_leader_years: [2023, 2024]
    GradeLeaderAssignment.query.filter_by(teacher_id=teacher.id).delete()
    if "grade_leader_years" in data:
        for year in data["grade_leader_years"]:
            db.session.add(
                GradeLeaderAssignment(teacher_id=teacher.id, entry_year=year)
            )

    # 4. 更新科组长
    # 前端传 subject_group_ids: [1]
    SubjectGroupLeaderAssignment.query.filter_by(teacher_id=teacher.id).delete()
    if "subject_group_ids" in data:
        for sid in data["subject_group_ids"]:
            db.session.add(
                SubjectGroupLeaderAssignment(teacher_id=teacher.id, subject_id=sid)
            )

    # 5. 更新备课组长
    # 前端传 prep_group_data: [{"entry_year": 2023, "subject_id": 1}, ...]
    PrepGroupLeaderAssignment.query.filter_by(teacher_id=teacher.id).delete()
    if "prep_group_data" in data:
        for item in data["prep_group_data"]:
            if item.get("entry_year") and item.get("subject_id"):
                db.session.add(
                    PrepGroupLeaderAssignment(
                        teacher_id=teacher.id,
                        entry_year=item["entry_year"],
                        subject_id=item["subject_id"],
                    )
                )

    db.session.commit()
    return jsonify({"msg": "教师信息更新成功"})


# --- 3. 班级管理 ---


@admin_bp.route("/classes", methods=["GET"])
def get_classes():
    # 获取所有班级，并按入学年份降序排
    classes = ClassInfo.query.order_by(
        ClassInfo.entry_year.desc(), ClassInfo.class_num.asc()
    ).all()
    return jsonify(
        [
            {
                "id": c.id,
                "entry_year": c.entry_year,
                "class_num": c.class_num,
                "grade_name": c.grade_display,  # 使用我们在 models 定义的动态计算属性
            }
            for c in classes
        ]
    )


@admin_bp.route("/classes", methods=["POST"])
def add_class():
    data = request.get_json()
    new_class = ClassInfo(entry_year=data["entry_year"], class_num=data["class_num"])
    db.session.add(new_class)
    db.session.commit()
    return jsonify({"msg": "班级创建成功"})


# --- 4. 学生学籍管理 ---


@admin_bp.route("/students", methods=["GET"])
def get_students():
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 20, type=int)
    class_id = request.args.get("class_id", type=int)

    query = Student.query
    if class_id:
        query = query.filter_by(class_id=class_id)

    pagination = query.order_by(Student.student_id.asc()).paginate(
        page=page, per_page=limit, error_out=False
    )

    data = []
    for s in pagination.items:
        # 格式化班级名
        class_name = "未分配"
        if s.current_class_rel:
            c = s.current_class_rel
            short_year = str(c.entry_year)[-2:]
            class_num_str = str(c.class_num).zfill(2)
            class_name = f"{short_year}级({class_num_str})班"

        data.append(
            {
                "id": s.id,
                "student_id": s.student_id,
                "name": s.name,
                "gender": s.gender,
                "class_id": s.class_id,
                "grade_class": class_name,
                "status": s.status,
                "household_registration": s.household_registration,
                "city_school_id": s.city_school_id,
                "national_school_id": s.national_school_id,
                "id_card_number": s.id_card_number,  # 新增返回
                "remarks": s.remarks,
            }
        )

    return jsonify({"total": pagination.total, "data": data})


@admin_bp.route("/students", methods=["POST"])
def add_student():
    data = request.get_json()

    # 基础校验
    if Student.query.filter_by(student_id=data["student_id"]).first():
        return jsonify({"msg": "学号已存在"}), 400

    # 身份证查重
    id_card = data.get("id_card_number")
    if id_card and Student.query.filter_by(id_card_number=id_card).first():
        return jsonify({"msg": "身份证号已存在"}), 400

    # 校验市学籍号 (必须为纯数字)
    city_sid = data.get("city_school_id", "")
    if city_sid and not city_sid.isdigit():
        return jsonify({"msg": "市学籍号必须为纯数字"}), 400

    student = Student(
        student_id=data["student_id"],
        name=data["name"],
        gender=data.get("gender", "男"),
        class_id=data["class_id"],
        status=data.get("status", "在读"),
        household_registration=data.get("household_registration"),
        city_school_id=city_sid,
        national_school_id=data.get("national_school_id"),
        id_card_number=id_card,  # 新增保存
        remarks=data.get("remarks"),
    )
    db.session.add(student)
    db.session.commit()
    return jsonify({"msg": "学生添加成功"})


@admin_bp.route("/students/<int:s_id>", methods=["PUT"])
def update_student(s_id):
    data = request.get_json()
    student = Student.query.get(s_id)
    if not student:
        return jsonify({"msg": "学生不存在"}), 404

    # 校验市学籍号
    city_sid = data.get("city_school_id", student.city_school_id)
    if city_sid and not str(city_sid).isdigit():
        return jsonify({"msg": "市学籍号必须为纯数字"}), 400

    # 校验身份证查重 (排除自己)
    new_id_card = data.get("id_card_number")
    if new_id_card and new_id_card != student.id_card_number:
        if Student.query.filter_by(id_card_number=new_id_card).first():
            return jsonify({"msg": "该身份证号已被其他学生占用"}), 400

    student.name = data.get("name", student.name)
    student.gender = data.get("gender", student.gender)
    student.class_id = data.get("class_id", student.class_id)
    student.status = data.get("status", student.status)
    student.household_registration = data.get(
        "household_registration", student.household_registration
    )
    student.city_school_id = city_sid
    student.national_school_id = data.get(
        "national_school_id", student.national_school_id
    )
    student.id_card_number = new_id_card  # 新增更新
    student.remarks = data.get("remarks", student.remarks)

    db.session.commit()
    return jsonify({"msg": "学生信息更新成功"})


# --- 5. 成绩统计与排名 ---


@admin_bp.route("/stats/class_report", methods=["GET"])
def get_class_report():
    class_id = request.args.get("class_id")
    term = request.args.get("term")

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

        report_data.append(
            {
                "student_id": s.student_id,
                "name": s.name,
                "scores": score_detail,
                "total": round(student_total, 1),
            }
        )

    # 计算各科全班平均分
    class_subject_averages = {}
    for sub_name, stats in subject_stats.items():
        if stats["count"] > 0:
            class_subject_averages[sub_name] = round(stats["sum"] / stats["count"], 1)
        else:
            class_subject_averages[sub_name] = "-"

    # 排序并生成排名
    report_data.sort(key=lambda x: x["total"], reverse=True)
    for index, item in enumerate(report_data):
        item["rank"] = index + 1

    return jsonify(
        {
            "subjects": [s.name for s in subjects],
            "report": report_data,
            "subject_averages": class_subject_averages,  # 新增：返回各科全班均分
        }
    )


# --- 6. 任课分配管理 ---


@admin_bp.route("/assignments", methods=["GET"])
def get_assignments():
    # 联表查询，获取 老师名、班级名、科目名
    results = (
        db.session.query(
            CourseAssignment.id,
            Teacher.name.label("teacher_name"),
            ClassInfo.entry_year,
            ClassInfo.class_num,
            Subject.name.label("subject_name"),
        )
        .join(Teacher, CourseAssignment.teacher_id == Teacher.id)
        .join(ClassInfo, CourseAssignment.class_id == ClassInfo.id)
        .join(Subject, CourseAssignment.subject_id == Subject.id)
        .all()
    )

    return jsonify(
        [
            {
                "id": r.id,
                "teacher_name": r.teacher_name,
                "grade_class": f"{r.entry_year}级({r.class_num})班",
                "subject_name": r.subject_name,
            }
            for r in results
        ]
    )


@admin_bp.route("/assignments", methods=["POST"])
def add_assignment():
    data = request.get_json()
    # 检查是否已经存在相同的分配（同一个老师在一个班教同一门课）
    exists = CourseAssignment.query.filter_by(
        teacher_id=data["teacher_id"],
        class_id=data["class_id"],
        subject_id=data["subject_id"],
    ).first()

    if exists:
        return jsonify({"msg": "该分配已存在"}), 400

    new_assign = CourseAssignment(
        teacher_id=data["teacher_id"],
        class_id=data["class_id"],
        subject_id=data["subject_id"],
    )
    db.session.add(new_assign)
    db.session.commit()
    return jsonify({"msg": "分配成功"})


@admin_bp.route("/assignments/<int:a_id>", methods=["DELETE"])
def delete_assignment(a_id):
    assign = CourseAssignment.query.get(a_id)
    if assign:
        db.session.delete(assign)
        db.session.commit()
    return jsonify({"msg": "已取消该任课分配"})


# “选择科目”实现
@admin_bp.route("/subjects", methods=["GET"])
def get_all_subjects():
    subs = Subject.query.all()
    return jsonify([{"id": s.id, "name": s.name} for s in subs])


# --- 7. Excel 导入功能 ---
# 导入学生
@admin_bp.route("/students/import", methods=["POST"])
def import_students_excel():
    if "file" not in request.files:
        return jsonify({"msg": "没有上传文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"msg": "文件名为空"}), 400

    try:
        # 读取 Excel
        df = pd.read_excel(file)

        # 简单校验表头是否包含关键字段
        required_columns = ["姓名", "学号", "班级名称"]
        if not all(col in df.columns for col in required_columns):
            return (
                jsonify({"msg": "Excel格式错误，缺少必要列(姓名/学号/班级名称)"}),
                400,
            )

        success_count = 0
        updated_count = 0

        for index, row in df.iterrows():
            # 1. 解析班级信息 "23级(01)班" -> entry_year=2023, class_num=1
            class_str = str(row["班级名称"]).strip()
            # 正则匹配：数字 + 级 + ( + 数字 + ) + 班
            match = re.match(r"(\d+)级\((\d+)\)班", class_str)

            class_id = None
            if match:
                short_year = int(match.group(1))  # 23
                class_num = int(match.group(2))  # 01
                # 假设是 20xx 年
                entry_year = 2000 + short_year

                # 查找班级是否存在，不存在则创建
                existing_class = ClassInfo.query.filter_by(
                    entry_year=entry_year, class_num=class_num
                ).first()
                if existing_class:
                    class_id = existing_class.id
                else:
                    new_class = ClassInfo(entry_year=entry_year, class_num=class_num)
                    db.session.add(new_class)
                    db.session.flush()  # 以此获取 id
                    class_id = new_class.id
            else:
                # 班级格式不对，跳过或记录日志，这里选择暂时跳过该行或设为未分配
                continue

            # 2. 准备学生数据
            student_id = str(row["学号"]).strip()

            # 检查学生是否已存在 (更新或跳过，这里选择更新)
            student = Student.query.filter_by(student_id=student_id).first()
            is_new = False

            if not student:
                student = Student(student_id=student_id)
                is_new = True

            # 填充/更新字段
            student.name = str(row["姓名"])
            student.gender = str(row.get("性别", "男"))
            student.class_id = class_id
            student.status = str(row.get("状态", "在读"))
            student.household_registration = str(row.get("户口属地", "本市"))
            student.id_card_number = str(row.get("身份证号", ""))

            # 处理学籍号，确保是字符串且去除 .0 (pandas读取数字有时会带小数)
            city_sid = str(row.get("市学籍号", ""))
            if city_sid.endswith(".0"):
                city_sid = city_sid[:-2]
            student.city_school_id = city_sid

            nat_sid = str(row.get("国家学籍号", ""))
            if nat_sid.endswith(".0"):
                nat_sid = nat_sid[:-2]
            student.national_school_id = nat_sid

            student.remarks = (
                str(row.get("备注", "")) if pd.notna(row.get("备注")) else ""
            )

            if is_new:
                db.session.add(student)
                success_count += 1
            else:
                updated_count += 1

        db.session.commit()
        return jsonify(
            {"msg": f"操作完成", "added": success_count, "updated": updated_count}
        )

    except Exception as e:
        print(e)
        return jsonify({"msg": f"导入失败: {str(e)}"}), 500


# 导入老师
@admin_bp.route("/teachers/import", methods=["POST"])
def import_teachers_excel():
    if "file" not in request.files:
        return jsonify({"msg": "没有上传文件"}), 400

    file = request.files["file"]
    try:
        df = pd.read_excel(file)
        # 填充 NaN 为空字符串，防止报错
        df = df.fillna("")
    except Exception as e:
        return jsonify({"msg": f"读取Excel失败: {str(e)}"}), 400

    # --- 1. 预处理：构建缓存字典，减少数据库查询次数 ---
    # 构建科目映射: {'语文': 1, '数学': 2}
    all_subjects = Subject.query.all()
    subject_map = {s.name: s.id for s in all_subjects}

    # 构建班级映射: {(2023, 1): 5}  key是(年份, 班号), value是class_id
    all_classes = ClassInfo.query.all()
    class_map = {(c.entry_year, c.class_num): c.id for c in all_classes}

    success_count = 0

    try:
        for index, row in df.iterrows():
            username = str(row.get("工号", "")).strip()
            name = str(row.get("姓名", "")).strip()
            if not username or not name:
                continue  # 跳过无效行

            # --- 2. 用户账户处理 ---
            user = User.query.filter_by(username=username).first()
            if not user:
                # 创建新用户，默认密码 123456
                user = User(username=username, role="teacher", is_approved=True)
                user.set_password("123456")
                db.session.add(user)
                db.session.flush()  # 以此获取 user.id

            # --- 3. 教师档案处理 ---
            teacher = Teacher.query.filter_by(user_id=user.id).first()
            if not teacher:
                teacher = Teacher(user_id=user.id, name=name)
                db.session.add(teacher)
            else:
                teacher.name = name  # 更新姓名

            # 更新基础信息
            teacher.gender = str(row.get("性别", "男"))
            teacher.phone = str(row.get("电话", ""))
            teacher.job_title = str(row.get("职称", ""))

            db.session.flush()  # 确保 teacher.id 可用

            # ================= 复杂职务解析 =================

            # 定义分隔符处理函数 (支持中英文逗号)
            def split_str(s):
                return [x.strip() for x in re.split(r"[,，]", str(s)) if x.strip()]

            # 辅助函数：解析班级字符串 "23级(1)班" -> class_id
            def parse_class_id(cls_str):
                # 匹配 "23级(1)班" 或 "2023级(01)班"
                match = re.search(r"(\d+)级\D*?(\d+)\D*?班", cls_str)
                if match:
                    y_str = match.group(1)
                    c_num = int(match.group(2))
                    # 处理年份：如果是 23 则转为 2023
                    entry_year = int(y_str) if len(y_str) == 4 else 2000 + int(y_str)
                    return class_map.get((entry_year, c_num))
                return None

            # 辅助函数：解析年份 "23级" -> 2023
            def parse_year(yr_str):
                match = re.search(r"(\d+)级?", yr_str)
                if match:
                    y_str = match.group(1)
                    return int(y_str) if len(y_str) == 4 else 2000 + int(y_str)
                return None

            # --- A. 班主任分配 ---
            # 策略：先删除该老师所有的旧班主任记录，再添加新的
            HeadTeacherAssignment.query.filter_by(teacher_id=teacher.id).delete()
            ht_str = row.get("班主任分配", "")
            for item in split_str(ht_str):
                cid = parse_class_id(item)
                if cid:
                    db.session.add(
                        HeadTeacherAssignment(teacher_id=teacher.id, class_id=cid)
                    )

            # --- B. 级长分配 ---
            GradeLeaderAssignment.query.filter_by(teacher_id=teacher.id).delete()
            gl_str = row.get("级长分配", "")
            for item in split_str(gl_str):
                year = parse_year(item)
                if year:
                    db.session.add(
                        GradeLeaderAssignment(teacher_id=teacher.id, entry_year=year)
                    )

            # --- C. 科组长分配 ---
            SubjectGroupLeaderAssignment.query.filter_by(teacher_id=teacher.id).delete()
            sgl_str = row.get("科组长分配", "")
            for item in split_str(sgl_str):
                # 假设输入直接是科目名 "语文"
                sid = subject_map.get(item)
                if sid:
                    db.session.add(
                        SubjectGroupLeaderAssignment(
                            teacher_id=teacher.id, subject_id=sid
                        )
                    )

            # --- D. 备课组长分配 (格式: "23级语文") ---
            PrepGroupLeaderAssignment.query.filter_by(teacher_id=teacher.id).delete()
            pgl_str = row.get("备课组长分配", "")
            for item in split_str(pgl_str):
                # 拆解年份和科目
                # 这里假设格式紧凑，先提取数字作为年份，剩下的作为科目
                year_match = re.match(r"(\d+)级?", item)
                if year_match:
                    y_str = year_match.group(1)
                    entry_year = int(y_str) if len(y_str) == 4 else 2000 + int(y_str)
                    # 移除年份部分，剩下的即为科目名 (需去掉"级"字)
                    sub_name = item.replace(y_str, "").replace("级", "").strip()
                    sid = subject_map.get(sub_name)
                    if entry_year and sid:
                        db.session.add(
                            PrepGroupLeaderAssignment(
                                teacher_id=teacher.id,
                                entry_year=entry_year,
                                subject_id=sid,
                            )
                        )

            # --- E. 任教分配 (格式: "23级(1)班-语文") ---
            CourseAssignment.query.filter_by(teacher_id=teacher.id).delete()
            teach_str = row.get("任教分配", "")
            for item in split_str(teach_str):
                # 用 '-' 或 '_' 分隔班级和科目
                parts = re.split(r"[-_]", item)
                if len(parts) >= 2:
                    cls_part = parts[0].strip()
                    sub_part = parts[1].strip()

                    cid = parse_class_id(cls_part)
                    sid = subject_map.get(sub_part)

                    if cid and sid:
                        db.session.add(
                            CourseAssignment(
                                teacher_id=teacher.id, class_id=cid, subject_id=sid
                            )
                        )

            success_count += 1

        db.session.commit()
        return jsonify({"msg": f"导入成功，共处理 {success_count} 位教师信息"})

    except Exception as e:
        db.session.rollback()
        import traceback

        traceback.print_exc()
        return jsonify({"msg": f"处理数据时出错: {str(e)}"}), 500
