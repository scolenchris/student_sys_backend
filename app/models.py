from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# 1. 用户表（登录与权限控制）
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' 或 'teacher'
    is_approved = db.Column(db.Boolean, default=False)  # 新增：是否已审核通过(注册)
    # 建立与教师表的1对1关联
    teacher_profile = db.relationship('Teacher', backref='user', uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 2. 教师信息表
class Teacher(db.Model):
    __tablename__ = 'teachers'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    name = db.Column(db.String(64), nullable=False)
    phone = db.Column(db.String(20))
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id')) # 教师主教学科

# 3. 班级表
class ClassInfo(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    entry_year = db.Column(db.Integer, nullable=False)  # 入学年份，如2023
    class_num = db.Column(db.Integer, nullable=False)   # 班级编号，如1 (即2023级1班)
    
    # 关联学生
    students = db.relationship('Student', backref='current_class', lazy='dynamic')

    @property
    def grade_display(self):
        """根据当前年份动态计算年级名称（初一/初二/初三）"""
        current_year = datetime.now().year
        diff = current_year - self.entry_year
        grade_map = {0: "初一", 1: "初二", 2: "初三"}
        return grade_map.get(diff, "已毕业")

# 4. 学生学籍表
class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False) # 学号
    name = db.Column(db.String(64), nullable=False)
    gender = db.Column(db.String(10))
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))
    status = db.Column(db.String(20), default='active') # active/graduated

    scores = db.relationship('Score', backref='student', lazy='dynamic')

# 5. 科目表
class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False) # 语文、数学等

# 6. 任课关联表（核心：谁在哪个班教哪门课）
class CourseAssignment(db.Model):
    __tablename__ = 'course_assignments'
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))

# 7. 成绩表
class Score(db.Model):
    __tablename__ = 'scores'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    score = db.Column(db.Float, default=0.0)
    term = db.Column(db.String(20)) # 学期，如 "2023-2024-1"
    create_time = db.Column(db.DateTime, default=datetime.now)
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)