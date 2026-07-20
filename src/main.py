import sys
import os
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine

from modules.projects_manager import ProjectsManager
from modules.videos_manager import VideosManager
from modules.tracker_worker import TrackerWorker
from modules.homography_module import HomographyManager
from modules.getpixelcoord import GetPixelCoordManager
from modules.reid import ReidManager
from modules.edit_video import EditVideoManager
from modules.reports import ReportsManager
from modules.athlete_manager import AthleteManager
from modules.trajectories import TrajectoriesManager

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR  = os.path.join(BASE_DIR, "fonts")
QML_MAIN   = os.path.join(BASE_DIR, "src", "qml", "main.qml")
ICON_PATH  = os.path.join(BASE_DIR, "assets", "trocker.ico")
PROJ_DIR   = os.path.join(BASE_DIR, "projects")

app = QApplication(sys.argv)

for font_file in os.listdir(FONTS_DIR):
    if font_file.endswith((".ttf", ".otf")):
        QFontDatabase.addApplicationFont(os.path.join(FONTS_DIR, font_file))

app.setWindowIcon(QIcon(ICON_PATH))

projects_manager = ProjectsManager(PROJ_DIR)
videos_manager   = VideosManager()
tracker_worker   = TrackerWorker()
homography_manager    = HomographyManager()
getpixelcoord_manager = GetPixelCoordManager(videos_manager, projects_manager)
reid_manager          = ReidManager(videos_manager, projects_manager)
edit_video_manager    = EditVideoManager(videos_manager)
athlete_manager       = AthleteManager(videos_manager)
reports_manager       = ReportsManager(videos_manager, athlete_manager)
trajectories_manager  = TrajectoriesManager(videos_manager)

engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("projectsManager", projects_manager)
engine.rootContext().setContextProperty("videosManager",   videos_manager)
engine.rootContext().setContextProperty("trackerWorker",   tracker_worker)
engine.rootContext().setContextProperty("homographyManager",     homography_manager)
engine.rootContext().setContextProperty("getpixelcoordManager",  getpixelcoord_manager)
engine.rootContext().setContextProperty("reidManager",           reid_manager)
engine.rootContext().setContextProperty("editVideoManager",      edit_video_manager)
engine.rootContext().setContextProperty("athleteManager",        athlete_manager)
engine.rootContext().setContextProperty("reportsManager",        reports_manager)
engine.rootContext().setContextProperty("trajectoriesManager",   trajectories_manager)
engine.load(QML_MAIN)

if not engine.rootObjects():
    print(f"[ERROR] Failed to load QML: {QML_MAIN}", file=sys.stderr)
    sys.exit(1)

sys.exit(app.exec())
