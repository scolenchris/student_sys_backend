import os
import sys
from waitress import serve
import traceback

# 动态获取当前文件 (run.py) 所在的绝对路径
basedir = os.path.dirname(os.path.abspath(__file__))
# 将该路径加入搜索列表的首位
if basedir not in sys.path:
    sys.path.insert(0, basedir)

# 现在再尝试导入
try:
    from app import create_app, db
    from app.models import User
except ModuleNotFoundError as e:
    print(f"当前搜索路径: {sys.path}")
    input(f"导入错误: {e}\n按回车键退出...")  # 防止闪退
    sys.exit(1)

app = create_app()


def initialize_system():
    """
    系统冷启动初始化：
    1. 自动创建数据库表
    2. 检测并创建默认管理员账户
    """
    print("-" * 50)
    print("[系统自检] 正在检查数据库环境...")

    with app.app_context():
        # 1. 确保所有表都已创建 (如果 school.db 不存在会自动生成)
        db.create_all()

        # 2. 检查是否存在管理员账号
        # 这里假设 role='admin' 代表管理员权限
        admin_user = User.query.filter_by(username="adminwds").first()

        if not admin_user:
            print("[系统初始化] 未检测到管理员，正在创建默认账户...")

            # 根据你的 app/models.py 结构创建用户
            new_admin = User(
                username="adminwds",
                real_name="韦东生",  # 注意：你的模型里字段叫 real_name
                role="admin",  # 设置角色为管理员
                is_approved=True,  # 默认已审核通过
                must_change_password=False,
            )

            # 设置初始密码
            new_admin.set_password("wds123456@")

            db.session.add(new_admin)
            db.session.commit()

            print("[系统初始化] 管理员创建成功！")
        else:
            print("[系统自检] 管理员账户已存在，跳过初始化。")
    print("-" * 50)


if __name__ == "__main__":

    try:
        # 1. 执行初始化
        initialize_system()

        print("系统启动中... 请访问 http://localhost:5173 进行调试")
        print("注意：如需关闭服务器，请直接关闭此窗口")
        print("=" * 60)

        # 2. 启动服务 (Waitress)
        serve(app, host="0.0.0.0", port=5173, threads=6)
        # app.run(host="0.0.0.0", port=5173, debug=True)

    except OSError as e:
        if e.winerror == 10048:
            print("\n" + "!" * 60)
            print("【启动失败】端口 5173 被占用！")
            print("原因：上一次运行的程序可能没有完全关闭。")
            print("解决方法：请打开任务管理器，结束所有 'run.exe' 或 'main.exe' 进程。")
            print("!" * 60 + "\n")
        else:
            print(f"\n【启动错误】: {e}")
            traceback.print_exc()
    except Exception as e:
        print(f"\n【未知错误】: {e}")
        traceback.print_exc()
    finally:
        # 【关键】无论发生什么错误，都暂停在这里，等待用户按回车
        input("\n程序已结束，按回车键关闭窗口...")

    # initialize_system()
    # # host='0.0.0.0' 允许局域网内的其他电脑访问该服务器
    # # port=5000 默认端口
    # # debug=True 开发环境开启，老旧电脑建议上线后设为 False 减少资源占用
    # print("系统启动中... 请访问 http://localhost:5173 进行调试")
    # print("注意：如需关闭服务器，请直接关闭此窗口")

    # # 使用 Flask 内置服务器启动（仅限开发调试使用）
    # # app.run(host="0.0.0.0", port=5173, debug=True)

    # # 使用 waitress 启动，支持并发，更稳定
    # serve(app, host="0.0.0.0", port=5173, threads=6)
