import os
import sys

# if getattr(sys, "frozen", False):
#     basedir = os.path.dirname(sys.executable)
# else:
#     basedir = os.path.abspath(os.path.dirname(__file__))

basedir = os.getcwd()


class Config:
    # 基础安全配置
    SECRET_KEY = os.environ.get("SECRET_KEY") or "student-sys-secret-123456"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # --- 数据库配置 (已切换为 SQLite) ---
    # 数据库文件 'school.db' 将生成在后端项目根目录下
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(basedir, "school.db")

    # 性能优化配置
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # 禁用追踪以节省内存

    # SQLite 配置项
    # 注意：SQLite 通常不需要 MySQL 的 pool_recycle 配置
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }

    # JWT 或 Session 过期时间设置（可选）
    # JWT_ACCESS_TOKEN_EXPIRES = 3600
