"""主入口脚本 — 启动课堂注意力检测系统。"""

import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gui.main_window import MainWindow


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config_path = PROJECT_ROOT / "config" / "default.json"
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 跨平台一致的样式

    window = MainWindow(config_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
