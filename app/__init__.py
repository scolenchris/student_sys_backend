from flask import Flask, request
from flask_cors import CORS
from config import Config
from .models import db
from sqlalchemy.exc import OperationalError
from flask import jsonify
import os
import sys

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
    # --- 1. 更加稳健的路径查找逻辑 ---

    # 路径A：当前工作目录下的 dist (通常是用户双击 exe 时的目录)
    cwd_dist = os.path.join(os.getcwd(), "dist")

    # 路径B：exe 文件所在目录下的 dist (防止某些情况下工作目录不一致)
    exe_dist = os.path.join(os.path.dirname(sys.executable), "dist")

    # 路径C：开发环境的相对路径
    dev_dist = "../../student_sys_frontend/dist"

    # --- 2. 依次检测 ---
    if os.path.exists(cwd_dist):
        dist_path = cwd_dist
        mode_msg = "生产模式 (在当前目录下找到 dist)"
    elif os.path.exists(exe_dist):
        dist_path = exe_dist
        mode_msg = "生产模式 (在exe目录下找到 dist)"
    else:
        dist_path = dev_dist
        mode_msg = "开发模式 (未找到本地dist，尝试使用源码路径)"

    # --- 3. 打印调试信息 ---
    print("=" * 60)
    print(f"路径判定结果: {mode_msg}")
    print(f"最终使用的前端路径: {dist_path}")
    print(f"路径有效性校验: {os.path.exists(dist_path)}")
    print("=" * 60)

    # --- 4. 初始化 Flask ---
    app = Flask(__name__, static_folder=dist_path, static_url_path="")
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

    @app.route("/")
    def index():
        # 如果 dist 目录还没生成，提示一下
        if not os.path.exists(app.static_folder):
            return (
                "前端构建文件(dist)未找到，请先执行 npm run build 并将 dist 文件夹拷贝到后端根目录。",
                404,
            )
        return app.send_static_file("index.html")

    @app.errorhandler(404)
    def not_found(e):
        # 如果请求的是 API 接口 (以 /api 开头)，那确实是 404
        if request.path.startswith("/api/"):
            return jsonify(msg="接口不存在"), 404

        # 否则，如果是页面请求，返回 index.html
        if os.path.exists(os.path.join(app.static_folder, "index.html")):
            return app.send_static_file("index.html")

        return "404 Not Found", 404

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
