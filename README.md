# Trocker

**Trocker** is a desktop sports performance analysis tool built for researchers and coaches. It combines computer vision, homography transformation, and physiological metrics to extract precise movement data from video footage.

The name combines **"tracker"** with the Portuguese word **"troca"** (switch), reflecting the challenge of player identity swaps during tracking.

---

## 🛠️ Requirements

- Python 3.11
- - [FFmpeg](https://ffmpeg.org/download.html) (must be in system PATH)
  - - NVIDIA GPU with CUDA support (recommended)
    - - Windows 10/11
     
      - ---

      ## 🚀 Installation

      ```bash
      git clone https://github.com/MateoBalikian/trocker.git
      cd trocker

      # Create virtual environment
      python -m venv trockerv
      trockerv\Scripts\activate

      # Install dependencies
      pip install -r requirements.txt
      ```

      ---

      ## ▶️ Running

      ```bash
      trockerv\Scripts\activate
      python src/main.py
      ```

      ---

      ## 📦 Requirements.txt

      ```
      PySide6>=6.6.0
      opencv-python>=4.8.0
      numpy>=1.24.0
      pandas>=2.0.0
      matplotlib>=3.7.0
      scipy>=1.11.0
      ultralytics>=8.0.0
      boxmot>=10.0.0
      torch>=2.0.0
      torchvision>=0.15.0
      ```

      > **Note:** For GPU support, install PyTorch with CUDA from https://pytorch.org/get-started/locally/ before running `pip install -r requirements.txt`.
      >
      > ---
      >
      > ## ✨ Features
      >
      > | Module | Description |
      > |---|---|
      > | **Projects** | Organize videos and data by project |
      > | **Edit Video** | Cut, mask (paint area inside/outside polygon), export with GPU acceleration via FFmpeg |
      > | **Tracker** | YOLO11 detection + BoxMOT tracking (ByteTrack, StrongSORT, BoTSORT) |
      > | **Pixel Data** | Assign player names to tracked IDs frame by frame |
      > | **Homography** | Transform pixel coordinates to real-world meters (Grid or DLT mode) |
      > | **Reports** | Speed zones, distance, acceleration, VO₂max (Yo-Yo IR1/IR2/Endurance), fatigue index |
      > | **Trajectories** | Filter and visualize player trajectories with Kalman and Rolling Mean filters |
      > | **Athletes** | Player profiles (name, age, sex, weight) synced with Reports |
      > | **Trigger Zone** | Define polygon zones to filter tracking data to specific areas |
      >
      > ---
      >
      > ## 🔄 Data Pipeline
      >
      > ```
      > Video
      >   └─► Tracker (YOLO11 + BoxMOT)
      >         └─► pixel_coordinates CSV
      >               └─► Pixel Data (assign player names)
      >                     └─► players.json
      >               └─► Homography
      >                     └─► homography CSV (meters)
      >                           └─► [Trigger Zone — optional filter]
      >                                 └─► Reports (metrics + charts)
      >                                 └─► Trajectories (filters + plots)
      > ```
      >
      > ---
      >
      > ## 📁 Project Structure
      >
      > ```
      > trocker/
      > ├── src/
      > │   ├── main.py
      > │   ├── modules/
      > │   │   ├── tracker_engine.py       # YOLO + BoxMOT processing logic
      > │   │   ├── tracker_worker.py       # QThread wrapper for tracker
      > │   │   ├── edit_video.py           # Video editing + FFmpeg export
      > │   │   ├── homography_module.py    # Homography (Grid + DLT)
      > │   │   ├── getpixelcoord.py        # Player ID assignment
      > │   │   ├── reid.py                 # Re-identification / ID merging
      > │   │   ├── trigger_zone.py         # Zone selection and filtering
      > │   │   ├── reports.py              # Metrics and charts
      > │   │   ├── reports_plots.py        # Plot functions
      > │   │   ├── reports_metrics.py      # VO2max, fatigue, sprint calc
      > │   │   ├── trajectories.py         # Trajectories + heatmap viewer
      > │   │   ├── athlete_manager.py      # Athlete profiles
      > │   │   └── player_io.py            # Player JSON I/O
      > │   └── qml/
      > │       ├── main.qml
      > │       └── components/
      > │           ├── ProjectsPage.qml
      > │           ├── TrackerPage.qml
      > │           ├── ReportsPage.qml
      > │           └── ...
      > ├── models/                         # YOLO .pt files (not tracked in git)
      > ├── projects/                       # User project data (not tracked in git)
      > ├── requirements.txt
      > └── README.md
      > ```
      >
      > ---
      >
      > ## 🤖 Tech Stack
      >
      > - **UI:** QML + PySide6 (Qt 6)
      > - - **Detection:** Ultralytics YOLO11
      >   - - **Tracking:** BoxMOT (ByteTrack, StrongSORT, BoTSORT)
      >     - - **Video I/O:** OpenCV + FFmpeg (NVENC GPU acceleration)
      >       - - **Data:** NumPy, Pandas, SciPy
      >         - - **Charts:** Matplotlib
      >          
      >           - ---
      >
      > ## 📄 License
      >
      > MIT License
