import os
import shutil
from datetime import datetime
from PySide6.QtCore import QObject, Property, Signal, Slot


class ProjectsManager(QObject):
    projectsChanged = Signal()

    def __init__(self, projects_dir: str, parent=None):
        super().__init__(parent)
        self._projects_dir = projects_dir
        os.makedirs(projects_dir, exist_ok=True)

    def _scan(self) -> list:
        result = []
        if not os.path.isdir(self._projects_dir):
            return result
        for name in sorted(os.listdir(self._projects_dir)):
            path = os.path.join(self._projects_dir, name)
            if not os.path.isdir(path):
                continue
            video_exts = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

            # Conta vídeos na raiz E na subpasta videos/
            video_count = sum(
                1 for f in os.listdir(path)
                if os.path.splitext(f)[1].lower() in video_exts
            )
            videos_subdir = os.path.join(path, "videos")
            if os.path.isdir(videos_subdir):
                video_count += sum(
                    1 for f in os.listdir(videos_subdir)
                    if os.path.splitext(f)[1].lower() in video_exts
                )

            mtime = os.path.getmtime(path)
            date_str = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y")
            result.append({
                "name": name,
                "date": date_str,
                "videoCount": video_count,
                "path": path,
            })
        return result

    @Property(list, notify=projectsChanged)
    def projects(self):
        return self._scan()

    @Slot(str, result=bool)
    def createProject(self, name: str) -> bool:
        name = name.strip()
        if not name:
            return False
        path = os.path.join(self._projects_dir, name)
        if os.path.exists(path):
            return False
        os.makedirs(path)
        self.projectsChanged.emit()
        return True

    @Slot(str, str, result=bool)
    def renameProject(self, old_name: str, new_name: str) -> bool:
        new_name = new_name.strip()
        if not new_name or old_name == new_name:
            return False
        old_path = os.path.join(self._projects_dir, old_name)
        new_path = os.path.join(self._projects_dir, new_name)
        if not os.path.exists(old_path) or os.path.exists(new_path):
            return False
        os.rename(old_path, new_path)
        self.projectsChanged.emit()
        return True

    @Slot(str)
    def deleteProject(self, name: str):
        path = os.path.join(self._projects_dir, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
            self.projectsChanged.emit()
