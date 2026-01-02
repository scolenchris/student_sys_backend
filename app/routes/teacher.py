from flask import Blueprint, request, jsonify, send_file
import pandas as pd
import io
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
        return jsonify([]), 200

    # 查询关联的班级和科目
    # 修改点：额外查询 academic_year，用于后续匹配考试任务
    assignments = (
        db.session.query(
            CourseAssignment.id,
            CourseAssignment.academic_year,
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

    valid_courses = []

    for a in assignments:
        # 核心过滤：检查该班级（年级+学年）在当前科目下，是否有“未锁定”的考试
        # 只有存在 is_active=True 的考试，才把这个班级返回给前端
        has_active_exam = (
            db.session.query(ExamTask.id)
            .filter_by(
                entry_year=a.entry_year,  # 匹配年级 (如2023级)
                subject_id=a.subject_id,  # 匹配科目
                academic_year=a.academic_year,  # 匹配学年 (如2025学年)
                is_active=True,  # 必须是开启状态
            )
            .first()
        )

        if has_active_exam:
            valid_courses.append(
                {
                    "assignment_id": a.id,
                    "class_id": a.class_id,
                    "grade_class": f"{a.entry_year}级({a.class_num})班",
                    "subject_name": a.subject_name,
                    "subject_id": a.subject_id,
                }
            )

    return jsonify(valid_courses)


# --- 2. 获取打分列表（学生名单 + 现有分数） ---
@teacher_bp.route("/score_list", methods=["GET"])
def get_score_list():
    class_id = request.args.get("class_id")
    exam_task_id = request.args.get("exam_task_id")

    if not exam_task_id:
        return jsonify([])

    students = Student.query.filter_by(class_id=class_id, status="在读").all()

    result = []
    for s in students:
        score_record = Score.query.filter_by(
            student_id=s.id, exam_task_id=exam_task_id
        ).first()

        # 默认显示逻辑
        display_val = None
        if score_record:
            # 如果备注是缺考，优先返回字符串 "缺考"
            if score_record.remark == "缺考":
                display_val = "缺考"
            else:
                display_val = score_record.score

        result.append(
            {
                "student_id": s.id,
                "student_no": s.student_id,
                "name": s.name,
                "score": display_val,  # 前端直接接收 "缺考" 或 数字
            }
        )

    return jsonify(result)


# --- 3. 保存成绩 ---
@teacher_bp.route("/save_scores", methods=["POST"])
def save_scores():
    data = request.get_json()
    exam_task_id = data.get("exam_task_id")
    scores_data = data.get("scores")  # [{"student_id": 1, "score": "缺考" 或 95}, ...]

    task = ExamTask.query.get(exam_task_id)
    if not task:
        return jsonify({"msg": "考试任务不存在"}), 404

    if not task.is_active:
        return jsonify({"msg": "该考试录入通道已关闭，无法保存"}), 403

    for item in scores_data:
        raw_val = item["score"]

        # 处理数值逻辑
        final_score = 0.0
        final_remark = ""

        # 允许前端传 null 或 空串
        if raw_val is None or raw_val == "":
            # 如果是空，根据需求可能是不录入，或者归零。这里假设不做修改或设为0
            # 简单起见，空值不更新，或者视为0
            continue

        if str(raw_val).strip() == "缺考":
            final_score = 0.0
            final_remark = "缺考"
        else:
            try:
                final_score = float(raw_val)
                final_remark = ""  # 正常分数清空备注
            except ValueError:
                continue  # 格式非法跳过

        existing_score = Score.query.filter_by(
            student_id=item["student_id"], exam_task_id=exam_task_id
        ).first()

        if existing_score:
            existing_score.score = final_score
            existing_score.remark = final_remark
        else:
            new_score = Score(
                student_id=item["student_id"],
                subject_id=task.subject_id,
                exam_task_id=exam_task_id,
                score=final_score,
                term=task.name,
                remark=final_remark,
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
        ExamTask.query.filter_by(
            entry_year=cls.entry_year, subject_id=subject_id, is_active=True
        )
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


# --- 5. 导出成绩单/录入模板 (XLSX格式) ---
@teacher_bp.route("/export_scores", methods=["GET"])
def export_scores():
    exam_task_id = request.args.get("exam_task_id", type=int)
    class_id = request.args.get("class_id", type=int)

    if not exam_task_id or not class_id:
        return jsonify({"msg": "参数缺失"}), 400

    # 1. 获取任务、科目、班级信息
    task = ExamTask.query.get(exam_task_id)
    cls = ClassInfo.query.get(class_id)
    if not task or not cls:
        return jsonify({"msg": "任务或班级不存在"}), 404

    subject_name = task.subject.name  # 例如 "语文"
    short_year = str(cls.entry_year)[-2:]
    formatted_class_name = f"{short_year}级({cls.class_num})班"

    # 2. 获取该班级所有在读学生
    students = (
        Student.query.filter_by(class_id=class_id, status="在读")
        .order_by(Student.student_id)
        .all()
    )

    # 3. 获取已有成绩
    scores = Score.query.filter_by(exam_task_id=exam_task_id).all()
    score_map = {}
    for s in scores:
        if s.remark == "缺考":
            score_map[s.student_id] = "缺考"
        else:
            score_map[s.student_id] = s.score

    # 4. 构造 DataFrame 数据
    data_list = []
    for s in students:
        row = {
            "学号": s.student_id,
            "姓名": s.name,
            "班级名称": formatted_class_name,
            "状态": s.status,
            subject_name: score_map.get(s.id, ""),
        }
        data_list.append(row)

    df = pd.DataFrame(data_list)

    # 5. 写入内存中的 Excel 文件
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="成绩录入")

    output.seek(0)

    filename = f"{formatted_class_name}-{subject_name}-{task.name}.xlsx"
    # 进行 URL 编码防止中文文件名乱码 (前端需配合 decodeURI)
    from urllib.parse import quote

    filename = quote(filename)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
        # 暴露 Content-Disposition 头部给前端，以便获取文件名
        max_age=0,
    )


# --- 6. Excel 批量导入成绩 (含详细错误处理与严格校验) ---
@teacher_bp.route("/import_scores", methods=["POST"])
def import_scores():
    if "file" not in request.files:
        return jsonify({"msg": "没有上传文件"}), 400

    file = request.files["file"]
    exam_task_id = request.form.get("exam_task_id", type=int)
    class_id = request.form.get("class_id", type=int)

    if not exam_task_id or not class_id:
        return jsonify({"msg": "缺少任务ID或班级ID"}), 400

    task = ExamTask.query.get(exam_task_id)
    cls = ClassInfo.query.get(class_id)
    if not task or not cls:
        return jsonify({"msg": "考试任务或班级不存在"}), 404

    if not task.is_active:
        return jsonify({"msg": "该考试已锁定，禁止导入"}), 403

    subject_name = task.subject.name  # 当前要录入的科目名

    # 构造预期的班级名称格式，用于严格校验
    short_year = str(cls.entry_year)[-2:]
    expected_class_name = f"{short_year}级({cls.class_num})班"

    try:
        df = pd.read_excel(file)
        df.fillna("", inplace=True)  # 填充空值为字符串
    except Exception as e:
        return jsonify({"msg": f"Excel读取失败: {str(e)}"}), 400

    # --- 1. 严格校验表头 ---
    # 必须包含 "班级名称", "学号", "姓名" 以及 当前科目
    required_cols = ["学号", "姓名", "班级名称", subject_name]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        return (
            jsonify({"msg": f"Excel格式错误，缺少必要列: {','.join(missing_cols)}"}),
            400,
        )

    # 记录日志
    logs = {"success": 0, "updated": 0, "errors": []}  # 格式: {"row": 1, "msg": "..."}

    # --- 2. 检查是否有“多余”的科目列 ---
    # 获取系统中所有科目名称
    all_subjects = Subject.query.all()
    all_subject_names = set(s.name for s in all_subjects)

    # 找出 Excel 中存在，且属于系统科目，但不是当前录入科目的列
    # 比如当前录“语文”，但表里还有“数学”
    extra_subjects = [
        col for col in df.columns if col in all_subject_names and col != subject_name
    ]

    if extra_subjects:
        logs["errors"].append(
            {
                "row": "全局警报",
                "name": "-",
                "msg": f"检测到多余的科目数据列: [{', '.join(extra_subjects)}]。为了安全起见，只读取 [{subject_name}]，其余科目数据已被忽略。",
            }
        )

    # --- 3. 准备对比数据 ---
    # 获取系统中该班级的所有学生 {student_id_str: student_obj}
    db_students = Student.query.filter_by(class_id=class_id, status="在读").all()
    db_student_map = {s.student_id: s for s in db_students}

    processed_student_ids = set()  # 记录 Excel 中出现的有效系统学号

    # --- 4. 遍历 Excel 行 ---
    for index, row in df.iterrows():
        excel_row_num = index + 2  # Excel 行号从 2 开始

        s_id = str(row["学号"]).strip()
        s_name = str(row["姓名"]).strip()
        row_class_name = str(row["班级名称"]).strip()
        raw_score = row[subject_name]

        # 空行跳过
        if not s_id:
            continue

        # A. 校验班级名称是否匹配
        # 这里进行简单兼容：如果 Excel 是 "23级(1)班" 而 系统期望 "23级(01)班"，也视作不匹配，要求严格一致
        if row_class_name != expected_class_name:
            logs["errors"].append(
                {
                    "row": excel_row_num,
                    "name": s_name,
                    "msg": f"班级不匹配: Excel中为 [{row_class_name}]，应为 [{expected_class_name}]",
                }
            )
            continue

        # B. 检查学生是否存在于当前班级 (db_student_map 只包含本班学生)
        if s_id not in db_student_map:
            # 尝试去全局查一下，明确报错原因
            other_student = Student.query.filter_by(student_id=s_id).first()
            if other_student:
                current_cls = other_student.current_class_rel
                c_name = current_cls.full_name if current_cls else "未知"
                logs["errors"].append(
                    {
                        "row": excel_row_num,
                        "name": s_name,
                        "msg": f"非本班学生 (该生属于 {c_name})，已忽略",
                    }
                )
            else:
                logs["errors"].append(
                    {
                        "row": excel_row_num,
                        "name": s_name,
                        "msg": "系统中不存在该学号，已忽略",
                    }
                )
            continue

        student_obj = db_student_map[s_id]

        # C. 校验姓名是否匹配 (防止学号填错)
        if student_obj.name != s_name:
            logs["errors"].append(
                {
                    "row": excel_row_num,
                    "name": s_name,
                    "msg": f"姓名与学号不匹配，系统记录为: {student_obj.name}",
                }
            )
            continue

        # D. 校验成绩格式
        score_val = 0.0
        remark_val = ""
        if raw_score == "" or pd.isna(raw_score):
            # 空值跳过，不覆盖已有成绩
            continue

        str_val = str(raw_score).strip()

        if str_val == "缺考":
            score_val = 0.0
            remark_val = "缺考"
        else:
            try:
                score_val = float(raw_score)
                if score_val < 0 or score_val > task.full_score:
                    logs["errors"].append(
                        {
                            "row": excel_row_num,
                            "name": s_name,
                            "msg": f"分数 {score_val} 超出范围 (0-{task.full_score})",
                        }
                    )
                    continue
            except ValueError:
                logs["errors"].append(
                    {
                        "row": excel_row_num,
                        "name": s_name,
                        "msg": f"分数格式错误: {raw_score}",
                    }
                )
                continue

        # --- 数据合法，执行写入 ---
        processed_student_ids.add(s_id)

        existing_score = Score.query.filter_by(
            student_id=student_obj.id, exam_task_id=exam_task_id
        ).first()

        if existing_score:
            if existing_score.score != score_val or existing_score.remark != remark_val:
                existing_score.score = score_val
                existing_score.remark = remark_val
                logs["updated"] += 1
        else:
            new_score = Score(
                student_id=student_obj.id,
                subject_id=task.subject_id,
                exam_task_id=task.id,
                score=score_val,
                term=task.name,
                remark=remark_val,
            )
            db.session.add(new_score)
            logs["success"] += 1

    # --- 5. 检查本班名单中缺失的人员 (在班里但 Excel 没填) ---
    all_db_ids = set(db_student_map.keys())
    missing_ids = all_db_ids - processed_student_ids

    # 只是记录一下，不算作错误，也许老师就是只想录入一部分
    # 但如果为了严格提示，也可以加到 errors 里作为 Info
    if missing_ids:
        missing_names = [db_student_map[mid].name for mid in missing_ids]
        # 只取前5个名字展示，避免太长
        show_names = ",".join(missing_names[:5])
        if len(missing_names) > 5:
            show_names += f" 等{len(missing_names)}人"

        logs["errors"].append(
            {
                "row": "-",
                "name": "-",
                "msg": f"提示: 本班还有 {len(missing_names)} 人未包含在Excel中 ({show_names})，未更新其成绩",
            }
        )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"数据库写入失败: {str(e)}"}), 500

    # 构造返回信息
    msg = f"处理完成。成功录入: {logs['success']}，更新: {logs['updated']}。"
    if logs["errors"]:
        msg += f" 发现 {len(logs['errors'])} 个问题/提示，请务必查看详情。"

    return jsonify({"msg": msg, "logs": logs})
