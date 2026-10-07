"""测试公共配置

项目是平铺布局（`import config` 这类顶层导入），因此在收集测试前先导入本文件，
把项目根目录加入 sys.path。

运行：`uv run pytest tests -q`
"""

import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
