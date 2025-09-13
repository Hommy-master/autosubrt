# 项目常量定义
import os


# 临时目录，用在缓存临时文件
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
VIDEO_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "video")
SRT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "srt")

# 将容器内的文件路径转成一个下载路径，执行替换操作，即将/app/ -> https://autosubrt.jcaigc.cn/
DOWNLOAD_URL = os.getenv("DOWNLOAD_URL", "https://autosubrt.jcaigc.cn/")
