from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# 1. 用户表（登录与权限控制）
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    is_approved = db.Column(db.Boolean, default=False)
    teacher_profile = db.relationship("Teacher", backref="user", uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# 2. 教师信息表
class Teacher(db.Model):
    __tablename__ = "teachers"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    # 基础档案
    name = db.Column(db.String(64), nullable=False)
    gender = db.Column(db.String(10), default="男")
    ethnicity = db.Column(db.String(20), default="汉族")
    phone = db.Column(db.String(20))

    # 职业属性
    status = db.Column(db.String(20), default="在职")
    job_title = db.Column(db.String(50))  # 职称 (中学一级等)
    education = db.Column(db.String(20))  # 学历
    major = db.Column(db.String(50))  # 专业

    # 权限备注
    remarks = db.Column(db.String(255))

    # 关联关系 (反向引用)
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
    students = db.relationship("Student", backref="current_class", lazy="dynamic")

    @property
    def grade_display(self):
        current_year = datetime.now().year
        diff = current_year - self.entry_year
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


# --- 新增：职务分配关联表 ---


# 5. 班主任分配 (多对多：一个老师可以是多个班的班主任)
class HeadTeacherAssignment(db.Model):
    __tablename__ = "assign_head_teacher"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"))

    class_info = db.relationship("ClassInfo")


# 6. 级长分配 (一个老师可以是某个年级(entry_year)的级长)
class GradeLeaderAssignment(db.Model):
    __tablename__ = "assign_grade_leader"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    entry_year = db.Column(db.Integer)  # 记录的是入学年份，代表某一级

    @property
    def grade_name(self):
        current_year = datetime.now().year
        diff = current_year - self.entry_year
        grade_map = {0: "初一", 1: "初二", 2: "初三"}
        return grade_map.get(diff, f"{self.entry_year}级")


# 7. 科组长分配 (全校性，针对某个学科)
class SubjectGroupLeaderAssignment(db.Model):
    __tablename__ = "assign_subject_group_leader"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))

    subject = db.relationship("Subject")


# 8. 备课组长分配 (特定年级 + 特定学科)
class PrepGroupLeaderAssignment(db.Model):
    __tablename__ = "assign_prep_group_leader"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    entry_year = db.Column(db.Integer)  # 针对哪个年级
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))  # 针对哪个学科

    subject = db.relationship("Subject")

    @property
    def grade_name(self):
        current_year = datetime.now().year
        diff = current_year - self.entry_year
        grade_map = {0: "初一", 1: "初二", 2: "初三"}
        return grade_map.get(diff, f"{self.entry_year}级")


# 9. 任课分配 (教学) (保持不变，支持多班多科)
class CourseAssignment(db.Model):
    __tablename__ = "course_assignments"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))

    class_info = db.relationship("ClassInfo")
    subject = db.relationship("Subject")


# 10. 学生和成绩表 (略，保持不变)
class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    gender = db.Column(db.String(10))
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"))
    status = db.Column(db.String(20), default="active")
    scores = db.relationship("Score", backref="student", lazy="dynamic")
    current_class_rel = db.relationship("ClassInfo")  # 避免重名冲突


class Score(db.Model):
    __tablename__ = "scores"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))
    score = db.Column(db.Float, default=0.0)
    term = db.Column(db.String(20))
    create_time = db.Column(db.DateTime, default=datetime.now)
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
