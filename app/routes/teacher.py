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
            "班级名称": formatted_class_name,  # 【修改点 2】使用上面构造的格式
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


# --- 6. Excel 批量导入成绩 (含详细错误处理) ---
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
    if not task:
        return jsonify({"msg": "考试任务不存在"}), 404

    if not task.is_active:
        return jsonify({"msg": "该考试已锁定，禁止导入"}), 403

    subject_name = task.subject.name  # 必须匹配的列名

    try:
        df = pd.read_excel(file)
        df.fillna("", inplace=True)  # 填充空值为字符串，防止 NaN 报错
    except Exception as e:
        return jsonify({"msg": f"Excel读取失败: {str(e)}"}), 400

    # --- 校验表头 ---
    required_cols = ["学号", "姓名", subject_name]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        return jsonify({"msg": f"Excel格式错误，缺少列: {','.join(missing_cols)}"}), 400

    # --- 准备对比数据 ---
    # 获取系统中该班级的所有学生 {student_id_str: student_obj}
    db_students = Student.query.filter_by(class_id=class_id, status="在读").all()
    db_student_map = {s.student_id: s for s in db_students}

    # 记录日志
    logs = {"success": 0, "updated": 0, "errors": []}  # 格式: {"row": 1, "msg": "..."}

    processed_student_ids = set()  # 记录 Excel 中出现的有效系统学号

    # --- 遍历 Excel 行 ---
    for index, row in df.iterrows():
        excel_row_num = index + 2  # Excel 行号从 2 开始 (1是表头)

        s_id = str(row["学号"]).strip()
        s_name = str(row["姓名"]).strip()
        # 获取成绩，可能是数字或字符串
        raw_score = row[subject_name]

        # 1. 检查空行
        if not s_id:
            continue

        # 2. 检查 Excel 中的学生是否存在于 系统当前班级
        if s_id not in db_student_map:
            # 错误情形：Excel里有，但系统班级里没有 (可能是转走了，或者是别的班的)
            # 尝试去全局查一下，看是不是别的班的
            other_student = Student.query.filter_by(student_id=s_id).first()
            if other_student:
                logs["errors"].append(
                    {
                        "row": excel_row_num,
                        "name": s_name,
                        "msg": f"该生在系统中属于 {other_student.current_class_rel.full_name}，非当前班级",
                    }
                )
            else:
                logs["errors"].append(
                    {
                        "row": excel_row_num,
                        "name": s_name,
                        "msg": "系统中未找到该学号（非本班学生）",
                    }
                )
            continue

        student_obj = db_student_map[s_id]

        # 3. 校验姓名是否匹配 (防止学号填错导致张冠李戴)
        if student_obj.name != s_name:
            logs["errors"].append(
                {
                    "row": excel_row_num,
                    "name": s_name,
                    "msg": f"学号与姓名不匹配，系统记录为: {student_obj.name}",
                }
            )
            continue

        # 4. 校验成绩格式
        score_val = 0.0
        remark_val = ""
        if raw_score == "" or pd.isna(raw_score):
            continue  # 或根据需求处理

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
            # 更新逻辑：分数变了 OR 备注变了（例如从0分变缺考，或缺考变0分）
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

    # --- 5. 循环结束后，检查缺失人员 ---
    # (即：系统里有，但 Excel 里没出现的学生)
    all_db_ids = set(db_student_map.keys())
    missing_ids = all_db_ids - processed_student_ids

    for mid in missing_ids:
        missing_stu = db_student_map[mid]
        logs["errors"].append(
            {"row": "-", "name": missing_stu.name, "msg": "Excel 中缺失该学生成绩"}
        )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"数据库写入失败: {str(e)}"}), 500

    # 构造返回信息
    msg = f"处理完成。新增: {logs['success']}，更新: {logs['updated']}。"
    if logs["errors"]:
        msg += f" 发现 {len(logs['errors'])} 个问题，请查看详情。"

    return jsonify({"msg": msg, "logs": logs})
