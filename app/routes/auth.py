from flask import Blueprint, request, jsonify
from app.models import db, User, Teacher
from flask_jwt_extended import create_access_token # 建议安装 flask-jwt-extended

auth_bp = Blueprint('auth', __name__)

# 注册接口
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')  # 'admin' 或 'teacher'
    real_name = data.get('name') # 真实姓名

    if User.query.filter_by(username=username).first():
        return jsonify({"msg": "用户名已存在"}), 400

    new_user = User(username=username, role=role, is_approved=False)
    new_user.set_password(password)
    
    db.session.add(new_user)
    db.session.flush() # 获取新用户的ID

    # 如果是老师，同时在教师表创建一条基础信息
    if role == 'teacher':
        new_teacher = Teacher(user_id=new_user.id, name=real_name)
        db.session.add(new_teacher)
    
    db.session.commit()
    return jsonify({"msg": "注册成功，请等待管理员审核"}), 201

# 登录接口
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    # print(f"收到登录请求: {data}") #debug
    user = User.query.filter_by(username=data.get('username')).first()

    if not user or not user.check_password(data.get('password')):
        return jsonify({"msg": "用户名或密码错误"}), 401
    
    if not user.is_approved:
        return jsonify({"msg": "账号正在审核中，请联系系主任"}), 403

    # 生成 Token (简单起见这里先返回用户信息，后续建议用 JWT)
    return jsonify({
        "msg": "登录成功",
        "role": user.role,
        "username": user.username,
        "user_id": user.id
    }), 200