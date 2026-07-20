// src/qml/components/HomographyPage.qml
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

Item {
    id: root
    property QtObject theme

    // ── Helpers ──────────────────────────────────────────────────────────────
    readonly property bool   hasActiveVideo:  videosManager ? videosManager.activeVideo !== "" : false
    readonly property string activeVideoPath: videosManager ? videosManager.activeVideoPath : ""
    readonly property string activeProjectPath: videosManager ? videosManager.activeProjectPath : ""

    // ── Background ───────────────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: theme.bg
    }

    // ── Scroll container ─────────────────────────────────────────────────────
    Flickable {
        anchors.fill: parent
        contentWidth:  parent.width
        contentHeight: mainColumn.implicitHeight + 64
        clip: true

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
            contentItem: Rectangle {
                implicitWidth: 4
                radius: 2
                color: Qt.rgba(1,1,1,0.12)
            }
        }

        Column {
            id: mainColumn
            x: 40
            y: 36
            width: parent.width - 80
            spacing: 0

            // ── Page header ──────────────────────────────────────────────────
            Item {
                width: parent.width
                height: 72

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4

                    Text {
                        text: "Homography"
                        font.family:      theme.fontDisplay
                        font.weight:      Font.Bold
                        font.pixelSize:   34
                        font.letterSpacing: 1
                        color: theme.textPrimary
                    }
                    Text {
                        text: "Transform pixel coordinates to real-world field coordinates"
                        font.family:    theme.fontBody
                        font.pixelSize: 11
                        color: theme.textMuted
                    }
                }
            }

            // ── Active video card ─────────────────────────────────────────────
            Rectangle {
                id: videoCard
                width: parent.width
                height: 64
                radius: 12
                color: theme.surface
                border.color: hasActiveVideo
                              ? Qt.rgba(66/255, 130/255, 255/255, 0.45)
                              : theme.border
                border.width: 1

                Behavior on border.color { ColorAnimation { duration: 250 } }

                Row {
                    anchors.left:           parent.left
                    anchors.leftMargin:     20
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 14

                    Rectangle {
                        width: 8; height: 8; radius: 4
                        anchors.verticalCenter: parent.verticalCenter
                        color: hasActiveVideo ? theme.accent : theme.textMuted

                        SequentialAnimation on opacity {
                            running: hasActiveVideo
                            loops:   Animation.Infinite
                            NumberAnimation { from: 1.0; to: 0.25; duration: 900; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 0.25; to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                            onStopped: parent.opacity = 1
                        }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2

                        Text {
                            text: hasActiveVideo
                                  ? (videosManager.activeProjectName !== ""
                                     ? videosManager.activeProjectName + "  ·  " + videosManager.activeVideo
                                     : videosManager.activeVideo)
                                  : "No active video"
                            font.family:    theme.fontBody
                            font.pixelSize: 12
                            font.weight:    hasActiveVideo ? Font.SemiBold : Font.Normal
                            color: hasActiveVideo ? theme.textPrimary : theme.textMuted
                        }

                        Text {
                            visible: hasActiveVideo
                            text: activeVideoPath
                            font.family:    theme.fontBody
                            font.pixelSize: 9
                            color: theme.textMuted
                            elide: Text.ElideLeft
                            width: videoCard.width - 140
                        }
                    }
                }

                Text {
                    visible: !hasActiveVideo
                    anchors.right:          parent.right
                    anchors.rightMargin:    20
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Open a project and activate a video →"
                    font.family:    theme.fontBody
                    font.pixelSize: 10
                    color: theme.textMuted
                }
            }

            Item { width: 1; height: 28 }

            // ── Warning banner (sem vídeo ativo) ──────────────────────────────
            Rectangle {
                width:  parent.width
                height: !hasActiveVideo ? 48 : 0
                radius: 10
                color:  Qt.rgba(1, 0.75, 0.1, 0.07)
                border.color: Qt.rgba(1, 0.75, 0.1, 0.25)
                border.width: 1
                clip: true
                visible: height > 0

                Behavior on height { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

                Text {
                    anchors.centerIn: parent
                    text: "Select an active video to use the Homography tools"
                    font.family:    theme.fontBody
                    font.pixelSize: 11
                    color: "#f5c842"
                }
            }

            Item { width: 1; height: !hasActiveVideo ? 16 : 0 }

            // ── Section label ─────────────────────────────────────────────────
            Text {
                text: "CAMERA MODE"
                font.family:      theme.fontBody
                font.pixelSize:   10
                font.weight:      Font.Medium
                font.letterSpacing: 1.2
                color: theme.textMuted
                bottomPadding: 10
            }

            // ── Fixed Camera card ─────────────────────────────────────────────
            Rectangle {
                width:  parent.width
                height: 80
                radius: 12
                color:  fixedMouse.containsMouse && hasActiveVideo ? theme.surface2 : theme.surface
                border.color: theme.border
                border.width: 1
                opacity: hasActiveVideo ? 1.0 : 0.45

                Behavior on color   { ColorAnimation { duration: 150 } }
                Behavior on opacity { NumberAnimation { duration: 150 } }

                Row {
                    anchors.left:           parent.left
                    anchors.leftMargin:     20
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 16

                    Rectangle {
                        width: 40; height: 40; radius: 10
                        color: Qt.rgba(66/255, 130/255, 255/255, 0.12)
                        anchors.verticalCenter: parent.verticalCenter
                        Text { anchors.centerIn: parent; text: "📷"; font.pixelSize: 18 }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3
                        Text {
                            text: "Fixed Camera"
                            font.family:    theme.fontBody
                            font.pixelSize: 13
                            font.weight:    Font.SemiBold
                            color: theme.textPrimary
                        }
                        Text {
                            text: "Select 4 points on the frame to define the field boundaries"
                            font.family:    theme.fontBody
                            font.pixelSize: 10
                            color: theme.textMuted
                        }
                    }
                }

                Text {
                    anchors.right:          parent.right
                    anchors.rightMargin:    20
                    anchors.verticalCenter: parent.verticalCenter
                    text: "›"
                    font.pixelSize: 22
                    color: hasActiveVideo ? theme.accent : theme.textMuted
                }

                MouseArea {
                    id: fixedMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape:  hasActiveVideo ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        if (!hasActiveVideo) return
                        homographyManager.open_tool(activeVideoPath, activeProjectPath)
                    }
                }
            }

            Item { width: 1; height: 12 }

            // ── Pre-selected card ─────────────────────────────────────────────
            Rectangle {
                width:  parent.width
                height: 80
                radius: 12
                color:  preselMouse.containsMouse && hasActiveVideo ? theme.surface2 : theme.surface
                border.color: theme.border
                border.width: 1
                opacity: hasActiveVideo ? 1.0 : 0.45

                Behavior on color   { ColorAnimation { duration: 150 } }
                Behavior on opacity { NumberAnimation { duration: 150 } }

                Row {
                    anchors.left:           parent.left
                    anchors.leftMargin:     20
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 16

                    Rectangle {
                        width: 40; height: 40; radius: 10
                        color: Qt.rgba(80/255, 200/255, 120/255, 0.12)
                        anchors.verticalCenter: parent.verticalCenter
                        Text { anchors.centerIn: parent; text: "♻️"; font.pixelSize: 18 }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3
                        Text {
                            text: "Pre-selected Points"
                            font.family:    theme.fontBody
                            font.pixelSize: 13
                            font.weight:    Font.SemiBold
                            color: theme.textPrimary
                        }
                        Text {
                            text: "Reuse a previously saved homography matrix (JSON)"
                            font.family:    theme.fontBody
                            font.pixelSize: 10
                            color: theme.textMuted
                        }
                    }
                }

                Text {
                    anchors.right:          parent.right
                    anchors.rightMargin:    20
                    anchors.verticalCenter: parent.verticalCenter
                    text: "›"
                    font.pixelSize: 22
                    color: hasActiveVideo ? theme.accent : theme.textMuted
                }

                MouseArea {
                    id: preselMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape:  hasActiveVideo ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        if (!hasActiveVideo) return
                        homographyManager.open_preselected(activeVideoPath, activeProjectPath)
                    }
                }
            }

            Item { width: 1; height: 12 }

            // ── Trigger Zone card ─────────────────────────────────────────────
            Rectangle {
                width:  parent.width
                height: 100
                radius: 12
                color:  theme.surface
                border.color: theme.border
                border.width: 1
                opacity: hasActiveVideo ? 1.0 : 0.45
                Behavior on opacity { NumberAnimation { duration: 150 } }

                Row {
                    anchors.left:           parent.left
                    anchors.leftMargin:     20
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 16

                    Rectangle {
                        width: 40; height: 40; radius: 10
                        color: Qt.rgba(255/255, 152/255, 48/255, 0.12)
                        anchors.verticalCenter: parent.verticalCenter
                        Text { anchors.centerIn: parent; text: "📍"; font.pixelSize: 18 }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6

                        Text {
                            text: "Trigger Zone"
                            font.family:    theme.fontBody
                            font.pixelSize: 13
                            font.weight:    Font.SemiBold
                            color: theme.textPrimary
                        }

                        Row {
                            spacing: 8

                            Rectangle {
                                width: 130; height: 28; radius: 7
                                color: definirHov && hasActiveVideo ? theme.surface3 : theme.surface2
                                border.color: theme.border; border.width: 1
                                Behavior on color { ColorAnimation { duration: 120 } }
                                property bool definirHov: false

                                Text {
                                    anchors.centerIn: parent
                                    text: "📍 Definir Zona"
                                    font.family:    theme.fontBody
                                    font.pixelSize: 10
                                    font.weight:    Font.Medium
                                    color: hasActiveVideo ? theme.textPrimary : theme.textMuted
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: hasActiveVideo ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onEntered:  parent.definirHov = true
                                    onExited:   parent.definirHov = false
                                    onClicked: {
                                        if (!hasActiveVideo) return
                                        homographyManager.open_trigger_zone(activeVideoPath, activeProjectPath)
                                    }
                                }
                            }

                            Rectangle {
                                width: 130; height: 28; radius: 7
                                color: aplicarHov && hasActiveVideo ? theme.surface3 : theme.surface2
                                border.color: theme.border; border.width: 1
                                Behavior on color { ColorAnimation { duration: 120 } }
                                property bool aplicarHov: false

                                Text {
                                    anchors.centerIn: parent
                                    text: "✂ Aplicar Zona"
                                    font.family:    theme.fontBody
                                    font.pixelSize: 10
                                    font.weight:    Font.Medium
                                    color: hasActiveVideo ? theme.textPrimary : theme.textMuted
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: hasActiveVideo ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onEntered:  parent.aplicarHov = true
                                    onExited:   parent.aplicarHov = false
                                    onClicked: {
                                        if (!hasActiveVideo) return
                                        homographyManager.apply_trigger_zone_slot(activeVideoPath, activeProjectPath)
                                    }
                                }
                            }

                            Rectangle {
                                width: 130; height: 28; radius: 7
                                color: verHov && hasActiveVideo ? theme.surface3 : theme.surface2
                                border.color: theme.border; border.width: 1
                                Behavior on color { ColorAnimation { duration: 120 } }
                                property bool verHov: false

                                Text {
                                    anchors.centerIn: parent
                                    text: "👁 Ver Zona"
                                    font.family:    theme.fontBody
                                    font.pixelSize: 10
                                    font.weight:    Font.Medium
                                    color: hasActiveVideo ? theme.textPrimary : theme.textMuted
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: hasActiveVideo ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onEntered:  parent.verHov = true
                                    onExited:   parent.verHov = false
                                    onClicked: {
                                        if (!hasActiveVideo) return
                                        homographyManager.open_zone_viewer(activeVideoPath, activeProjectPath)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item { width: 1; height: 12 }

            // ── Broadcast Camera (em breve) ───────────────────────────────────
            Rectangle {
                width:  parent.width
                height: 80
                radius: 12
                color:  theme.surface
                border.color: theme.border
                border.width: 1
                opacity: 0.4

                Row {
                    anchors.left:           parent.left
                    anchors.leftMargin:     20
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 16

                    Rectangle {
                        width: 40; height: 40; radius: 10
                        color: Qt.rgba(1,1,1,0.05)
                        anchors.verticalCenter: parent.verticalCenter
                        Text { anchors.centerIn: parent; text: "📡"; font.pixelSize: 18 }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3

                        Row {
                            spacing: 8
                            Text {
                                text: "Broadcast Camera"
                                font.family:    theme.fontBody
                                font.pixelSize: 13
                                font.weight:    Font.SemiBold
                                color: theme.textPrimary
                            }
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width:  lbl.implicitWidth + 12
                                height: 18
                                radius: 4
                                color:  Qt.rgba(1,1,1,0.07)
                                Text {
                                    id: lbl
                                    anchors.centerIn: parent
                                    text: "Em breve"
                                    font.family:    theme.fontBody
                                    font.pixelSize: 9
                                    font.weight:    Font.Medium
                                    color: theme.textMuted
                                }
                            }
                        }

                        Text {
                            text: "Per-frame homography for moving cameras"
                            font.family:    theme.fontBody
                            font.pixelSize: 10
                            color: theme.textMuted
                        }
                    }
                }
            }

            Item { width: 1; height: 40 }
        }
    }
}
