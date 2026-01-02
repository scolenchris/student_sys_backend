from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint  # 引入联合唯一约束

db = SQLAlchemy()


# 1. 用户表 (不变)
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


# 2. 教师信息表 (去除了关系字段的直接关联，交由中间表管理)
class Teacher(db.Model):
    __tablename__ = "teachers"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    name = db.Column(db.String(64), nullable=False)
    gender = db.Column(db.String(10), default="男")
    ethnicity = db.Column(db.String(20), default="汉族")
    phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default="在职")  # 在职/离职/退休
    job_title = db.Column(db.String(50))
    education = db.Column(db.String(20))
    major = db.Column(db.String(50))
    remarks = db.Column(db.String(255))

    # 关系定义保持不变，通过 backref 访问
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


# 3. 班级表 (不变)
class ClassInfo(db.Model):
    __tablename__ = "classes"
    id = db.Column(db.Integer, primary_key=True)
    entry_year = db.Column(db.Integer, nullable=False)
    class_num = db.Column(db.Integer, nullable=False)
    students = db.relationship("Student", backref="current_class_rel", lazy="dynamic")

    @property
    def grade_display(self):
        # 注意：这个属性是动态计算的，只代表“当前”的年级。
        # 如果要查询历史某个学年时的年级，需要在业务逻辑中手动计算 (查询学年 - entry_year)
        current_year = datetime.now().year
        if datetime.now().month >= 9:
            diff = current_year - self.entry_year
        else:
            diff = current_year - self.entry_year - 1

        grade_map = {0: "初一", 1: "初二", 2: "初三"}
        return grade_map.get(diff, "已毕业")

    @property
    def full_name(self):
        return f"{self.grade_display}({self.class_num})班"


# 4. 科目表 (不变)
class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)


# 5. 考试任务表 (新增 academic_year)
class ExamTask(db.Model):
    __tablename__ = "exam_tasks"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    entry_year = db.Column(db.Integer, nullable=False)  # 针对哪个年级 (如2023级)

    # [新增] 所属学年 (如 2024 表示 2024-2025学年)
    academic_year = db.Column(db.Integer, nullable=False, default=datetime.now().year)

    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    full_score = db.Column(db.Float, default=100.0)
    is_active = db.Column(db.Boolean, default=True)
    create_time = db.Column(db.DateTime, default=datetime.now)

    subject = db.relationship("Subject")

    @property
    def grade_name(self):
        # 同样，这个是基于当前时间的动态显示。历史查询时建议后端计算好返回给前端。
        current_year = datetime.now().year
        if datetime.now().month >= 9:
            diff = current_year - self.entry_year
        else:
            diff = current_year - self.entry_year - 1
        grade_map = {0: "初一", 1: "初二", 2: "初三"}
        return grade_map.get(diff, f"{self.entry_year}级")


# --- 职务分配关联表 (全部新增 academic_year) ---


class HeadTeacherAssignment(db.Model):
    __tablename__ = "assign_head_teacher"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"))

    # [新增] 学年
    academic_year = db.Column(db.Integer, nullable=False)

    class_info = db.relationship("ClassInfo")

    # 联合唯一：同一个班级在同一个学年只能有一个班主任
    __table_args__ = (
        UniqueConstraint("class_id", "academic_year", name="uq_ht_class_year"),
    )


class GradeLeaderAssignment(db.Model):
    __tablename__ = "assign_grade_leader"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    entry_year = db.Column(db.Integer)  # 负责哪一届

    # [新增] 学年
    academic_year = db.Column(db.Integer, nullable=False)

    @property
    def grade_name(self):
        return f"{self.entry_year}级"


class SubjectGroupLeaderAssignment(db.Model):
    __tablename__ = "assign_subject_group_leader"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))

    # [新增] 学年
    academic_year = db.Column(db.Integer, nullable=False)

    subject = db.relationship("Subject")


class PrepGroupLeaderAssignment(db.Model):
    __tablename__ = "assign_prep_group_leader"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    entry_year = db.Column(db.Integer)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))

    # [新增] 学年
    academic_year = db.Column(db.Integer, nullable=False)

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

    # [新增] 学年
    academic_year = db.Column(db.Integer, nullable=False)

    class_info = db.relationship("ClassInfo")
    subject = db.relationship("Subject")

    # 联合唯一：同一学年、同一班级、同一科目 只能有一个老师 (避免重复导入)
    __table_args__ = (
        UniqueConstraint(
            "class_id", "subject_id", "academic_year", name="uq_course_assign"
        ),
    )


# 10. 学生和成绩表
class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    gender = db.Column(db.String(10), default="男")

    # 这是学生“当前”所在的班级
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

    exam_task_id = db.Column(db.Integer, db.ForeignKey("exam_tasks.id"), nullable=True)
    task = db.relationship("ExamTask")

    # [新增] 班级快照：记录考试时学生所在的班级ID，防止学生转班后历史成绩归属错误
    class_id_snapshot = db.Column(
        db.Integer, db.ForeignKey("classes.id"), nullable=True
    )

    # 关联到班级表，方便直接查询历史班级信息
    class_info = db.relationship("ClassInfo")

    term = db.Column(db.String(20))  # 保留兼容
    create_time = db.Column(db.DateTime, default=datetime.now)
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
