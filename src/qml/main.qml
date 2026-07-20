// src/qml/main.qml
import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import "components"

Window {
    id: root
    width:  1280
    height: 800
    minimumWidth:  960
    minimumHeight: 600
    title:   "Trocker"
    visible: true

    property bool collapsed:   false
    property int  activeIndex: 0

    Theme { id: theme }

    // Eliminate white flash: set colour before anything is drawn
    color: theme.bg

    Rectangle {
        anchors.fill: parent
        color:        theme.bg

        // ── Sidebar ───────────────────────────────────────────────────────────
        Sidebar {
            id: sidebar
            anchors.top:    parent.top
            anchors.left:   parent.left
            anchors.bottom: parent.bottom
            theme:          theme
            collapsed:      root.collapsed
            activeIndex:    root.activeIndex
            onNavSelected:    (i) => root.activeIndex = i
            onToggleCollapse: root.collapsed = !root.collapsed
        }

        // ── Page stack ────────────────────────────────────────────────────────
        StackLayout {
            anchors.left:   sidebar.right
            anchors.top:    parent.top
            anchors.right:  parent.right
            anchors.bottom: parent.bottom
            currentIndex:   root.activeIndex

            // 0 — Projects
            ProjectsPage {
                theme: theme
            }

            // 1 — Edit Video
            EditVideoPage {
                theme: theme
            }

            // 2 — Tracker
            TrackerPage {
                theme: theme
            }

            // 3 — Pixel Data
            PixelDataPage {
                theme: theme
            }

            // 4 — Homography
            HomographyPage {
                theme: theme
            }

            // 5 — Reports
            ReportsPage {
                theme: theme
            }

            // 6 — Athletes
            AthletesPage {
                theme: theme
            }

            // 7 — Settings (placeholder)
            Item {
                Column {
                    anchors.centerIn: parent
                    spacing: 8
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text:               "Settings"
                        font.family:        theme.fontDisplay
                        font.weight:        Font.Normal
                        font.pixelSize:     56
                        font.letterSpacing: 2
                        color:              theme.textPrimary
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text:           "content area"
                        font.family:    theme.fontBody
                        font.pixelSize: 12
                        color:          theme.textMuted
                    }
                }
            }
        }
    }
}
