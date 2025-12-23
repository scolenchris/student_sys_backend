import os

class Config:
    # 基础安全配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'student-sys-secret-123456'
    
    # MySQL 数据库配置
    # 格式: mysql+pymysql://用户名:密码@主机地址:端口/数据库名?charset=utf8mb4
    # utf8mb4 确保能支持中文姓名及特殊字符
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:@localhost:3306/school_db?charset=utf8mb4'
    
    # 性能优化配置
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # 禁用追踪以节省内存和性能
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 3600,  # 1小时重连一次，防止 MySQL 自动断开
        "pool_pre_ping": True, # 每次请求前检查连接是否可用
    }

    # JWT 或 Session 过期时间设置（可选）
    # JWT_ACCESS_TOKEN_EXPIRES = 3600