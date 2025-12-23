import os

def print_directory_contents(path, skip_dirs, indent_level=0):
    """
    递归打印文件夹结构，跳过指定的目录。
    """
    try:
        # 获取当前目录下所有文件和子目录
        items = os.listdir(path)
    except PermissionError:
        print("  " * indent_level + "[权限不足]")
        return

    for item in items:
        item_path = os.path.join(path, item)
        
        # 检查是否在跳过列表中
        if item in skip_dirs:
            continue
            
        # 打印当前层级
        print("  " * indent_level + "|-- " + item)

        # 如果是目录，则递归进入
        if os.path.isdir(item_path):
            print_directory_contents(item_path, skip_dirs, indent_level + 1)

if __name__ == "__main__":
    # 设定根目录（点号代表当前目录）
    root_directory = "." 
    
    # 设定需要排除的文件夹名称
    exclude = [
        "python-3.12.6-embed-amd64", 
        "__pycache__",
        ".vscode"
    ]
    
    print(f"项目结构目录 ({os.path.abspath(root_directory)}):")
    print_directory_contents(root_directory, exclude)