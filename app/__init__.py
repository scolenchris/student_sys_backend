from flask import Flask
from flask_cors import CORS
from config import Config
from .models import db
from sqlalchemy.exc import OperationalError
from flask import jsonify

# from sqlalchemy import event
# from sqlalchemy.engine import Engine


# --- 核心修改：开启 SQLite 的 WAL 模式 ---
# 监听 Engine 的 connect 事件，设置 SQLite 的日志模式为 WAL，提升并发性能
# @event.listens_for(Engine, "connect")
# def set_sqlite_pragma(dbapi_connection, connection_record):
#     # 只有当使用 SQLite 时才执行（判断 dbapi_connection 是否是 sqlite3 的连接对象）
#     # 简单的做法是直接执行，因为我们已经确定切换到了 SQLite
#     cursor = dbapi_connection.cursor()
#     cursor.execute("PRAGMA journal_mode=WAL")
#     cursor.execute(
#         "PRAGMA synchronous=NORMAL"
#     )  # 可选：进一步牺牲极少的数据安全性换取更高写入性能
#     cursor.close()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 1. 初始化插件
    CORS(app)
    db.init_app(app)

    @app.errorhandler(413)
    def request_entity_too_large(error):
        from flask import jsonify

        return jsonify(msg="上传文件过大，请限制在 16MB 以内"), 413

    @app.errorhandler(OperationalError)
    def handle_db_error(e):
        # 打印错误到后台控制台，方便你排查
        print(f"数据库错误: {str(e)}")

        # 如果是 SQLite 的锁定错误
        if "database is locked" in str(e):
            return jsonify({"msg": "当前提交人数过多，系统繁忙，请稍后重试！"}), 500

        return jsonify({"msg": "数据库操作异常"}), 500

    # 2. 注册蓝图
    from .routes.auth import auth_bp
    from .routes.admin import admin_bp
    from .routes.teacher import teacher_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(teacher_bp, url_prefix="/api/teacher")

    # 3. 创建数据库表
    with app.app_context():
        # SQLite 文件不存在时会自动创建
        db.create_all()

        from .models import Subject

        # 初始化科目数据
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

        if Subject.query.count() == 0:
            for name in target_order:
                db.session.add(Subject(name=name))
            db.session.commit()
            print(">> [SQLite] 科目表初始化完成。")

        db.session.commit()

    return app
