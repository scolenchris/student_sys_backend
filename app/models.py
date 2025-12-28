from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# 1. 用户表
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    is_approved = db.Column(db.Boolean, default=False)
    teacher_profile = db.relationship("Teacher", backref="user", uselist=False)
    must_change_password = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# 2. 教师信息表
class Teacher(db.Model):
    __tablename__ = "teachers"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    name = db.Column(db.String(64), nullable=False)
    gender = db.Column(db.String(10), default="男")
    ethnicity = db.Column(db.String(20), default="汉族")
    phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default="在职")
    job_title = db.Column(db.String(50))
    education = db.Column(db.String(20))
    major = db.Column(db.String(50))
    remarks = db.Column(db.String(255))

    head_teacher_assigns = db.relationship(
        "HeadTeacherAssignment", backref="teacher", cascade="all, delete-orphan"
    )
    grade_leader_assigns = db.relationship(
        "GradeLeaderAssignment", backref="teacher", cascade="all, delete-orphan"
    )
    subject_group_assigns = db.relationship(
        "SubjectGroupLeaderAssignment", backref="teacher", cascade="all, delete-orphan"
    )
    prep_group_assigns = db.relationship(
        "PrepGroupLeaderAssignment", backref="teacher", cascade="all, delete-orphan"
    )
    course_assignments = db.relationship(
        "CourseAssignment", backref="teacher", cascade="all, delete-orphan"
    )


# 3. 班级表 (已修复警告：修改 backref 名称)
class ClassInfo(db.Model):
    __tablename__ = "classes"
    id = db.Column(db.Integer, primary_key=True)
    entry_year = db.Column(db.Integer, nullable=False)
    class_num = db.Column(db.Integer, nullable=False)
    students = db.relationship("Student", backref="current_class_rel", lazy="dynamic")

    @property
    def grade_display(self):
        current_year = datetime.now().year
        # 简单逻辑：9月后算新学年
        if datetime.now().month >= 9:
            diff = current_year - self.entry_year
        else:
            diff = current_year - self.entry_year - 1

        grade_map = {0: "初一", 1: "初二", 2: "初三"}
        return grade_map.get(diff, "已毕业")

    @property
    def full_name(self):
        return f"{self.grade_display}({self.class_num})班"


# 4. 科目表
class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)


# --- 考试发布任务表 ---
class ExamTask(db.Model):
    __tablename__ = "exam_tasks"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # 考试名称，如“初一上期末”
    # 针对哪个年级（入学年份），因为班级也是按入学年份区分的
    entry_year = db.Column(db.Integer, nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    full_score = db.Column(db.Float, default=100.0)
    is_active = db.Column(db.Boolean, default=True)  # 录入状态：True可录，False禁录
    create_time = db.Column(db.DateTime, default=datetime.now)

    subject = db.relationship("Subject")

    @property
    def grade_name(self):
        current_year = datetime.now().year
        if datetime.now().month >= 9:
            diff = current_year - self.entry_year
        else:
            diff = current_year - self.entry_year - 1
        grade_map = {0: "初一", 1: "初二", 2: "初三"}
        return grade_map.get(diff, f"{self.entry_year}级")


# --- 职务分配关联表 ---
class HeadTeacherAssignment(db.Model):
    __tablename__ = "assign_head_teacher"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"))
    class_info = db.relationship("ClassInfo")


class GradeLeaderAssignment(db.Model):
    __tablename__ = "assign_grade_leader"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    entry_year = db.Column(db.Integer)

    @property
    def grade_name(self):
        return f"{self.entry_year}级"  # 简化显示


class SubjectGroupLeaderAssignment(db.Model):
    __tablename__ = "assign_subject_group_leader"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))
    subject = db.relationship("Subject")


class PrepGroupLeaderAssignment(db.Model):
    __tablename__ = "assign_prep_group_leader"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    entry_year = db.Column(db.Integer)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))
    subject = db.relationship("Subject")

    @property
    def grade_name(self):
        return f"{self.entry_year}级"


class CourseAssignment(db.Model):
    __tablename__ = "course_assignments"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))
    class_info = db.relationship("ClassInfo")
    subject = db.relationship("Subject")


# 10. 学生和成绩表
class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    gender = db.Column(db.String(10), default="男")
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"))
    status = db.Column(db.String(20), default="在读")
    household_registration = db.Column(db.String(50))
    city_school_id = db.Column(db.String(50))
    national_school_id = db.Column(db.String(50))
    id_card_number = db.Column(db.String(20), unique=True)
    remarks = db.Column(db.String(255))

    scores = db.relationship("Score", backref="student", lazy="dynamic")


class Score(db.Model):
    __tablename__ = "scores"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))
    score = db.Column(db.Float, default=0.0)
    remark = db.Column(db.String(20), default="")

    # 关联具体的考试任务
    exam_task_id = db.Column(db.Integer, db.ForeignKey("exam_tasks.id"), nullable=True)
    task = db.relationship("ExamTask")

    # 保留 term 字段以兼容旧数据，新逻辑主要依赖 exam_task_id
    term = db.Column(db.String(20))

    create_time = db.Column(db.DateTime, default=datetime.now)
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
