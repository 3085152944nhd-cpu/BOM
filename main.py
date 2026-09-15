import sys
import os
import configparser
import shutil
import yaml
import logging
import logging.handlers
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QInputDialog, QLineEdit
from PySide6.QtGui import QIcon
from database.db_manager import DBManager
from gui.main_window import MainWindow

# ---------- 全局 logger ----------
logger = None

# ---------- 日志初始化 ----------
def setup_logging(db_path):
    """
    根据数据库路径初始化日志系统。
    日志将存放在数据库所在目录下的 logs 子文件夹中。
    """
    global logger
    # 获取数据库所在目录
    db_dir = os.path.dirname(db_path)
    if not db_dir:
        db_dir = os.getcwd()
    # 在该目录下创建 logs 文件夹
    log_dir = os.path.join(db_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "operation.log")

    logger = logging.getLogger('InventoryManager')
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.info("===== 程序启动 =====")
    logger.info(f"数据库路径: {db_path}")
    logger.info(f"日志文件: {log_file}")
    return logger

# ---------- 路径工具 ----------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_user_data_dir():
    """用户数据目录（用于存放配置文件，不用于存放日志）"""
    appdata = os.environ.get('APPDATA', os.path.expanduser("~"))
    data_dir = os.path.join(appdata, "InventoryManager")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def get_config_path():
    return os.path.join(get_user_data_dir(), "config.yaml")

def load_config():
    config_path = get_config_path()
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}

def save_config(config):
    config_path = get_config_path()
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True)

def ensure_config_exists():
    config_path = get_config_path()
    if os.path.exists(config_path):
        return
    default_config = {
        'openai_api_key': '',
        'openai_base_url': 'https://api.deepseek.com/v1',
        'ai_model': 'deepseek-chat',
        'database': 'data/inventory.db',
        'theme': {
            'alpha': 102,
            'alpha_percent': 40,
            'auto_font': False,
            'background_color': '#ffffff',
            'background_image': '',
            'background_type': 'color',
            'font_color': '#000000'
        }
    }
    save_config(default_config)
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    key, ok = QInputDialog.getText(
        None,
        "设置 AI API Key",
        "请输入您的 DeepSeek 或 OpenAI API Key（如不需要 AI 功能，可留空）：",
        QLineEdit.Normal,
        ""
    )
    if ok and key.strip():
        config = load_config()
        config['openai_api_key'] = key.strip()
        save_config(config)
        QMessageBox.information(None, "提示", "API Key 已保存，AI 功能已启用。")
        if logger:
            logger.info("用户设置了 API Key")
    else:
        QMessageBox.information(None, "提示", "您已跳过设置 API Key，AI 功能将被禁用。")
        if logger:
            logger.info("用户跳过了 API Key 设置")

# ---------- 数据库路径获取 ----------
def get_db_path_from_installer():
    exe_dir = os.path.dirname(sys.executable)
    config_file = os.path.join(exe_dir, "db_config.ini")
    if not os.path.exists(config_file):
        return None

    config = configparser.ConfigParser()
    try:
        with open(config_file, 'r', encoding='gbk') as f:
            content = f.read()
        # 去除可能的重复节
        lines = content.splitlines()
        new_lines = []
        found_section = False
        for line in lines:
            if line.strip().lower() == '[settings]':
                if found_section:
                    continue
                found_section = True
            new_lines.append(line)
        clean_content = '\n'.join(new_lines)
        config.read_string(clean_content)
    except Exception:
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
            lines = content.splitlines()
            new_lines = []
            found_section = False
            for line in lines:
                if line.strip().lower() == '[settings]':
                    if found_section:
                        continue
                    found_section = True
                new_lines.append(line)
            clean_content = '\n'.join(new_lines)
            config.read_string(clean_content)
        except Exception as e:
            print(f"读取 db_config.ini 失败: {e}")
            return None

    if config.has_section('Settings') and config.has_option('Settings', 'db_path'):
        return config.get('Settings', 'db_path')
    return None

def get_database_path():
    # 1. 安装程序配置的路径
    db_path = get_db_path_from_installer()
    if db_path:
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        return db_path

    # 2. 从用户配置文件读取
    config = load_config()
    db_path = config.get('database_path', '')
    if db_path and (os.path.exists(os.path.dirname(db_path)) or not os.path.exists(db_path)):
        return db_path

    # 3. 首次运行，询问用户
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    reply = QMessageBox.question(
        None,
        "数据库位置",
        "您是否希望自定义数据库文件（inventory.db）的存放位置？\n"
        "若选择“是”，将弹出文件选择框；\n"
        "若选择“否”，将使用默认位置（用户数据目录）。",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )

    if reply == QMessageBox.Yes:
        folder = QFileDialog.getExistingDirectory(
            None,
            "选择数据库存放文件夹",
            os.path.expanduser("~")
        )
        if folder:
            db_path = os.path.join(folder, "inventory.db")
            config['database_path'] = db_path
            save_config(config)
            if logger:
                logger.info(f"用户选择数据库目录: {folder}")
            return db_path

    data_dir = get_user_data_dir()
    default_db = os.path.join(data_dir, "inventory.db")
    config['database_path'] = default_db
    save_config(config)
    if logger:
        logger.info(f"使用默认数据库路径: {default_db}")
    return default_db

# ---------- 主入口 ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 设置窗口图标
    icon_path = resource_path("app_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 确保配置文件存在（会在用户目录创建 config.yaml）
    ensure_config_exists()

    # 获取数据库路径（这里可能会弹出用户交互对话框）
    db_path = get_database_path()

    # ---------- 关键步骤：根据数据库路径初始化日志 ----------
    logger = setup_logging(db_path)

    # 确保数据库目录存在
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    # 复制默认配置文件到用户目录（如果不存在）
    config_src = resource_path("config.yaml")
    config_dst = os.path.join(get_user_data_dir(), "config.yaml")
    if os.path.exists(config_src) and not os.path.exists(config_dst):
        shutil.copy2(config_src, config_dst)

    db = DBManager(db_path)
    window = MainWindow(db)
    window.show()
    sys.exit(app.exec())