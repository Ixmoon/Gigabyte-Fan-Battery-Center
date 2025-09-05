import os

class PathManager:
    """
    一个中心化的路径管理器，用于生成和存储应用程序所需的所有文件和目录路径。
    """
    def __init__(self, base_dir: str):
        """
        使用应用程序的根目录初始化路径管理器。

        Args:
            base_dir (str): 应用程序的根目录 (BASE_DIR)。
        """
        self.base_dir = base_dir

        # --- 核心配置文件 ---
        self.control_config = os.path.join(self.base_dir, 'control_config.json')
        self.languages = os.path.join(self.base_dir, 'languages.json')

        # --- GUI 相关文件 ---
        self.style_qss = os.path.join(self.base_dir, 'gui', 'style.qss')
        
        # --- 图标 ---
        self.app_icon = os.path.join(self.base_dir, 'app_icon.ico')

        # --- 任务计划程序模板 ---
        self.task_template = os.path.join(self.base_dir, 'task_template.xml')

        # 可以根据需要添加更多路径，例如日志目录、临时文件目录等
        # self.log_dir = os.path.join(self.base_dir, 'logs')
        # self._ensure_dir_exists(self.log_dir)

    def _ensure_dir_exists(self, path: str):
        """确保指定的目录存在，如果不存在则创建它。"""
        if not os.path.exists(path):
            os.makedirs(path)
