import os

class PathManager:
    """
    一个中心化的路径管理器，用于生成和存储应用程序所需的所有文件和目录路径。
    此类现在是所有权威路径的唯一来源，由main.py在启动时注入。
    """
    def __init__(self, base_dir: str, executable_path: str, main_script_path: str):
        """
        使用应用程序的权威路径初始化路径管理器。

        Args:
            base_dir (str): 应用程序的根目录 (BASE_DIR)。
            executable_path (str): 启动器 .exe 或 python.exe 的真实路径。
            main_script_path (str): 主脚本 main.py 的真实路径 (仅在脚本模式下有效)。
        """
        self.base_dir = base_dir
        self.executable_path = executable_path
        self.main_script_path = main_script_path

        # --- 核心配置文件 ---
        self.control_config = os.path.join(self.base_dir, 'control_config.json')
        self.languages = os.path.join(self.base_dir, 'languages.json')

        # --- GUI 相关文件 ---
        self.style_qss = os.path.join(self.base_dir, 'gui', 'style.qss')
        
        # --- 图标 ---
        self.app_icon = os.path.join(self.base_dir, 'app_icon.ico')

        # --- 任务计划程序模板 ---
        self.task_template = os.path.join(self.base_dir, 'task_template.xml')

    def is_running_as_script(self) -> bool:
        """根据可执行文件名判断当前是否以脚本模式运行。"""
        return os.path.basename(self.executable_path).lower() in ('python.exe', 'pythonw.exe')