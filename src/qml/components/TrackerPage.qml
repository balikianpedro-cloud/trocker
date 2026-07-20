// src/qml/components/TrackerPage.qml
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

Item {
    id: root
    property QtObject theme

    // ── Helpers ──────────────────────────────────────────────────────────────
    readonly property bool   hasActiveVideo:  videosManager ? videosManager.activeVideo !== "" : false
    readonly property string activeVideoPath: videosManager ? videosManager.activeVideoPath : ""

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
                        text: "Tracker"
                        font.family:      theme.fontDisplay
                        font.weight:      Font.Bold
                        font.pixelSize:   34
                        font.letterSpacing: 1
                        color: theme.textPrimary
                    }
                    Text {
                        text: "Detect and track players using YOLO + BoxMOT"
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

                    // Dot indicator
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

            Item { width: 1; height: 24 }

            // ── Settings ──────────────────────────────────────────────────────
            Column {
                width:   parent.width
                spacing: 16

                // Row 1 — Model + Tracker
                Row {
                    width:   parent.width
                    spacing: 16

                    Column {
                        width:   (parent.width - 16) / 2
                        spacing: 6
                        FieldLabel { text: "YOLO Model"; width: parent.width }
                        DropDown {
                            id:      modelCombo
                            theme:   root.theme
                            width:   parent.width
                            model:   ["yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt", "yolo11x.pt"]
                            current: 0
                        }
                    }

                    Column {
                        width:   (parent.width - 16) / 2
                        spacing: 6
                        FieldLabel { text: "Tracker"; width: parent.width }
                        DropDown {
                            id:      trackerCombo
                            theme:   root.theme
                            width:   parent.width
                            model:   ["bytetrack", "botsort", "strongsort"]
                            current: 0
                        }
                    }
                }

                // Row 2 — Confidence + IoU
                Row {
                    width:   parent.width
                    spacing: 16

                    Column {
                        width:   (parent.width - 16) / 2
                        spacing: 6
                        FieldLabel { text: "Confidence Threshold"; width: parent.width }
                        NumberField {
                            id:          confField
                            theme:       root.theme
                            width:       parent.width
                            placeholder: "0.15"
                            value:       "0.15"
                        }
                    }

                    Column {
                        width:   (parent.width - 16) / 2
                        spacing: 6
                        FieldLabel { text: "IoU Threshold"; width: parent.width }
                        NumberField {
                            id:          iouField
                            theme:       root.theme
                            width:       parent.width
                            placeholder: "0.50"
                            value:       "0.50"
                        }
                    }
                }

                // Row 3 — Device + Stride
                Row {
                    width:   parent.width
                    spacing: 16

                    Column {
                        width:   (parent.width - 16) / 2
                        spacing: 6
                        FieldLabel { text: "Device"; width: parent.width }
                        DropDown {
                            id:      deviceCombo
                            theme:   root.theme
                            width:   parent.width
                            model:   ["cpu", "cuda"]
                            current: 0
                        }
                    }

                    Column {
                        width:   (parent.width - 16) / 2
                        spacing: 6
                        FieldLabel { text: "Video Stride"; width: parent.width }
                        NumberField {
                            id:          strideField
                            theme:       root.theme
                            width:       parent.width
                            placeholder: "1"
                            value:       "1"
                        }
                    }
                }

                // Row 4 — Coordinate Type (full width)
                Column {
                    width:   parent.width
                    spacing: 6
                    FieldLabel { text: "Coordinate Type"; width: parent.width }
                    DropDown {
                        id:      coordCombo
                        theme:   root.theme
                        width:   parent.width
                        model:   ["Center-Bottom", "Center-Center"]
                        current: 0
                    }
                }
            }

            Item { width: 1; height: 24 }

            // ── Advanced toggle ───────────────────────────────────────────────
            Rectangle {
                id: advancedRow
                width:  parent.width
                height: 42
                radius: 10
                color:  advMouse.containsMouse ? theme.surface2 : theme.surface
                border.color: theme.border
                border.width: 1

                Behavior on color { ColorAnimation { duration: 150 } }

                property bool expanded: false

                Row {
                    anchors.left:           parent.left
                    anchors.leftMargin:     16
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10

                    Text {
                        text: "Advanced Settings"
                        font.family:    theme.fontBody
                        font.pixelSize: 12
                        font.weight:    Font.Medium
                        color: theme.textPrimary
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                Text {
                    anchors.right:          parent.right
                    anchors.rightMargin:    16
                    anchors.verticalCenter: parent.verticalCenter
                    text: advancedRow.expanded ? "▲" : "▼"
                    font.pixelSize: 9
                    color: theme.textMuted
                }

                MouseArea {
                    id: advMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape:  Qt.PointingHandCursor
                    onClicked:    advancedRow.expanded = !advancedRow.expanded
                }
            }

            // ── Advanced panel ────────────────────────────────────────────────
            Rectangle {
                id: advPanel
                width:  parent.width
                height: advancedRow.expanded ? advContent.implicitHeight + 24 : 0
                radius: 10
                color:  theme.surface
                border.color: theme.border
                border.width: 1
                clip: true
                visible: height > 0

                Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

                Column {
                    id: advContent
                    x: 20; y: 12
                    width: parent.width - 40
                    spacing: 10

                    FieldLabel { text: "Track Buffer (bytetrack/botsort)"; visible: true }
                    NumberField {
                        id: trackBufferField
                        theme:       root.theme
                        width:       parent.width
                        placeholder: "30"
                        value:       "30"
                    }

                    FieldLabel { text: "Match Threshold" }
                    NumberField {
                        id: matchThreshField
                        theme:       root.theme
                        width:       parent.width
                        placeholder: "0.80"
                        value:       "0.80"
                    }

                    FieldLabel { text: "Max Cos Distance — StrongSORT ReID tolerance (lower = stricter)" }
                    NumberField {
                        id: maxCosDistField
                        theme:       root.theme
                        width:       parent.width
                        placeholder: "0.40"
                        value:       "0.40"
                    }

                    FieldLabel { text: "N Init — frames to confirm new ID (1 = faster, 3 = safer)" }
                    NumberField {
                        id: nInitField
                        theme:       root.theme
                        width:       parent.width
                        placeholder: "1"
                        value:       "1"
                    }

                    FieldLabel { text: "Image Size — resolução interna do YOLO (640=padrão, 1280=melhor para 4K)" }
                    NumberField {
                        id: imgszField
                        theme:       root.theme
                        width:       parent.width
                        placeholder: "1280"
                        value:       "1280"
                    }

                    FieldLabel { text: "Classes to Track (comma-separated IDs, empty = all)" }
                    NumberField {
                        id: classesField
                        theme:       root.theme
                        width:       parent.width
                        placeholder: "0   (person only)"
                        value:       "0"
                    }

                    Item { width: 1; height: 4 }
                }
            }

            Item { width: 1; height: advancedRow.expanded ? 12 : 24 }

            // ── Progress section ──────────────────────────────────────────────
            Rectangle {
                id: progressSection
                width:  parent.width
                height: trackerWorker.running ? progContent.implicitHeight + 24 : 0
                radius: 12
                color:  theme.surface
                border.color: theme.border
                border.width: 1
                clip: true
                visible: height > 0

                Behavior on height { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }

                Column {
                    id: progContent
                    x: 20; y: 12
                    width: parent.width - 40
                    spacing: 10

                    Row {
                        width: parent.width
                        spacing: 0

                        Text {
                            width: parent.width - pctText.width
                            text: trackerWorker.status || "Initializing…"
                            font.family:    theme.fontBody
                            font.pixelSize: 11
                            color: theme.textMuted
                            elide: Text.ElideRight
                        }
                        Text {
                            id: pctText
                            text: trackerWorker.progress + "%"
                            font.family:    theme.fontBody
                            font.pixelSize: 11
                            font.weight:    Font.SemiBold
                            color: theme.accent
                        }
                    }

                    Rectangle {
                        width:  parent.width
                        height: 4
                        radius: 2
                        color:  theme.surface2

                        Rectangle {
                            width:  parent.width * (trackerWorker.progress / 100)
                            height: parent.height
                            radius: parent.radius
                            color:  theme.accent

                            Behavior on width { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
                        }
                    }

                    Item { width: 1; height: 2 }
                }
            }

            Item { width: 1; height: progressSection.visible ? 12 : 0 }

            // ── Error banner ──────────────────────────────────────────────────
            Rectangle {
                id: errorBanner
                width:  parent.width
                height: errorText.text !== "" ? errorText.implicitHeight + 24 : 0
                radius: 10
                color:  Qt.rgba(1, 0.2, 0.2, 0.08)
                border.color: Qt.rgba(1, 0.3, 0.3, 0.30)
                border.width: 1
                clip: true
                visible: height > 0

                Behavior on height { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

                Text {
                    id: errorText
                    x: 16; y: 12
                    width: parent.width - 32
                    text: ""
                    wrapMode: Text.WordWrap
                    font.family:    theme.fontBody
                    font.pixelSize: 11
                    color: "#ff6b6b"
                }
            }

            Item { width: 1; height: errorText.text !== "" ? 12 : 0 }

            // ── Actions ───────────────────────────────────────────────────────
            Rectangle {
                id: startBtn
                width:  parent.width
                height: 44
                radius: 11
                color: {
                    if (!hasActiveVideo)       return Qt.rgba(1,1,1,0.04)
                    if (trackerWorker.running) return Qt.rgba(1, 0.3, 0.3, 0.12)
                    return startMouse.pressed        ? Qt.darker(theme.accent, 1.2)
                         : startMouse.containsMouse  ? theme.accentHover
                         : theme.accent
                }
                border.color: {
                    if (!hasActiveVideo)       return theme.border
                    if (trackerWorker.running) return Qt.rgba(1, 0.4, 0.4, 0.35)
                    return "transparent"
                }
                border.width: 1

                Behavior on color { ColorAnimation { duration: 150 } }

                Text {
                    anchors.centerIn: parent
                    text: trackerWorker.running ? "Cancel Tracking" : "Start Tracking"
                    font.family:    theme.fontBody
                    font.pixelSize: 13
                    font.weight:    Font.SemiBold
                    color: {
                        if (!hasActiveVideo)       return theme.textMuted
                        if (trackerWorker.running) return "#ff6b6b"
                        return "#ffffff"
                    }
                }

                MouseArea {
                    id: startMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape:  hasActiveVideo ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        if (!hasActiveVideo) return
                        errorText.text = ""
                        if (trackerWorker.running) {
                            trackerWorker.cancel()
                        } else {
                            _startTracking()
                        }
                    }
                }
            }

            Item { width: 1; height: 40 }
        }
    }

    // ── TrackerWorker connections ─────────────────────────────────────────────
    Connections {
        target: trackerWorker

        function onFinished(videoPath) {
            if (videosManager) {
                videosManager.refreshVideos()
            }
        }

        function onFailed(error) {
            errorText.text = error
        }
    }

    // ── Internal helpers ──────────────────────────────────────────────────────
    function _parseClasses() {
        const raw = classesField.value.trim()
        if (raw === "" || raw === "0   (person only)") return [0]
        return raw.split(",").map(s => parseInt(s.trim())).filter(n => !isNaN(n))
    }

    function _startTracking() {
        trackerWorker.start(
            activeVideoPath,
            modelCombo.currentText,
            trackerCombo.currentText,
            parseFloat(confField.value)        || 0.15,
            parseFloat(iouField.value)         || 0.50,
            deviceCombo.currentText,
            parseInt(strideField.value)        || 1,
            coordCombo.currentText,
            _parseClasses(),
            parseInt(trackBufferField.value)   || 120,
            parseFloat(matchThreshField.value) || 0.60,
            parseFloat(maxCosDistField.value)  || 0.40,
            parseInt(nInitField.value)         || 1,
            parseInt(imgszField.value)         || 1280
        )
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Inline sub-components
    // ─────────────────────────────────────────────────────────────────────────

    component FieldLabel: Text {
        font.family:      theme.fontBody
        font.pixelSize:   11
        font.weight:      Font.Medium
        font.letterSpacing: 0.3
        color: theme.textSecondary
        topPadding: 4
        bottomPadding: 0
    }

    component NumberField: Rectangle {
        id: _nf
        property QtObject theme
        property string placeholder: ""
        property alias  value:       _input.text

        height: 38
        radius: 9
        color:  _input.activeFocus
                ? Qt.rgba(66/255, 130/255, 255/255, 0.10)
                : theme.surface2
        border.color: _input.activeFocus
                      ? Qt.rgba(66/255, 130/255, 255/255, 0.50)
                      : theme.border
        border.width: 1

        Behavior on border.color { ColorAnimation { duration: 150 } }
        Behavior on color        { ColorAnimation { duration: 150 } }

        TextInput {
            id: _input
            anchors.left:           parent.left
            anchors.right:          parent.right
            anchors.leftMargin:     12
            anchors.rightMargin:    12
            anchors.verticalCenter: parent.verticalCenter
            font.family:    theme.fontBody
            font.pixelSize: 12
            color:          theme.textPrimary
            selectionColor: Qt.rgba(66/255, 130/255, 255/255, 0.35)

            Text {
                anchors.fill: parent
                text:         _nf.placeholder
                font:         parent.font
                color:        theme.textMuted
                visible:      parent.text === ""
            }
        }
    }

    component DropDown: Rectangle {
        id: _dd
        property QtObject theme
        property var    model:   []
        property int    current: 0
        property alias  currentText: _label.text

        height: 38
        radius: 9
        color:  _ddMouse.containsMouse ? theme.surface2 : theme.surface
        border.color: _popup.visible
                      ? Qt.rgba(66/255, 130/255, 255/255, 0.50)
                      : theme.border
        border.width: 1

        Behavior on color        { ColorAnimation { duration: 150 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }

        onCurrentChanged: _label.text = model[current] ?? ""
        Component.onCompleted: _label.text = model[current] ?? ""

        Row {
            anchors.left:           parent.left
            anchors.leftMargin:     12
            anchors.right:          parent.right
            anchors.rightMargin:    12
            anchors.verticalCenter: parent.verticalCenter
            spacing: 0

            Text {
                id: _label
                width: parent.width - _chevron.implicitWidth - 4
                font.family:    theme.fontBody
                font.pixelSize: 12
                color: theme.textPrimary
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
                height: parent.height
            }
            Text {
                id: _chevron
                text: _popup.visible ? "▲" : "▼"
                font.pixelSize: 8
                color: theme.textMuted
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        MouseArea {
            id: _ddMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape:  Qt.PointingHandCursor
            onClicked: {
                if (!_popup.visible) {
                    var pt = _dd.mapToItem(root, 0, _dd.height + 6)
                    _popup.x     = pt.x
                    _popup.y     = pt.y
                    _popup.width = _dd.width
                }
                _popup.visible = !_popup.visible
            }
        }

        // Full-screen catch to close popup on outside click
        MouseArea {
            id:      _dimmer
            parent:  root
            z:       998
            anchors.fill: parent
            visible: _popup.visible
            onClicked: _popup.visible = false
        }

        // Floating popup — parented to root, always on top
        Rectangle {
            id:      _popup
            visible: false
            parent:  root
            z:       999

            height:  _dd.model ? Math.min(_dd.model.length * 36, 216) : 0
            radius:  9
            color:   _dd.theme.surface2
            border.color: Qt.rgba(66/255, 130/255, 255/255, 0.45)
            border.width: 1
            clip:    true

            ListView {
                anchors.fill: parent
                model:        _dd.model
                clip:         true

                delegate: Item {
                    width:  _popup.width
                    height: 36

                    Rectangle {
                        anchors.fill: parent
                        color: _itemMouse.containsMouse
                               ? Qt.rgba(0, 113/255, 227/255, 0.14)
                               : (_dd.current === index
                                  ? Qt.rgba(0, 113/255, 227/255, 0.07)
                                  : "transparent")
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }

                    Text {
                        anchors.left:           parent.left
                        anchors.leftMargin:     14
                        anchors.verticalCenter: parent.verticalCenter
                        text:           modelData
                        font.family:    theme.fontBody
                        font.pixelSize: 12
                        color: _dd.current === index
                               ? _dd.theme.accent
                               : _dd.theme.textPrimary
                    }

                    MouseArea {
                        id:          _itemMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape:  Qt.PointingHandCursor
                        onClicked: {
                            _dd.current = index
                            _popup.visible = false
                        }
                    }
                }
            }
        }
    }
}
