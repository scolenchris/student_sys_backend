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
        db.create_all()

        from .models import Subject

        # 【全局修正】严格按照教务处的顺序初始化
        # 数据库 ID 将会是：1-语文, 2-数学, 3-英语, 4-英语听说 ... 14-音乐
        target_order = [
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

        # 检查是否为空，只有为空时才初始化，保证 ID 连续
        if Subject.query.count() == 0:
            for name in target_order:
                db.session.add(Subject(name=name))
            db.session.commit()
            print(">> 科目表初始化完成，ID顺序已校准。")

        db.session.commit()

    return app
