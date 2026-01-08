import os
import sys
from waitress import serve

# 动态获取当前文件 (run.py) 所在的绝对路径
basedir = os.path.dirname(os.path.abspath(__file__))
# 将该路径加入搜索列表的首位
if basedir not in sys.path:
    sys.path.insert(0, basedir)

# 现在再尝试导入
try:
    from app import create_app
except ModuleNotFoundError as e:
    print(f"当前搜索路径: {sys.path}")
    raise e
app = create_app()

if __name__ == "__main__":
    # host='0.0.0.0' 允许局域网内的其他电脑访问该服务器
    # port=5000 默认端口
    # debug=True 开发环境开启，老旧电脑建议上线后设为 False 减少资源占用
    print("系统启动中... 请访问 http://localhost:5173")
    app.run(host="0.0.0.0", port=5173, debug=True)

    # 使用 waitress 启动，支持并发，更稳定
    # serve(app, host="0.0.0.0", port=5173, threads=6)
