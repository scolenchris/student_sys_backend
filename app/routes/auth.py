from flask import Blueprint, request, jsonify
from app.models import db, User, Teacher
from flask_jwt_extended import create_access_token  # 建议安装 flask-jwt-extended

auth_bp = Blueprint("auth", __name__)


# 注册接口
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    role = data.get("role")  # 'admin' 或 'teacher'
    real_name = data.get("name")  # 真实姓名

    if User.query.filter_by(username=username).first():
        return jsonify({"msg": "用户名已存在"}), 400

    new_user = User(username=username, role=role, is_approved=False)
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.flush()  # 获取新用户的ID

    # 如果是老师，同时在教师表创建一条基础信息
    if role == "teacher":
        new_teacher = Teacher(user_id=new_user.id, name=real_name)
        db.session.add(new_teacher)

    db.session.commit()
    return jsonify({"msg": "注册成功，请等待管理员审核"}), 201


# 登录接口
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    user = User.query.filter_by(username=data.get("username")).first()

    if not user or not user.check_password(data.get("password")):
        return jsonify({"msg": "用户名或密码错误"}), 401

    if not user.is_approved:
        return jsonify({"msg": "账号正在审核中，请联系系主任"}), 403

    return (
        jsonify(
            {
                "msg": "登录成功",
                "role": user.role,
                "username": user.username,
                "user_id": user.id,
                "must_change_password": user.must_change_password,  # 必须修改密码标记
            }
        ),
        200,
    )


# 修改密码接口
@auth_bp.route("/change_password", methods=["POST"])
def change_password():
    data = request.get_json()
    user_id = data.get("user_id")
    old_password = data.get("old_password")
    new_password = data.get("new_password")

    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "用户不存在"}), 404

    # 验证旧密码
    if not user.check_password(old_password):
        return jsonify({"msg": "旧密码错误"}), 400

    user.set_password(new_password)
    user.must_change_password = False  # 修改成功后，取消强制标记
    db.session.commit()

    return jsonify({"msg": "密码修改成功，请重新登录"}), 200
