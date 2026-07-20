// src/qml/Sidebar.qml
import QtQuick
import QtQuick.Controls

Item {
    id: root

    // ── Props ──────────────────────────────────────────────────────────────
    property QtObject theme
    property bool collapsed:   false
    property int  activeIndex: 0

    signal navSelected(int index)
    signal toggleCollapse()

    // ── Dimensions ─────────────────────────────────────────────────────────
    width:  collapsed ? theme.sidebarCollapsed : theme.sidebarExpanded
    height: parent ? parent.height : 0
    Behavior on width { NumberAnimation { duration: theme.collapseMs; easing.type: Easing.OutCubic } }

    // ── Nav model ──────────────────────────────────────────────────────────
    property var navItems: [
        { label: "Projects",   icon: "⊞" },
        { label: "Edit Video", icon: "✦" },
        { label: "Tracker",    icon: "◎" },
        { label: "Pixel Data", icon: "⌖" },
        { label: "Homography", icon: "⌗" },
        { label: "Reports",    icon: "▤" },
        { label: "Athletes",   icon: "◉" },
        { label: "Settings",   icon: "⚙" }
    ]

    // ── Surface ────────────────────────────────────────────────────────────
    Rectangle {
        id: surface
        anchors.fill: parent
        color: theme.surface

        // Right border
        Rectangle {
            anchors.top:    parent.top
            anchors.right:  parent.right
            anchors.bottom: parent.bottom
            width: 1
            color: theme.border
        }

        // ── Header ────────────────────────────────────────────────────────
        Item {
            id: header
            anchors.top:   parent.top
            anchors.left:  parent.left
            anchors.right: parent.right
            height: 110

            // Logo mark — centralizes when collapsed
            Rectangle {
                id: logoMark
                width: 28; height: 28; radius: 7
                color: theme.accent
                anchors.verticalCenter: parent.verticalCenter
                anchors.left:              root.collapsed ? undefined : parent.left
                anchors.leftMargin:        root.collapsed ? 0 : 16
                anchors.horizontalCenter:  root.collapsed ? parent.horizontalCenter : undefined

                Text {
                    anchors.centerIn: parent
                    text:           "T"
                    font.family:    theme.fontDisplay
                    font.weight:    Font.Bold
                    font.pixelSize: 16
                    color:          "white"
                }
            }

            // Wordmark
            Text {
                anchors.left:           logoMark.right
                anchors.leftMargin:     10
                anchors.verticalCenter: parent.verticalCenter
                text:             "TROCKER"
                font.family:      theme.fontDisplay
                font.weight:      Font.Bold
                font.pixelSize:   17
                font.letterSpacing: 3
                color:            theme.textPrimary
                opacity:          root.collapsed ? 0 : 1
                Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
            }

            // Active video badge
            Rectangle {
                id: activeBadge
                anchors.left:        parent.left
                anchors.right:       parent.right
                anchors.leftMargin:  14
                anchors.rightMargin: 14
                anchors.bottom:      parent.bottom
                anchors.bottomMargin: 10
                height: 26
                radius: 7
                color:  theme.surface2
                border.color: hasActiveVideo
                              ? Qt.rgba(66/255, 130/255, 255/255, 0.40)
                              : theme.border
                border.width: 1
                opacity: root.collapsed ? 0 : 1
                Behavior on border.color { ColorAnimation { duration: 250 } }
                Behavior on opacity      { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

                // Computed badge state from QML context
                property bool   hasActiveVideo: videosManager ? videosManager.activeVideo   !== "" : false
                property string activeVidName:  videosManager ? videosManager.activeVideo         : ""
                property string activeProjName: videosManager ? videosManager.activeProjectName   : ""

                property string badgeText: {
                    if (hasActiveVideo)
                        return (activeProjName !== "" ? activeProjName + " · " : "") + activeVidName
                    if (activeProjName !== "")
                        return activeProjName
                    return "No active video"
                }

                Row {
                    anchors.left:           parent.left
                    anchors.leftMargin:     9
                    anchors.right:          parent.right
                    anchors.rightMargin:    9
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 7

                    // Pulsing dot
                    Rectangle {
                        id: statusDot
                        width: 6; height: 6; radius: 3
                        anchors.verticalCenter: parent.verticalCenter
                        color: activeBadge.hasActiveVideo
                               ? theme.green
                               : Qt.rgba(
                                   theme.textMuted.r,
                                   theme.textMuted.g,
                                   theme.textMuted.b,
                                   0.45
                                 )
                        Behavior on color { ColorAnimation { duration: 300 } }

                        SequentialAnimation on opacity {
                            running:  activeBadge.hasActiveVideo
                            loops:    Animation.Infinite
                            NumberAnimation { from: 1.0; to: 0.35; duration: 900; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 0.35; to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                            onStopped: statusDot.opacity = 1
                        }
                    }

                    Text {
                        width:          parent.width - statusDot.width - parent.spacing
                        text:           activeBadge.badgeText
                        font.family:    theme.fontBody
                        font.pixelSize: 10
                        font.weight:    activeBadge.hasActiveVideo ? Font.SemiBold : Font.Normal
                        color:          activeBadge.hasActiveVideo ? theme.textPrimary : theme.textMuted
                        elide:          Text.ElideRight
                        anchors.verticalCenter: parent.verticalCenter
                        Behavior on color { ColorAnimation { duration: 250 } }
                    }
                }
            }
        }

        // Header divider
        Rectangle {
            id: headerDivider
            anchors.top:         header.bottom
            anchors.left:        parent.left
            anchors.right:       parent.right
            anchors.leftMargin:  12
            anchors.rightMargin: 12
            height: 1
            color:  theme.border
        }

        // ── Nav section ───────────────────────────────────────────────────
        Column {
            id: navCol
            anchors.top:        headerDivider.bottom
            anchors.left:       parent.left
            anchors.right:      parent.right
            anchors.topMargin:  10
            spacing: 2

            // Section label
            Text {
                width:               parent.width
                leftPadding:         root.collapsed ? 0 : 20
                horizontalAlignment: root.collapsed ? Text.AlignHCenter : Text.AlignLeft
                bottomPadding:       4
                text:             "MENU"
                font.family:      theme.fontBody
                font.pixelSize:   8
                font.weight:      Font.SemiBold
                font.letterSpacing: 2
                color:            theme.textMuted
                opacity:          root.collapsed ? 0 : 0.6
                Behavior on opacity { NumberAnimation { duration: 180 } }
            }

            // Nav items
            Repeater {
                model: root.navItems
                delegate: NavItem {
                    theme:     root.theme
                    label:     modelData.label
                    icon:      modelData.icon
                    active:    index === root.activeIndex
                    collapsed: root.collapsed
                    width:     navCol.width
                    height:    42
                    onClicked: root.navSelected(index)
                }
            }
        }

        // Footer divider
        Rectangle {
            anchors.bottom:      userRow.top
            anchors.left:        parent.left
            anchors.right:       parent.right
            anchors.leftMargin:  12
            anchors.rightMargin: 12
            height: 1
            color:  theme.border
        }

        // ── User row ──────────────────────────────────────────────────────
        Item {
            id: userRow
            anchors.bottom: parent.bottom
            anchors.left:   parent.left
            anchors.right:  parent.right
            height: 52

            // Avatar
            Rectangle {
                id: avatar
                width: 26; height: 26; radius: 13
                color: theme.surface3
                border.color: theme.borderHover
                border.width: 1
                anchors.verticalCenter: parent.verticalCenter
                anchors.left:             root.collapsed ? undefined : parent.left
                anchors.leftMargin:       root.collapsed ? 0 : 14
                anchors.horizontalCenter: root.collapsed ? parent.horizontalCenter : undefined

                Text {
                    anchors.centerIn: parent
                    text:           "M"
                    font.family:    theme.fontBody
                    font.pixelSize: 10
                    font.weight:    Font.SemiBold
                    color:          theme.textSecondary
                }
            }

            Text {
                anchors.left:           avatar.right
                anchors.leftMargin:     9
                anchors.verticalCenter: parent.verticalCenter
                text:           "mateo"
                font.family:    theme.fontBody
                font.pixelSize: 12
                color:          theme.textSecondary
                opacity:        root.collapsed ? 0 : 1
                Behavior on opacity { NumberAnimation { duration: 200 } }
            }
        }

        // ── Collapse toggle button ────────────────────────────────────────
        Rectangle {
            id: collapseBtn
            anchors.right:          parent.right
            anchors.rightMargin:    -14
            anchors.verticalCenter: parent.verticalCenter
            width: 28; height: 28; radius: 14
            color:        btnHovered ? theme.surface2 : theme.surface
            border.color: theme.border
            border.width: 1
            z: 10

            Behavior on color { ColorAnimation { duration: 150 } }

            property bool btnHovered: false

            Text {
                anchors.centerIn: parent
                text:           root.collapsed ? "›" : "‹"
                font.pixelSize: 13
                color:          theme.textMuted
            }

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape:  Qt.PointingHandCursor
                onEntered: parent.btnHovered = true
                onExited:  parent.btnHovered = false
                onClicked: root.toggleCollapse()
            }
        }
    }
}
