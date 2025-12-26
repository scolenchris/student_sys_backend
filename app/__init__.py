from flask import Flask
from flask_cors import CORS
from config import Config
from .models import db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 1. 初始化插件
    # CORS 解决前后端分离导致的跨域问题（Vue 访问 Flask）
    CORS(app)
    db.init_app(app)

    # 2. 注册蓝图 (待后续编写)
    from .routes.auth import auth_bp
    from .routes.admin import admin_bp
    from .routes.teacher import teacher_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(teacher_bp, url_prefix="/api/teacher")

    # 3. 创建数据库表
    with app.app_context():
        # 这行代码会在 MySQL 中自动创建 models.py 中定义的表
        # 如果表已存在，则不会重复创建或修改
        db.create_all()

        # 这里可以预留一个初始化管理员的函数
        # init_admin_user()

        from .models import Subject

        subject_list = [
            "语文",
            "数学",
            "英语",
            "道德与法治",
            "历史",
            "物理",
            "化学",
            "生物",
            "地理",
            "体育与健康",
            "美术",
            "音乐",
            "信息科技",
            "英语听说",
        ]

        for name in subject_list:
            # 如果数据库里没有这个科目，就添加进去
            if not Subject.query.filter_by(name=name).first():
                db.session.add(Subject(name=name))

        db.session.commit()

    return app
