from flask import Blueprint, request, jsonify, send_file, current_app
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
    ExamTask,
)
from sqlalchemy import func
from datetime import datetime
import re  # 引入正则模块用于校验
import io
from docxtpl import DocxTemplate

admin_bp = Blueprint("admin", __name__)

SUBJECT_PRIORITY = [
    "语文",
    "数学",
    "英语",
    "英语听说",
    "物理",
    "化学",
    "道德与法治",
    "历史",
    "生物",
    "地理",
    "体育与健康",
    "信息科技",
    "美术",
    "音乐",
]

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
    # 1. 获取筛选参数
    current_year = datetime.now().year
    # 默认查看当前学年 (如 2025年2月 -> 2024学年)
    default_year = current_year if datetime.now().month >= 9 else current_year - 1

    academic_year = request.args.get("academic_year", default_year, type=int)
    status_filter = request.args.get("status", "在职")  # 默认只看在职

    # 2. 查询教师基础信息
    query = db.session.query(Teacher, User).join(User, Teacher.user_id == User.id)

    if status_filter != "全部":
        query = query.filter(Teacher.status == status_filter)

    teachers = query.all()

    result = []
    for t, u in teachers:
        # --- 核心修改：只聚合指定学年的职务信息 ---

        # 1. 班主任 (带年份过滤)
        ht_list = [
            h.class_info.full_name
            for h in t.head_teacher_assigns
            if h.academic_year == academic_year and h.class_info
        ]
        ht_str = "、".join(ht_list) if ht_list else "否"

        # 2. 级长 (带年份过滤)
        gl_list = [
            g.grade_name
            for g in t.grade_leader_assigns
            if g.academic_year == academic_year
        ]
        gl_str = "、".join(gl_list) if gl_list else "否"

        # 3. 科组长 (带年份过滤)
        sgl_list = [
            s.subject.name
            for s in t.subject_group_assigns
            if s.academic_year == academic_year and s.subject
        ]
        sgl_str = "、".join(sgl_list) if sgl_list else "否"

        # 4. 备课组长 (带年份过滤)
        pgl_list = [
            f"{p.grade_name}{p.subject.name}"
            for p in t.prep_group_assigns
            if p.academic_year == academic_year and p.subject
        ]
        pgl_str = "、".join(pgl_list) if pgl_list else "否"

        # 5. 任教信息 (带年份过滤)
        # 注意：这里展示的是该老师在该学年的教学任务
        my_courses = [
            c for c in t.course_assignments if c.academic_year == academic_year
        ]

        teaching_grades = sorted(
            list(set([c.class_info.grade_display for c in my_courses if c.class_info]))
        )
        teaching_classes = sorted(
            list(set([c.class_info.full_name for c in my_courses if c.class_info]))
        )
        teaching_subjects = sorted(
            list(set([c.subject.name for c in my_courses if c.subject]))
        )

        # 构造职务显示字符串
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
            duty_parts.append("科任")

        result.append(
            {
                "id": t.id,
                "username": u.username,
                "name": t.name,
                "gender": t.gender,
                "ethnicity": t.ethnicity,
                "status": t.status,  # 这里的状态是当前的最新状态
                "job_duty_display": "、".join(duty_parts),  # 职务是指定学年的
                "job_title": t.job_title,
                "education": t.education,
                "major": t.major,
                "phone": t.phone,
                # 详细描述
                "head_teacher_desc": ht_str,
                "grade_leader_desc": gl_str,
                "subject_group_desc": sgl_str,
                "prep_group_desc": pgl_str,
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

    # --- 0. 确定操作的学年 ---
    # 如果前端在编辑时传入了 academic_year，则更新那一年的职务
    # 否则默认更新当前学年 (9月为界)
    req_year = data.get("academic_year")
    if req_year:
        target_year = int(req_year)
    else:
        now = datetime.now()
        target_year = now.year if now.month >= 9 else now.year - 1

    # --- 1. 更新基础信息 (全局有效，不分年份) ---
    teacher.name = data.get("name", teacher.name)
    teacher.gender = data.get("gender", teacher.gender)
    teacher.ethnicity = data.get("ethnicity", teacher.ethnicity)
    teacher.phone = data.get("phone", teacher.phone)
    teacher.status = data.get("status", teacher.status)
    teacher.job_title = data.get("job_title", teacher.job_title)
    teacher.education = data.get("education", teacher.education)
    teacher.major = data.get("major", teacher.major)
    teacher.remarks = data.get("remarks", teacher.remarks)

    # --- 2. 更新职务 (严格限定在 target_year) ---

    # A. 更新班主任
    # 先只删该学年的
    HeadTeacherAssignment.query.filter_by(
        teacher_id=teacher.id, academic_year=target_year
    ).delete()
    if "head_teacher_ids" in data:
        for cid in data["head_teacher_ids"]:
            db.session.add(
                HeadTeacherAssignment(
                    teacher_id=teacher.id,
                    class_id=cid,
                    academic_year=target_year,  # 写入学年
                )
            )

    # B. 更新级长
    GradeLeaderAssignment.query.filter_by(
        teacher_id=teacher.id, academic_year=target_year
    ).delete()
    if "grade_leader_years" in data:
        for year in data["grade_leader_years"]:
            db.session.add(
                GradeLeaderAssignment(
                    teacher_id=teacher.id, entry_year=year, academic_year=target_year
                )
            )

    # C. 更新科组长
    SubjectGroupLeaderAssignment.query.filter_by(
        teacher_id=teacher.id, academic_year=target_year
    ).delete()
    if "subject_group_ids" in data:
        for sid in data["subject_group_ids"]:
            db.session.add(
                SubjectGroupLeaderAssignment(
                    teacher_id=teacher.id, subject_id=sid, academic_year=target_year
                )
            )

    # D. 更新备课组长
    PrepGroupLeaderAssignment.query.filter_by(
        teacher_id=teacher.id, academic_year=target_year
    ).delete()
    if "prep_group_data" in data:
        for item in data["prep_group_data"]:
            if item.get("entry_year") and item.get("subject_id"):
                db.session.add(
                    PrepGroupLeaderAssignment(
                        teacher_id=teacher.id,
                        entry_year=item["entry_year"],
                        subject_id=item["subject_id"],
                        academic_year=target_year,
                    )
                )

    db.session.commit()
    return jsonify({"msg": f"教师信息已更新 (针对 {target_year} 学年)"})


# 重置教师密码
@admin_bp.route("/teachers/<int:t_id>/reset_password", methods=["POST"])
def reset_teacher_password(t_id):
    teacher = Teacher.query.get(t_id)
    if not teacher or not teacher.user:
        return jsonify({"msg": "教师账号不存在"}), 404

    user = teacher.user
    user.set_password("123456")  # 重置为初始密码
    user.must_change_password = True  # 标记为需要强制修改
    db.session.commit()

    return jsonify({"msg": f"教师 {teacher.name} 的密码已重置为 123456"})


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
                # 核心修改：如果是缺考，返回字符串
                if sc.remark == "缺考":
                    score_detail[sub_name] = "缺考"
                    # 缺考算0分计入总分
                    student_total += 0
                else:
                    score_detail[sub_name] = sc.score
                    student_total += sc.score

                # 统计平均分时，缺考通常也算作分母（视为0分），或者不计入？
                # 这里保持原有逻辑：0分计入总分，count+1
                subject_stats[sub_name]["sum"] += sc.score  # 缺考score是0
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


@admin_bp.route("/stats/exam_names", methods=["GET"])
def get_grade_exam_names():
    entry_year = request.args.get("entry_year", type=int)
    if not entry_year:
        return jsonify([])

    # 查询该年级所有考试任务的名称并去重
    names = (
        db.session.query(ExamTask.name)
        .filter_by(entry_year=entry_year)
        .distinct()
        .all()
    )

    # names 是 list of tuples, 如 [('初一上期末',), ('期中考',)]
    return jsonify([n[0] for n in names])


# 新增：综合成绩报表接口
@admin_bp.route("/stats/comprehensive_report", methods=["POST"])
def get_comprehensive_report():
    data = request.get_json()
    # 接收参数
    entry_year = data.get("entry_year")  # 必填：入学年份 (用于确定年级)
    exam_name = data.get("exam_name")  # 必填：考试名称 (如 "初一上期末")
    subject_ids = data.get("subject_ids", [])  # 必填：选择的科目ID列表
    class_ids = data.get("class_ids", [])  # 选填：查看的班级ID列表，为空则查看全级

    if not entry_year or not exam_name or not subject_ids:
        return jsonify({"msg": "请选择完整的筛选条件（年级、考试、科目）"}), 400

    # 1. 获取该年级所有班级信息 (用于映射班级名和确定全级范围)
    all_classes = ClassInfo.query.filter_by(entry_year=entry_year).all()
    class_map = {c.id: c.full_name for c in all_classes}  # ID -> "初一(01)班"
    all_grade_class_ids = [c.id for c in all_classes]

    # 2. 获取该年级、该次考试、指定科目的 考试任务信息
    tasks = ExamTask.query.filter(
        ExamTask.entry_year == entry_year,
        ExamTask.name == exam_name,
        ExamTask.subject_id.in_(subject_ids),
    ).all()

    if not tasks:
        return jsonify({"data": [], "subjects": []})

    # 建立映射：任务ID -> 科目ID，任务ID -> 满分
    task_map = {t.id: t.subject_id for t in tasks}
    task_ids = [t.id for t in tasks]

    # 计算所选科目的总满分
    total_full_score = sum([t.full_score for t in tasks])

    # 3. 获取全级学生 (即使只看一个班，也需要全级数据来计算级排名)
    # 注意：这里我们获取该年级所有班级的学生
    students = Student.query.filter(Student.class_id.in_(all_grade_class_ids)).all()
    student_map = {s.id: s for s in students}

    # 4. 获取所有相关成绩
    scores = Score.query.filter(
        Score.exam_task_id.in_(task_ids), Score.student_id.in_(student_map.keys())
    ).all()

    # 5. 内存中进行数据组装与排名计算
    # 结构: { student_id: { total: 0, scores: {subj_name: score}, ... } }
    stats_data = {}

    # 获取科目名称映射
    subjects = (
        Subject.query.filter(Subject.id.in_(subject_ids))
        .order_by(Subject.id.asc())
        .all()
    )

    subject_name_map = {s.id: s.name for s in subjects}
    ordered_subject_names = [s.name for s in subjects]

    # 初始化学生数据容器
    for s in students:
        stats_data[s.id] = {
            "obj": s,
            "score_map": {},  # { '语文': 90, '数学': 100 }
            "total": 0,
        }

    # 填充成绩
    for sc in scores:
        sid = sc.student_id
        if sid in stats_data:
            subj_id = task_map.get(sc.exam_task_id)
            subj_name = subject_name_map.get(subj_id)
            if subj_name:
                # 核心修改：存储用于展示的值
                if sc.remark == "缺考":
                    stats_data[sid]["score_map"][subj_name] = "缺考"
                    # total 依然加 0
                    stats_data[sid]["total"] += 0
                else:
                    stats_data[sid]["score_map"][subj_name] = sc.score
                    stats_data[sid]["total"] += sc.score

    # 转换为列表以便排序
    result_list = list(stats_data.values())

    def sort_key(item):
        sm = item["score_map"]
        compare_tuple = [item["total"]]
        for sub in SUBJECT_PRIORITY:
            val = sm.get(sub, 0)
            # 如果是 "缺考" 字符串，在排序时视为 0
            if val == "缺考":
                val = 0
            compare_tuple.append(val)
        return tuple(compare_tuple)

    # --- 1. 计算级排名 (同时计算两种) ---
    result_list.sort(key=sort_key, reverse=True)

    for i, item in enumerate(result_list):
        # A. 连续排名 (User Definition): 严格的 1, 2, 3...
        # 既然已经按规则排好序了，直接用序号即可
        item["grade_rank_dense"] = i + 1

        # B. 跳过排名 (Legacy): 仅基于总分，同分并列 (1, 1, 3)
        if i > 0 and item["total"] < result_list[i - 1]["total"]:
            item["grade_rank_skip"] = i + 1
        elif i == 0:
            item["grade_rank_skip"] = 1
        else:
            # 总分相同，继承上一名的排名
            item["grade_rank_skip"] = result_list[i - 1]["grade_rank_skip"]

    # --- 2. 计算班排名 ---
    # 先按班级分组
    class_groups = {}
    for item in result_list:
        cid = item["obj"].class_id
        if cid not in class_groups:
            class_groups[cid] = []
        class_groups[cid].append(item)

    for cid, items in class_groups.items():
        # 组内应用同样的排序规则
        items.sort(key=sort_key, reverse=True)

        for i, sub_item in enumerate(items):
            # A. 班级连续 (严格 1, 2, 3)
            sub_item["class_rank_dense"] = i + 1

            # B. 班级跳过 (并列 1, 1, 3)
            if i > 0 and sub_item["total"] < items[i - 1]["total"]:
                sub_item["class_rank_skip"] = i + 1
            elif i == 0:
                sub_item["class_rank_skip"] = 1
            else:
                sub_item["class_rank_skip"] = items[i - 1]["class_rank_skip"]

    # 6. 最终过滤与格式化输出
    target_class_ids = set(class_ids) if class_ids else set(all_grade_class_ids)

    final_output = []

    # 再次按级排名顺序遍历
    for item in result_list:
        s = item["obj"]
        if s.class_id in target_class_ids:
            row = {
                "student_id": s.student_id,
                "name": s.name,
                "class_name": class_map.get(s.class_id, "未知班级"),
                "status": s.status,
                "full_score": total_full_score,
                "total": round(item["total"], 1),
                # 返回四种排名
                "grade_rank_skip": item["grade_rank_skip"],
                "grade_rank_dense": item["grade_rank_dense"],
                "class_rank_skip": item.get("class_rank_skip", "-"),
                "class_rank_dense": item.get("class_rank_dense", "-"),
                "scores": item["score_map"],
            }
            final_output.append(row)

    return jsonify({"data": final_output, "subjects": ordered_subject_names})


# --- 6. 任课分配管理 ---


@admin_bp.route("/assignments", methods=["GET"])
def get_assignments():
    # 1. 获取前端传来的学年参数
    academic_year = request.args.get("academic_year", type=int)

    # 2. 构建基础查询
    query = (
        db.session.query(
            CourseAssignment.id,
            Teacher.name.label("teacher_name"),
            ClassInfo.entry_year,
            ClassInfo.class_num,
            Subject.name.label("subject_name"),
            # 如果需要，也可以把 academic_year 查出来
        )
        .join(Teacher, CourseAssignment.teacher_id == Teacher.id)
        .join(ClassInfo, CourseAssignment.class_id == ClassInfo.id)
        .join(Subject, CourseAssignment.subject_id == Subject.id)
    )

    # 3. [关键] 如果有学年参数，增加筛选条件
    if academic_year:
        query = query.filter(CourseAssignment.academic_year == academic_year)

    # 4. 执行查询
    results = query.all()

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
    subs = Subject.query.order_by(Subject.id.asc()).all()
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
    # 必填：学年 (如 2025)
    academic_year = request.form.get("academic_year", type=int)
    if not academic_year:
        return jsonify({"msg": "请选择导入的学年"}), 400

    try:
        df = pd.read_excel(file).fillna("")
    except Exception as e:
        return jsonify({"msg": f"读取Excel失败: {str(e)}"}), 400

    # --- 定义合法年级范围 (初一至初三) ---
    # 例如 2025学年，合法年级为 [2025, 2024, 2023]
    valid_years = [academic_year, academic_year - 1, academic_year - 2]
    valid_years_str = "/".join([f"{y}级" for y in valid_years])

    # 预加载数据缓存
    all_subjects = Subject.query.all()
    subject_map = {s.name: s.id for s in all_subjects}

    # 正则工具函数
    def split_str(s):
        return [x.strip() for x in re.split(r"[,，]", str(s)) if x.strip()]

    def parse_year(yr_str):
        # 提取 "23级" 或 "2023级" 中的数字
        match = re.search(r"(\d+)级?", str(yr_str))
        if match:
            y_str = match.group(1)
            # 自动补全：23 -> 2023
            return int(y_str) if len(y_str) == 4 else 2000 + int(y_str)
        return None

    # --- 阶段一：严格数据校验 (不操作数据库) ---
    errors = []

    for index, row in df.iterrows():
        row_num = index + 2
        name = str(row.get("姓名", "")).strip()
        if not name:
            continue

        # 1. 校验级长分配
        gl_str = row.get("级长分配", "")
        for item in split_str(gl_str):
            entry_year = parse_year(item)
            if entry_year and entry_year not in valid_years:
                errors.append(
                    f"行{row_num} ({name}): 级长年份【{entry_year}级】在 {academic_year} 学年无效。合法范围: {valid_years_str}"
                )

        # 2. 校验备课组长分配 (格式如 "23级语文")
        pgl_str = row.get("备课组长分配", "")
        for item in split_str(pgl_str):
            # 解析年份
            y_match = re.search(r"(\d+)级?", item)
            if y_match:
                y_str = y_match.group(1)
                entry_year = int(y_str) if len(y_str) == 4 else 2000 + int(y_str)

                if entry_year not in valid_years:
                    errors.append(
                        f"行{row_num} ({name}): 备课组年份【{entry_year}级】在 {academic_year} 学年无效。合法范围: {valid_years_str}"
                    )

            # 顺便校验科目是否存在
            sub_name = re.sub(r"\d+级?", "", item).strip()
            if sub_name and sub_name not in subject_map:
                errors.append(f"行{row_num} ({name}): 备课组科目【{sub_name}】不存在")

    # 如果有任何错误，直接返回，不进行数据库操作
    if errors:
        # 只展示前 5 条错误，避免弹窗太长
        error_msg = "<br>".join(errors[:5])
        if len(errors) > 5:
            error_msg += f"<br>... 等共 {len(errors)} 处错误"
        return (
            jsonify({"msg": f"数据校验未通过，请修正Excel后重试：<br>{error_msg}"}),
            400,
        )

    # --- 阶段二：校验通过，执行写入 ---
    try:
        # 1. 清理该学年的旧行政职务
        db.session.query(GradeLeaderAssignment).filter_by(
            academic_year=academic_year
        ).delete()
        db.session.query(SubjectGroupLeaderAssignment).filter_by(
            academic_year=academic_year
        ).delete()
        db.session.query(PrepGroupLeaderAssignment).filter_by(
            academic_year=academic_year
        ).delete()

        added_count = 0
        updated_count = 0

        # 2. 遍历并写入
        for index, row in df.iterrows():
            username = str(row.get("工号", "")).strip()
            name = str(row.get("姓名", "")).strip()
            if not username or not name:
                continue

            # A. 查找或创建用户
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(
                    username=username,
                    role="teacher",
                    is_approved=True,
                    must_change_password=True,
                )
                user.set_password("123456")
                db.session.add(user)
                db.session.flush()

                teacher = Teacher(user_id=user.id, name=name)
                db.session.add(teacher)
                db.session.flush()
                added_count += 1
            else:
                teacher = user.teacher_profile
                if teacher:
                    teacher.name = name
                    updated_count += 1
                else:
                    teacher = Teacher(user_id=user.id, name=name)
                    db.session.add(teacher)
                    db.session.flush()

            # B. 更新基础信息
            teacher.gender = str(row.get("性别", teacher.gender))
            teacher.phone = str(row.get("电话", teacher.phone))
            teacher.job_title = str(row.get("职称", teacher.job_title))
            teacher.status = str(row.get("状态", teacher.status))

            # C. 插入行政职务 (此时数据已安全)

            # 级长
            gl_str = row.get("级长分配", "")
            for item in split_str(gl_str):
                entry_year = parse_year(item)
                if entry_year:
                    db.session.add(
                        GradeLeaderAssignment(
                            teacher_id=teacher.id,
                            entry_year=entry_year,
                            academic_year=academic_year,
                        )
                    )

            # 科组长
            sgl_str = row.get("科组长分配", "")
            for item in split_str(sgl_str):
                sid = subject_map.get(item)
                if sid:
                    db.session.add(
                        SubjectGroupLeaderAssignment(
                            teacher_id=teacher.id,
                            subject_id=sid,
                            academic_year=academic_year,
                        )
                    )

            # 备课组长
            pgl_str = row.get("备课组长分配", "")
            for item in split_str(pgl_str):
                y_match = re.search(r"(\d+)级?", item)
                if y_match:
                    y_str = y_match.group(1)
                    entry_year = int(y_str) if len(y_str) == 4 else 2000 + int(y_str)
                    sub_name = item.replace(
                        y_match.group(0), ""
                    ).strip()  # 去掉年份即为科目
                    sid = subject_map.get(sub_name)

                    if entry_year and sid:
                        db.session.add(
                            PrepGroupLeaderAssignment(
                                teacher_id=teacher.id,
                                entry_year=entry_year,
                                subject_id=sid,
                                academic_year=academic_year,
                            )
                        )

        db.session.commit()
        return jsonify(
            {
                "msg": f"处理完成。新增教师 {added_count} 人，更新 {updated_count} 人。行政职务已更新至 {academic_year} 学年。"
            }
        )

    except Exception as e:
        db.session.rollback()
        import traceback

        traceback.print_exc()
        return jsonify({"msg": f"导入失败: {str(e)}"}), 500


# --- 考试发布管理 ---
@admin_bp.route("/exam_tasks", methods=["GET"])
def get_exam_tasks():
    # 支持筛选
    entry_year = request.args.get("entry_year", type=int)
    subject_id = request.args.get("subject_id", type=int)
    # [新增] 支持按学年筛选
    academic_year = request.args.get("academic_year", type=int)

    query = ExamTask.query
    if entry_year:
        query = query.filter_by(entry_year=entry_year)
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    if academic_year:
        query = query.filter_by(academic_year=academic_year)

    tasks = query.order_by(ExamTask.create_time.desc()).all()

    return jsonify(
        [
            {
                "id": t.id,
                "name": t.name,
                "entry_year": t.entry_year,
                "grade_name": t.grade_name,
                "subject_id": t.subject_id,
                "subject_name": t.subject.name if t.subject else "-",
                "full_score": t.full_score,
                "is_active": t.is_active,
                "academic_year": t.academic_year,  # [新增] 返回学年信息
            }
            for t in tasks
        ]
    )


@admin_bp.route("/exam_tasks", methods=["POST"])
def add_exam_task():
    data = request.get_json()

    # 简单的防重复：同学年、同年级、同科目、同名
    # [修改] 增加 academic_year 的校验维度
    academic_year = data.get("academic_year", datetime.now().year)

    exists = ExamTask.query.filter_by(
        academic_year=academic_year,
        entry_year=data["entry_year"],
        subject_id=data["subject_id"],
        name=data["name"],
    ).first()

    if exists:
        return jsonify({"msg": "该学年的此考试任务已存在"}), 400

    new_task = ExamTask(
        name=data["name"],
        entry_year=data["entry_year"],
        subject_id=data["subject_id"],
        academic_year=academic_year,  # [新增] 保存学年
        full_score=data.get("full_score", 100),
        is_active=data.get("is_active", True),
    )
    db.session.add(new_task)
    db.session.commit()
    return jsonify({"msg": "发布成功"})


@admin_bp.route("/exam_tasks/<int:id>", methods=["PUT"])
def update_exam_task(id):
    task = ExamTask.query.get(id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404

    data = request.get_json()
    if "full_score" in data:
        task.full_score = data["full_score"]
    if "is_active" in data:
        task.is_active = data["is_active"]
    if "name" in data:
        task.name = data["name"]

    db.session.commit()
    return jsonify({"msg": "更新成功"})


@admin_bp.route("/exam_tasks/<int:id>", methods=["DELETE"])
def delete_exam_task(id):
    task = ExamTask.query.get(id)
    if not task:
        return jsonify({"msg": "任务不存在"}), 404

    try:
        # 1. 关键步骤：先删除该任务下所有已登记的成绩
        # 这样避免了外键约束冲突，同时也清理了旧数据
        Score.query.filter_by(exam_task_id=id).delete()

        # 2. 成绩清理完毕后，再删除任务本身
        db.session.delete(task)
        db.session.commit()

        return jsonify({"msg": "删除成功，相关成绩记录已同步清理"})

    except Exception as e:
        # 发生任何错误时回滚，保证数据一致性
        db.session.rollback()
        return jsonify({"msg": f"删除失败: {str(e)}"}), 500


# [在 app/routes/admin.py 中添加]


# --- 8. 批量导入任课信息 (新增功能) ---
@admin_bp.route("/assignments/import", methods=["POST"])
def import_course_assignments():
    if "file" not in request.files:
        return jsonify({"msg": "没有上传文件"}), 400

    file = request.files["file"]
    academic_year = request.form.get("academic_year", type=int)
    if not academic_year:
        return jsonify({"msg": "请选择导入的学年"}), 400

    try:
        df = pd.read_excel(file).fillna("")
    except Exception as e:
        return jsonify({"msg": f"Excel读取失败: {str(e)}"}), 400

    # --- 定义合法年级范围 (初一至初三) ---
    # 例如 2025学年，合法班级为 2025级、2024级、2023级
    valid_years = [academic_year, academic_year - 1, academic_year - 2]
    valid_years_str = "/".join([f"{y}级" for y in valid_years])

    # 1. 预加载映射
    all_teachers = Teacher.query.all()
    teacher_map = {t.name: t.id for t in all_teachers}

    all_subjects = Subject.query.all()
    subject_map = {s.name: s.id for s in all_subjects}

    # 班级映射 (用于后续写入)
    all_classes = ClassInfo.query.all()
    class_map = {}
    for c in all_classes:
        short_year = str(c.entry_year)[-2:]
        class_num_str = str(c.class_num).zfill(2)
        key = f"{short_year}级({class_num_str})班"
        class_map[key] = c.id

    # 正则用于解析 "23级(01)班"
    class_pattern = re.compile(r"(\d+)级\((\d+)\)班")

    # --- 阶段一：严格数据校验 (不操作数据库) ---
    errors = []
    missing_teachers = set()

    for index, row in df.iterrows():
        row_num = index + 2
        class_name = str(row.get("班级名称", "")).strip()

        if not class_name:
            continue

        # A. 校验班级是否存在于系统
        if class_name not in class_map:
            # 尝试解析一下看是不是年份不对
            match = class_pattern.match(class_name)
            if match:
                y_str = match.group(1)
                # 补全年份 23 -> 2023
                entry_year = int(y_str) if len(y_str) == 4 else 2000 + int(y_str)

                # 核心校验：检查年份是否合法
                if entry_year not in valid_years:
                    errors.append(
                        f"行{row_num}: 班级【{class_name}】的年份在 {academic_year} 学年无效。合法范围: {valid_years_str}"
                    )
                else:
                    # 年份合法但系统没这班，提示去创建
                    errors.append(
                        f"行{row_num}: 系统中找不到班级【{class_name}】，请先在班级管理中创建"
                    )
            else:
                errors.append(
                    f"行{row_num}: 班级名格式错误【{class_name}】，应为如 '23级(01)班'"
                )
            continue

        # B. 如果班级存在，也要反向检查它的年份是否符合当前学年逻辑
        # (防止用户把 2021级的班强行导入到 2025学年)
        cls_obj = ClassInfo.query.get(class_map[class_name])
        if cls_obj and cls_obj.entry_year not in valid_years:
            errors.append(
                f"行{row_num}: 班级【{class_name}】是 {cls_obj.entry_year}级，不属于 {academic_year} 学年的初中范围 ({valid_years_str})"
            )

        # C. 校验老师是否存在
        for col_name in df.columns:
            cell_value = str(row[col_name]).strip()
            if not cell_value:
                continue

            if col_name == "班主任" or col_name in subject_map:
                # 支持多个老师用逗号分隔的情况吗？目前代码逻辑看似是单个
                # 这里假设 Excel 里填的是单个老师姓名
                if cell_value not in teacher_map:
                    missing_teachers.add(cell_value)

    # 汇总错误
    if missing_teachers:
        # 只显示前5个
        t_list = list(missing_teachers)[:5]
        msg = f"系统不存在以下教师: {', '.join(t_list)}"
        if len(missing_teachers) > 5:
            msg += "..."
        errors.append(msg)

    if errors:
        # 格式化错误信息返回
        error_html = "<br>".join(errors[:8])
        if len(errors) > 8:
            error_html += f"<br>... 等共 {len(errors)} 处问题"
        return jsonify({"msg": f"校验失败，请修正后重试：<br>{error_html}"}), 400

    # --- 阶段二：校验通过，执行写入 ---
    try:
        # A. 清空该学年的旧数据
        db.session.query(CourseAssignment).filter_by(
            academic_year=academic_year
        ).delete()
        db.session.query(HeadTeacherAssignment).filter_by(
            academic_year=academic_year
        ).delete()

        count = 0

        for index, row in df.iterrows():
            class_name = str(row.get("班级名称", "")).strip()
            if not class_name or class_name not in class_map:
                continue
            class_id = class_map[class_name]

            # B. 遍历列
            for col_name in df.columns:
                teacher_name = str(row[col_name]).strip()
                if not teacher_name:
                    continue

                # 插入班主任
                if col_name == "班主任":
                    teacher_id = teacher_map.get(teacher_name)
                    if teacher_id:
                        db.session.add(
                            HeadTeacherAssignment(
                                teacher_id=teacher_id,
                                class_id=class_id,
                                academic_year=academic_year,
                            )
                        )

                # 插入任课
                elif col_name in subject_map:
                    teacher_id = teacher_map.get(teacher_name)
                    subject_id = subject_map[col_name]
                    if teacher_id:
                        db.session.add(
                            CourseAssignment(
                                teacher_id=teacher_id,
                                class_id=class_id,
                                subject_id=subject_id,
                                academic_year=academic_year,
                            )
                        )

            count += 1

        db.session.commit()
        return jsonify(
            {
                "msg": f"导入成功！已更新 {academic_year} 学年 {count} 个班级的任课与班主任信息。"
            }
        )

    except Exception as e:
        db.session.rollback()
        import traceback

        traceback.print_exc()
        return jsonify({"msg": f"数据库写入错误: {str(e)}"}), 500


@admin_bp.route("/assignments/export", methods=["GET"])
def export_course_assignments():
    # 1. 准备基础数据：班级按年级班号排序，科目按ID排序
    classes = ClassInfo.query.order_by(
        ClassInfo.entry_year.desc(), ClassInfo.class_num.asc()
    ).all()
    subjects = Subject.query.order_by(Subject.id).all()

    if not classes:
        return jsonify({"msg": "暂无班级数据，请先在班级管理中创建班级"}), 400

    # 2. 预查询现有数据（为了填充备份）
    # 获取所有班主任分配: { class_id: teacher_name }
    ht_assigns = HeadTeacherAssignment.query.all()
    ht_map = {ht.class_id: ht.teacher.name for ht in ht_assigns if ht.teacher}

    # 获取所有科任分配: { (class_id, subject_id): teacher_name }
    course_assigns = CourseAssignment.query.all()
    ca_map = {
        (ca.class_id, ca.subject_id): ca.teacher.name
        for ca in course_assigns
        if ca.teacher
    }

    # 3. 构建 Excel 数据行
    data_list = []

    for cls in classes:
        # 构造标准的班级名称格式，如 "23级(01)班"
        # 确保这个格式与导入功能的解析正则 r"(\d+)级\((\d+)\)班" 完美匹配
        short_year = str(cls.entry_year)[-2:]
        class_num_str = str(cls.class_num).zfill(2)
        class_name_str = f"{short_year}级({class_num_str})班"

        row = {
            "班级名称": class_name_str,
            "人数": cls.students.count(),  # 顺便导出人数供参考（导入时会自动忽略此列）
            "班主任": ht_map.get(cls.id, ""),  # 如果没数据就是空字符串（即空模板）
        }

        # 动态填充每一科的老师
        for sub in subjects:
            # 尝试获取该班该科的老师，没有则是空
            row[sub.name] = ca_map.get((cls.id, sub.id), "")

        data_list.append(row)

    # 4. 生成 DataFrame
    df = pd.DataFrame(data_list)

    # 强制设定列顺序：班级名称 -> 人数 -> 班主任 -> 语文 -> 数学 ...
    # 这样生成的模板非常直观
    column_order = ["班级名称", "人数", "班主任"] + [s.name for s in subjects]

    # 防止因数据为空导致列丢失，重新索引
    df = df.reindex(columns=column_order)

    # 5. 写入内存并返回
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="任课总表")

    output.seek(0)

    # 文件名加时间戳或简单命名均可
    filename = "任课分配表(导入模板_备份).xlsx"
    from urllib.parse import quote

    filename = quote(filename)  # 处理中文文件名

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


# --- 9. 导出教师信息 Excel---
@admin_bp.route("/teachers/export", methods=["GET"])
def export_teachers():
    # 1. 查询所有教师数据，预加载关联数据以提升性能
    teachers = Teacher.query.all()

    # 定义导出列头 (与导入模板保持一致)
    columns = [
        "工号",
        "姓名",
        "性别",
        "电话",
        "职称",
        "班主任分配",
        "级长分配",
        "科组长分配",
        "备课组长分配",
        "任教分配",
    ]

    data_list = []

    # 2. 遍历教师，构造数据行
    for t in teachers:
        # 获取关联的账号信息 (工号)
        user = User.query.get(t.user_id)
        username = user.username if user else ""

        # A. 格式化班主任分配: "23级(01)班, 23级(02)班"
        ht_list = [
            h.class_info.full_name for h in t.head_teacher_assigns if h.class_info
        ]
        ht_str = "，".join(ht_list)

        # B. 格式化级长分配: "2023级, 2024级"
        gl_list = [f"{g.entry_year}级" for g in t.grade_leader_assigns]
        gl_str = "，".join(gl_list)

        # C. 格式化科组长分配: "语文, 数学"
        sgl_list = [s.subject.name for s in t.subject_group_assigns if s.subject]
        sgl_str = "，".join(sgl_list)

        # D. 格式化备课组长分配: "2023级语文, 2024级数学"
        pgl_list = []
        for p in t.prep_group_assigns:
            if p.subject:
                pgl_list.append(f"{p.entry_year}级{p.subject.name}")
        pgl_str = "，".join(pgl_list)

        # E. 格式化任教分配: "23级(01)班-语文, 23级(02)班-数学"
        course_list = []
        for c in t.course_assignments:
            if c.class_info and c.subject:
                # 组合格式需与导入解析逻辑 split('-') 匹配
                course_list.append(f"{c.class_info.full_name}-{c.subject.name}")
        course_str = "，".join(course_list)

        data_list.append(
            {
                "工号": username,
                "姓名": t.name,
                "性别": t.gender,
                "电话": t.phone,
                "职称": t.job_title,
                "班主任分配": ht_str,
                "级长分配": gl_str,
                "科组长分配": sgl_str,
                "备课组长分配": pgl_str,
                "任教分配": course_str,
            }
        )

    # 3. 生成 DataFrame
    df = pd.DataFrame(data_list, columns=columns)

    # 如果没有数据，pandas 也会生成一个只有表头的空文件，正好作为模板

    # 4. 写入内存并返回
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="教师信息表")

    output.seek(0)

    filename = "教师信息表(模板_备份).xlsx"
    from urllib.parse import quote

    filename = quote(filename)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


@admin_bp.route("/students/<int:student_id>/certificate", methods=["GET"])
def generate_certificate(student_id):
    # 1. 查询数据
    student = Student.query.get(student_id)
    if not student:
        return jsonify({"msg": "学生不存在"}), 404

    # 2. 数据处理
    # 班级信息处理
    entry_year = "____"
    class_num = "__"
    if student.current_class_rel:
        entry_year = str(student.current_class_rel.entry_year)
        class_num = str(student.current_class_rel.class_num)

    # 学籍号处理：优先显示市学籍号，没有则显示国家学籍号，都没有显示暂无
    school_id = student.city_school_id or student.national_school_id or "暂无数据"

    # 身份证处理
    id_card = student.id_card_number or "暂无数据"

    # 获取当前日期
    now = datetime.now()

    # 3. 构建模板上下文 (Context)
    # 这里的 key 必须和 Word 模板里的 {{ key }} 一一对应
    context = {
        "name": student.name,
        "gender": student.gender,
        "entry_year": entry_year,  # 入学年份，如 2025
        "class_num": class_num,  # 班号，如 3
        "status": student.status,  # 在读
        "school_id": school_id,  # 学籍号
        "id_card": id_card,  # 身份证
        "year": now.year,  # 年
        "month": now.month,  # 月
        "day": now.day,  # 日
    }

    # 4. 加载模板
    # 假设模板放在后端项目根目录下
    template_name = "certificate_template.docx"
    # 获取绝对路径，防止路径错误
    import sys

    if getattr(sys, "frozen", False):
        # 如果是打包后的 exe 环境
        root_dir = os.path.dirname(sys.executable)
    else:
        # 开发环境
        root_dir = os.path.abspath(
            os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "..")
        )

    template_path = os.path.join(root_dir, template_name)

    if not os.path.exists(template_path):
        print(f"模板未找到: {template_path}")
        return (
            jsonify({"msg": "服务器端缺少证书模板文件(certificate_template.docx)"}),
            500,
        )

    try:
        tpl = DocxTemplate(template_path)
        tpl.render(context)

        # 5. 写入内存
        file_stream = io.BytesIO()
        tpl.save(file_stream)
        file_stream.seek(0)

        # 6. 生成文件名
        filename = f"{student.name}_学籍证明.docx"
        from urllib.parse import quote

        filename = quote(filename)

        return send_file(
            file_stream,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        print(f"生成错误: {str(e)}")
        return jsonify({"msg": f"生成证明文件失败: {str(e)}"}), 500


@admin_bp.route("/stats/class_score_stats", methods=["POST"])
def get_class_score_stats():
    data = request.get_json()
    entry_year = data.get("entry_year")
    exam_name = data.get("exam_name")
    subject_ids = data.get("subject_ids", [])

    # 获取阈值设置 (前端传百分比整数，如 85，需转换为 0.85)
    # 默认值：优秀 85%, 合格 60%, 低分 30%
    th_exc = data.get("threshold_excellent", 85) / 100.0
    th_pass = data.get("threshold_pass", 60) / 100.0
    th_low = data.get("threshold_low", 30) / 100.0

    if not entry_year or not exam_name or not subject_ids:
        return jsonify({"msg": "请选择完整的筛选条件"}), 400

    # 1. 获取符合条件的考试任务 (用于确定满分值和关联的科目)
    tasks = ExamTask.query.filter(
        ExamTask.entry_year == entry_year,
        ExamTask.name == exam_name,
        ExamTask.subject_id.in_(subject_ids),
    ).all()

    if not tasks:
        return jsonify([])

    # 计算所选科目的满分总和
    full_score_sum = sum(t.full_score for t in tasks)
    task_ids = [t.id for t in tasks]

    # 获取涉及的科目名称 (去重并排序)
    subject_names = sorted(list(set([t.subject.name for t in tasks])))
    subjects_display = "、".join(subject_names)

    # 2. 获取该年级所有班级
    classes = (
        ClassInfo.query.filter_by(entry_year=entry_year)
        .order_by(ClassInfo.class_num)
        .all()
    )
    class_ids = [c.id for c in classes]

    # 3. 获取所有相关学生 (状态为在读)
    students = Student.query.filter(
        Student.class_id.in_(class_ids), Student.status == "在读"
    ).all()
    student_class_map = {s.id: s.class_id for s in students}

    # 4. 获取所有相关成绩
    scores = Score.query.filter(
        Score.exam_task_id.in_(task_ids), Score.student_id.in_([s.id for s in students])
    ).all()

    # --- 数据处理 ---
    # 结构: student_id -> { total: 0, valid_subjects: 0 }
    student_stats = {s.id: {"total": 0, "valid_subjects": 0} for s in students}

    for sc in scores:
        sid = sc.student_id
        if sid in student_stats:
            # 只有非"缺考"才计入有效科目数和总分
            # 注意：如果您的需求是"缺考算0分但不算缺考人数"，逻辑需微调
            # 这里按照通常逻辑：有分数的才算"考试人数"
            if sc.remark != "缺考":
                student_stats[sid]["total"] += sc.score
                student_stats[sid]["valid_subjects"] += 1
            else:
                # 缺考时，总分加0，valid_subjects 不加
                pass

    # 计算级平均分 (仅基于"考试人数"，即至少有一科有效成绩的学生)
    grade_total_score = 0
    grade_exam_count = 0

    # 筛选出有效考生数据 (valid_subjects > 0)
    valid_student_data = []
    for sid, stat in student_stats.items():
        if stat["valid_subjects"] > 0:
            grade_total_score += stat["total"]
            grade_exam_count += 1
            valid_student_data.append(
                {"class_id": student_class_map[sid], "total": stat["total"]}
            )

    grade_avg = grade_total_score / grade_exam_count if grade_exam_count > 0 else 0

    # 5. 按班级聚合统计
    result = []

    for cls in classes:
        # 获取本班的所有学生ID
        cls_student_ids = [s.id for s in cls.students if s.status == "在读"]
        total_people = len(cls_student_ids)

        # 获取本班的"有效考生"数据
        cls_valid_data = [d for d in valid_student_data if d["class_id"] == cls.id]
        cls_exam_scores = [d["total"] for d in cls_valid_data]
        exam_people = len(cls_exam_scores)

        # 初始化统计数据
        cls_sum = sum(cls_exam_scores)
        cls_avg = cls_sum / exam_people if exam_people > 0 else 0
        cls_max = max(cls_exam_scores) if exam_people > 0 else 0
        cls_min = min(cls_exam_scores) if exam_people > 0 else 0

        # 阈值统计
        # 优秀: >= 满分 * 85%
        cnt_exc = sum(1 for s in cls_exam_scores if s >= full_score_sum * th_exc)
        # 合格: >= 满分 * 60%
        cnt_pass = sum(1 for s in cls_exam_scores if s >= full_score_sum * th_pass)
        # 低分: <= 满分 * 30%
        cnt_low = sum(1 for s in cls_exam_scores if s <= full_score_sum * th_low)
        # 不合格: < 合格线 (即 总人数 - 合格人数，或者严格小于)
        # 这里使用严格小于逻辑：
        cnt_fail = sum(1 for s in cls_exam_scores if s < full_score_sum * th_pass)

        # 计算与级比率 (班均 / 级均)
        ratio = (cls_avg / grade_avg * 100) if grade_avg > 0 else 0

        def calc_rate(cnt, total):
            return round(cnt / total * 100, 1) if total > 0 else 0

        result.append(
            {
                "class_name": cls.full_name,
                "subjects": subjects_display,
                "full_score": full_score_sum,
                "total_people": total_people,
                "exam_people": exam_people,
                "excellent_count": cnt_exc,
                "excellent_rate": calc_rate(cnt_exc, exam_people),
                "pass_count": cnt_pass,
                "pass_rate": calc_rate(cnt_pass, exam_people),
                "fail_count": cnt_fail,
                "fail_rate": calc_rate(cnt_fail, exam_people),
                "low_count": cnt_low,
                "low_rate": calc_rate(cnt_low, exam_people),
                "max_score": cls_max,
                "min_score": cls_min,
                "sum_score": cls_sum,
                "avg_score": round(cls_avg, 1),
                "grade_ratio": round(ratio, 1),
            }
        )

    return jsonify(result)


@admin_bp.route("/stats/teacher_score_stats", methods=["POST"])
def get_teacher_score_stats():
    data = request.get_json()
    entry_year = data.get("entry_year")  # 必填：年级 (如 2023)
    academic_year = data.get("academic_year")  # 必填：学年 (如 2024)
    exam_name = data.get("exam_name")  # 必填：考试名称

    # 阈值 (百分比整数，如 85)
    th_exc_rate = data.get("threshold_excellent", 85) / 100.0
    th_pass_rate = data.get("threshold_pass", 60) / 100.0

    if not entry_year or not academic_year or not exam_name:
        return jsonify({"msg": "请选择完整的筛选条件"}), 400

    # 1. 获取该年级下的所有科目 (按预定义顺序)
    #    为了保证输出顺序，我们遍历所有科目，逐一查询
    all_subjects = Subject.query.order_by(Subject.id).all()

    final_result = []

    # 缓存班级信息 {class_id: class_obj}
    classes = ClassInfo.query.filter_by(entry_year=entry_year).all()
    class_map = {c.id: c for c in classes}
    if not classes:
        return jsonify([])

    grade_class_ids = [c.id for c in classes]

    for sub in all_subjects:
        # 2. 查找该科目的考试任务
        task = ExamTask.query.filter_by(
            entry_year=entry_year,
            academic_year=academic_year,
            subject_id=sub.id,
            name=exam_name,
        ).first()

        if not task:
            continue  # 该科目没有考这场试，跳过

        full_score = task.full_score

        # 3. 获取该科目、该学年、该年级的所有任课分配
        #    注意：CourseAssignment 关联的是 class_id，我们要过滤出属于 entry_year 的班级
        assignments = (
            db.session.query(CourseAssignment)
            .join(ClassInfo)
            .filter(
                CourseAssignment.subject_id == sub.id,
                CourseAssignment.academic_year == academic_year,
                ClassInfo.entry_year == entry_year,
            )
            .all()
        )

        if not assignments:
            # 如果没人任课但有考试任务，可能也需要显示年级总分？
            # 这里简单处理：如果没有任课信息，暂不显示该科统计（或者只显示一行总计）
            pass

        # 4. 按教师聚合班级
        #    结构: { teacher_id: { 'teacher': teacher_obj, 'class_ids': [id1, id2] } }
        teacher_map = {}
        for assign in assignments:
            tid = assign.teacher_id
            if tid not in teacher_map:
                teacher_map[tid] = {
                    "teacher": assign.teacher,
                    "class_ids": [],
                    "class_names": [],
                }
            teacher_map[tid]["class_ids"].append(assign.class_id)
            # 班级名简写，如 (01)班
            c_obj = class_map.get(assign.class_id)
            if c_obj:
                teacher_map[tid]["class_names"].append(f"({c_obj.class_num})班")

        # 5. 获取该科目本次考试的所有成绩
        #    为了性能，一次性拉取该任务所有成绩
        all_scores = Score.query.filter(Score.exam_task_id == task.id).all()

        # 构建 { student_id: score_val } 映射，过滤缺考
        # 注意：这里需要知道学生属于哪个班，以便归属到老师
        #       Score 表里有 class_id_snapshot，或者是通过 student.class_id
        #       严谨做法是：学生当前班级必须在老师任教班级里。

        # 先获取该年级所有在读学生
        students = Student.query.filter(
            Student.class_id.in_(grade_class_ids), Student.status == "在读"
        ).all()

        student_cls_map = {s.id: s.class_id for s in students}

        # 筛选有效成绩
        # valid_scores_map: { student_id: score }
        valid_scores_map = {}
        for sc in all_scores:
            if sc.student_id in student_cls_map and sc.remark != "缺考":
                valid_scores_map[sc.student_id] = sc.score

        # --- 计算年级总数据 (Grade Total) ---
        # 统计该年级所有班级的学生（不管有没有老师教）
        grade_total_students = len(students)  # 年级总人数
        grade_exam_scores = []
        for sid in student_cls_map:
            if sid in valid_scores_map:
                grade_exam_scores.append(valid_scores_map[sid])

        grade_exam_count = len(grade_exam_scores)
        grade_sum = sum(grade_exam_scores)
        grade_avg = grade_sum / grade_exam_count if grade_exam_count > 0 else 0

        # 辅助计算函数
        def calc_stats(score_list, total_stu_count):
            count = len(score_list)
            if count == 0:
                # [修正点] 这里之前写了6个0，必须改为5个，否则解包报错
                return 0, 0, 0, 0, 0

            exc_cnt = sum(1 for s in score_list if s >= full_score * th_exc_rate)
            pass_cnt = sum(1 for s in score_list if s >= full_score * th_pass_rate)
            avg = sum(score_list) / count

            return (
                exc_cnt,
                round(exc_cnt / count * 100, 1),
                pass_cnt,
                round(pass_cnt / count * 100, 1),
                round(avg, 2),
            )

        # 6. 计算每位老师的数据
        teacher_rows = []
        for tid, t_data in teacher_map.items():
            t_class_ids = set(t_data["class_ids"])
            # 找出属于这些班级的学生
            t_stu_ids = [
                sid for sid, cid in student_cls_map.items() if cid in t_class_ids
            ]
            t_total_people = len(t_stu_ids)

            # 找出这些学生的成绩
            t_scores = [
                valid_scores_map[sid] for sid in t_stu_ids if sid in valid_scores_map
            ]
            t_exam_people = len(t_scores)

            exc_n, exc_r, pass_n, pass_r, t_avg = calc_stats(t_scores, t_total_people)

            # 班级名排序并拼接
            t_data["class_names"].sort()
            # 加上年级前缀，如 2023级(1)班, (2)班 -> 简略显示
            # 或者完整显示：2023级(1)班，2023级(2)班
            # 需求说：使用中文逗号分隔
            full_class_names = [f"{entry_year}级{n}" for n in t_data["class_names"]]

            teacher_rows.append(
                {
                    "name": t_data["teacher"].name,
                    "academic_year": f"{academic_year}学年",
                    "subject": sub.name,
                    "exam_name": exam_name,
                    "full_score": full_score,
                    "classes": "，".join(full_class_names),
                    "total_people": t_total_people,
                    "exam_people": t_exam_people,
                    "excellent_count": exc_n,
                    "excellent_rate": exc_r,
                    "pass_count": pass_n,
                    "pass_rate": pass_r,
                    "avg_score": t_avg,
                    "grade_ratio": round(t_avg / grade_avg, 2) if grade_avg > 0 else 0,
                    "_sort_key": t_avg,  # 用于排序
                }
            )

        # 7. 组内排序：按平均分降序
        teacher_rows.sort(key=lambda x: x["_sort_key"], reverse=True)

        # 8. 填充排名 (Rank)
        for i, row in enumerate(teacher_rows):
            row["rank"] = i + 1

        # 9. 构建年级总计行
        g_exc_n, g_exc_r, g_pass_n, g_pass_r, g_avg_res = calc_stats(
            grade_exam_scores, grade_total_students
        )

        total_row = {
            "name": f"{entry_year}级{sub.name}总计",
            "academic_year": f"{academic_year}学年",
            "subject": sub.name,
            "exam_name": exam_name,
            "full_score": full_score,
            "classes": "全年级",
            "total_people": grade_total_students,
            "exam_people": grade_exam_count,
            "excellent_count": g_exc_n,
            "excellent_rate": g_exc_r,
            "pass_count": g_pass_n,
            "pass_rate": g_pass_r,
            "avg_score": round(g_avg_res, 2),  # 重新保留2位
            "grade_ratio": 1.0,
            "rank": "-",
        }

        # 10. 合并到最终结果
        final_result.extend(teacher_rows)
        # 如果有数据，才加总计行
        if teacher_rows or grade_exam_count > 0:
            final_result.append(total_row)

    return jsonify(final_result)


@admin_bp.route("/stats/score_template", methods=["POST"])
def get_score_import_template():
    """
    功能A & B: 动态模版下载 / 备份导出
    接收: entry_year(必填), class_ids(列表), subject_ids(列表), exam_name(选填, 若填则为备份模式)
    """
    data = request.get_json()
    entry_year = data.get("entry_year")
    class_ids = data.get("class_ids", [])
    subject_ids = data.get("subject_ids", [])
    exam_name = data.get("exam_name")  # 如果有值，则是备份导出；为空则是空模版

    if not entry_year or not subject_ids:
        return jsonify({"msg": "请至少选择年级和统计科目"}), 400

    # 1. 获取科目名称 (作为动态表头)
    subjects = (
        Subject.query.filter(Subject.id.in_(subject_ids)).order_by(Subject.id).all()
    )
    subject_names = [s.name for s in subjects]

    # 2. 获取班级 (若前端未选班级，默认全级)
    query_cls = ClassInfo.query.filter_by(entry_year=entry_year)
    if class_ids:
        query_cls = query_cls.filter(ClassInfo.id.in_(class_ids))
    classes = query_cls.order_by(ClassInfo.class_num).all()
    target_class_ids = [c.id for c in classes]

    # 3. 获取学生
    students = (
        Student.query.filter(
            Student.class_id.in_(target_class_ids), Student.status == "在读"
        )
        .order_by(Student.class_id, Student.student_id)
        .all()
    )

    # 4. 如果是备份模式，预取成绩
    score_map = {}  # {(student_id, subject_name): score_val}
    if exam_name:
        # 找到对应的考试任务IDs
        tasks = ExamTask.query.filter(
            ExamTask.entry_year == entry_year,
            ExamTask.name == exam_name,
            ExamTask.subject_id.in_(subject_ids),
        ).all()
        task_ids = [t.id for t in tasks]
        task_subj_map = {t.id: t.subject.name for t in tasks}  # task_id -> subject_name

        scores = Score.query.filter(
            Score.exam_task_id.in_(task_ids),
            Score.student_id.in_([s.id for s in students]),
        ).all()

        for sc in scores:
            s_name = task_subj_map.get(sc.exam_task_id)
            val = "缺考" if sc.remark == "缺考" else sc.score
            score_map[(sc.student_id, s_name)] = val

    # 5. 构建 DataFrame
    data_list = []
    for s in students:
        # 格式化班级名
        c = s.current_class_rel
        class_name_str = f"{str(c.entry_year)[-2:]}级({str(c.class_num).zfill(2)})班"

        row = {"学号": s.student_id, "姓名": s.name, "班级名称": class_name_str}

        # 填充科目列
        for sub_name in subject_names:
            if exam_name:
                # 备份模式：填入成绩
                row[sub_name] = score_map.get((s.id, sub_name), "")
            else:
                # 模版模式：留空
                row[sub_name] = ""

        data_list.append(row)

    df = pd.DataFrame(data_list)

    # 确保列顺序
    cols = ["学号", "姓名", "班级名称"] + subject_names
    df = df.reindex(columns=cols)

    # 6. 导出
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        sheet_name = "成绩备份" if exam_name else "录入模版"
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    output.seek(0)

    filename = f"{entry_year}级_{exam_name or '导入模版'}_成绩数据.xlsx"
    from urllib.parse import quote

    filename = quote(filename)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


@admin_bp.route("/stats/import_scores", methods=["POST"])
def import_admin_scores():
    """
    功能C: 严格模式导入 (原子性事务)
    Step 1: 检查考试任务发布
    Step 2: 严格表头校验
    Step 3: 白名单过滤 (记录警告)
    Step 4: 身份三维匹配 (记录致命错误)
    Step 5: 写入或回滚
    """
    if "file" not in request.files:
        return jsonify({"msg": "未上传文件"}), 400

    file = request.files["file"]
    entry_year = request.form.get("entry_year", type=int)
    exam_name = request.form.get("exam_name")

    # 接收 JSON 字符串并解析
    import json

    try:
        subject_ids = json.loads(request.form.get("subject_ids", "[]"))
        class_ids = json.loads(request.form.get("class_ids", "[]"))
    except:
        return jsonify({"msg": "参数解析错误"}), 400

    if not entry_year or not exam_name or not subject_ids:
        return jsonify({"msg": "必要参数缺失(年级/考试/科目)"}), 400

    logs = {
        "fatal_errors": [],  # 阻断性错误
        "warnings": [],  # 冗余/非阻断警告
        "missing_students": [],  # 缺失名单
    }

    try:
        df = pd.read_excel(file).fillna("")
    except Exception as e:
        return jsonify({"msg": f"Excel读取失败: {str(e)}"}), 400

    # --- Step 1: 检查考试任务发布状态 ---
    # 必须所有选中的科目都发布了该考试
    selected_subjects = Subject.query.filter(Subject.id.in_(subject_ids)).all()
    subject_map = {s.name: s.id for s in selected_subjects}  # "语文": 1
    selected_subject_names = set(subject_map.keys())

    # 查找任务
    tasks = ExamTask.query.filter(
        ExamTask.entry_year == entry_year,
        ExamTask.name == exam_name,
        ExamTask.subject_id.in_(subject_ids),
    ).all()

    # 检查是否每个选中的科目都有对应的任务
    existing_sub_ids = set(t.subject_id for t in tasks)
    missing_tasks = []
    task_map = {}  # subject_name -> task_obj

    for s in selected_subjects:
        if s.id not in existing_sub_ids:
            missing_tasks.append(s.name)
        else:
            # 找到对应任务
            t = next(x for x in tasks if x.subject_id == s.id)
            task_map[s.name] = t

    if missing_tasks:
        return (
            jsonify(
                {
                    "msg": f"无法导入：科目 {missing_tasks} 尚未发布【{exam_name}】考试任务，请先去发布。"
                }
            ),
            400,
        )

    # --- Step 2 & 3: 表头校验与白名单过滤 ---
    excel_cols = set(df.columns)
    base_cols = {"学号", "姓名", "班级名称"}

    # 2.1 检查必要的基础列
    if not base_cols.issubset(excel_cols):
        missing = base_cols - excel_cols
        return jsonify({"msg": f"Excel缺少基础列: {missing}"}), 400

    # 2.2 识别有效科目列 (在Excel中 且 在前端已选中)
    valid_subject_cols = []
    missing_subjects = selected_subject_names - excel_cols
    if missing_subjects:
        # 直接阻断，告诉用户缺了哪些科
        return (
            jsonify(
                {
                    "msg": f"Excel文件缺失以下选中科目的数据列：{', '.join(missing_subjects)}。请检查是否使用了错误的模版。"
                }
            ),
            400,
        )

    for col in df.columns:
        if col in selected_subject_names:
            valid_subject_cols.append(col)
        elif col not in base_cols:
            # Excel里有，但没选中的列 -> 警告
            logs["warnings"].append(f"检测到未选中的列【{col}】，已自动忽略。")

    if not valid_subject_cols:
        return jsonify({"msg": "Excel中没有找到任何与当前选中科目匹配的列"}), 400

    # --- 准备数据库比对数据 ---
    # 获取目标范围内的所有学生 (用于身份校验)
    # 如果 class_ids 为空，则校验该年级所有班级
    cls_query = ClassInfo.query.filter_by(entry_year=entry_year)
    if class_ids:
        cls_query = cls_query.filter(ClassInfo.id.in_(class_ids))
    target_classes = cls_query.all()
    target_class_ids = [c.id for c in target_classes]

    # 构建映射: full_class_name -> class_id
    class_name_map = {}
    for c in target_classes:
        name = f"{str(c.entry_year)[-2:]}级({str(c.class_num).zfill(2)})班"
        class_name_map[name] = c.id

    # 获取学生: {(student_id): {name:xx, class_id:xx, db_obj:xx}}
    db_students = Student.query.filter(
        Student.class_id.in_(target_class_ids), Student.status == "在读"
    ).all()

    student_map = {s.student_id: s for s in db_students}
    processed_ids = set()

    # --- Step 4: 遍历并进行身份三维匹配 (内存中校验) ---
    pending_scores = []  # 待写入的数据列表

    for index, row in df.iterrows():
        row_num = index + 2
        sid = str(row["学号"]).strip()
        name = str(row["姓名"]).strip()
        cname = str(row["班级名称"]).strip()

        if not sid:
            continue  # 空行

        # A. 班级过滤
        if cname not in class_name_map:
            # 如果这个班级不在目标范围内 (没选中 或者 名字不对)
            # 如果是名字不对，已经在 class_name_map 覆盖了标准名
            # 如果是没选中，这里视为“冗余行”，警告并跳过
            logs["warnings"].append(
                f"行{row_num}: 班级【{cname}】不在本次导入范围内，已忽略。"
            )
            continue

        target_cid = class_name_map[cname]

        # B. 身份三维匹配 (核心阻断逻辑)
        if sid not in student_map:
            logs["fatal_errors"].append(
                f"行{row_num}: 学号【{sid}】在系统中不存在 (或非在读/非选中班级)。"
            )
            continue

        stu_obj = student_map[sid]

        # 校验姓名
        if stu_obj.name != name:
            logs["fatal_errors"].append(
                f"行{row_num}: 学号【{sid}】对应的姓名应为【{stu_obj.name}】，Excel中为【{name}】。"
            )
            continue

        # 校验班级归属
        if stu_obj.class_id != target_cid:
            logs["fatal_errors"].append(
                f"行{row_num}: 学生【{name}】系统归属班级ID不匹配，请检查班级名称。"
            )
            continue

        processed_ids.add(sid)

        # C. 提取成绩 (暂存)
        for sub_name in valid_subject_cols:
            raw_val = row.get(sub_name)
            task = task_map[sub_name]  # 肯定存在，前面Step 1校验过

            # 处理空值和格式
            # if raw_val == "" or raw_val is None:
            #     continue  # 空值不录入，保留原样 (或者需求是覆盖为空?) 这里假设是不处理
            # [新增修改] 严格空值校验
            if pd.isna(raw_val) or str(raw_val).strip() == "":
                logs["fatal_errors"].append(
                    f"行{row_num}: 学生【{name}】缺失【{sub_name}】科目的成绩。"
                )
                continue  # 记了错就跳过当前科目，继续查下一科

            val_str = str(raw_val).strip()
            score_val = 0.0
            remark_val = ""

            if val_str == "缺考":
                score_val = 0.0
                remark_val = "缺考"
            else:
                try:
                    score_val = float(val_str)
                    if score_val < 0 or score_val > task.full_score:
                        logs["fatal_errors"].append(
                            f"行{row_num}: {sub_name}分数【{score_val}】超出满分【{task.full_score}】。"
                        )
                except:
                    logs["fatal_errors"].append(
                        f"行{row_num}: {sub_name}分数【{val_str}】格式错误。"
                    )

            # 加入待写入队列
            pending_scores.append(
                {
                    "student_id": stu_obj.id,
                    "exam_task_id": task.id,
                    "subject_id": task.subject_id,
                    "score": score_val,
                    "remark": remark_val,
                    "term": task.name,
                }
            )

    # --- Step 5: 决策 (原子性写入) ---

    # 5.1 如果有任何致命错误 -> 拒绝写入
    if logs["fatal_errors"]:
        return jsonify(
            {
                "status": "error",
                "msg": f"校验未通过，发现 {len(logs['fatal_errors'])} 个致命错误，数据未写入。",
                "logs": logs,
            }
        )

    # 5.2 统计缺失学生 (仅提示)
    all_target_ids = set(student_map.keys())
    missing = all_target_ids - processed_ids
    if missing:
        # 取前5个名字
        names = [student_map[m].name for m in list(missing)[:5]]
        msg = (
            f"共 {len(missing)} 名选中班级的学生未在Excel中找到 ({','.join(names)}...)"
        )
        logs["missing_students"].append(msg)

    # 5.3 执行数据库写入
    try:
        updated_count = 0
        added_count = 0

        # 预加载现有成绩以减少查询: {(student_id, task_id): score_obj}
        # 涉及到的所有任务
        relevant_task_ids = [task_map[n].id for n in valid_subject_cols]
        # 涉及到的所有学生
        relevant_stu_ids = [p["student_id"] for p in pending_scores]

        existing_scores = Score.query.filter(
            Score.exam_task_id.in_(relevant_task_ids),
            Score.student_id.in_(relevant_stu_ids),
        ).all()

        existing_map = {(es.student_id, es.exam_task_id): es for es in existing_scores}

        for item in pending_scores:
            key = (item["student_id"], item["exam_task_id"])
            if key in existing_map:
                # 更新
                sc = existing_map[key]
                if sc.score != item["score"] or sc.remark != item["remark"]:
                    sc.score = item["score"]
                    sc.remark = item["remark"]
                    updated_count += 1
            else:
                # 新增
                new_sc = Score(
                    student_id=item["student_id"],
                    subject_id=item["subject_id"],
                    exam_task_id=item["exam_task_id"],
                    score=item["score"],
                    remark=item["remark"],
                    term=item["term"],
                )
                db.session.add(new_sc)
                added_count += 1

        db.session.commit()

        return jsonify(
            {
                "status": "success",
                "msg": f"导入成功！新增 {added_count} 条，更新 {updated_count} 条成绩。",
                "logs": logs,
            }
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"数据库写入异常: {str(e)}"}), 500
