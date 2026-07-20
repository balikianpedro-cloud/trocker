// src/qml/components/AthletesPage.qml
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

Item {
    id: root
    property QtObject theme

    readonly property bool hasActiveVideo: videosManager ? videosManager.activeVideo !== "" : false

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
                        text: "Athletes"
                        font.family:      theme.fontDisplay
                        font.weight:      Font.Bold
                        font.pixelSize:   34
                        font.letterSpacing: 1
                        color: theme.textPrimary
                    }
                    Text {
                        text: "Manage player profiles and physical data"
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
                            text: videosManager ? videosManager.activeVideoPath : ""
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

            // ── Warning banner ────────────────────────────────────────────────
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
                    text: "Select an active video to manage athlete profiles"
                    font.family:    theme.fontBody
                    font.pixelSize: 11
                    color: "#f5c842"
                }
            }

            Item { width: 1; height: !hasActiveVideo ? 16 : 0 }

            // ── Open Editor card ──────────────────────────────────────────────
            Rectangle {
                width:  parent.width
                height: 80
                radius: 12
                color:  editorMouse.containsMouse && hasActiveVideo ? theme.surface2 : theme.surface
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
                        Text { anchors.centerIn: parent; text: "◉"; font.pixelSize: 20; color: theme.accent }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3
                        Text {
                            text: "Open Athlete Editor"
                            font.family:    theme.fontBody
                            font.pixelSize: 13
                            font.weight:    Font.SemiBold
                            color: theme.textPrimary
                        }
                        Text {
                            text: "Edit player names, age, sex, and weight for this video"
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
                    id: editorMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape:  hasActiveVideo ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        if (!hasActiveVideo) return
                        athleteManager.open_tool()
                    }
                }
            }

            Item { width: 1; height: 40 }
        }
    }
}
