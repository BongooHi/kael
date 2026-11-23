import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    width: 1040
    height: 720
    minimumWidth: 860
    minimumHeight: 600
    visible: true
    title: "Kael Settings"
    color: "#11111B"

    // Catppuccin Mocha palette (matches Serpantinum & looks native on any desktop)
    readonly property color cCrust: "#11111B"
    readonly property color cMantle: "#181825"
    readonly property color cBase: "#1E1E2E"
    readonly property color cSurface0: "#28293D"
    readonly property color cSurface1: "#363852"
    readonly property color cOverlay: "#585B70"
    readonly property color cText: "#CDD6F4"
    readonly property color cSubtext: "#A6ADC8"
    readonly property color cMuted: "#7F849C"
    readonly property color cMauve: "#CBA6F7"
    readonly property color cBlue: "#89B4FA"
    readonly property color cCyan: "#74C7EC"
    readonly property color cGreen: "#A6E3A1"
    readonly property color cPeach: "#FAB387"
    readonly property color cRed: "#F38BA8"

    property bool inWelcomeMode: backend.showWelcomeOnStart
    property int welcomeStep: 0
    property int stepDirection: 1
    property int currentTab: 0
    property bool dirty: false
    property bool revealApiKey: false

    // Editable draft state hydrated from backend.configJson
    property var draft: ({})
    property string draftApiKey: backend.apiKey || ""

    // Toast notification state
    property string toastText: ""
    property bool toastError: false
    property bool toastVisible: false

    function loadDraftFromBackend() {
        try {
            draft = JSON.parse(backend.configJson || "{}");
        } catch (e) {
            draft = {};
        }
        draftApiKey = backend.apiKey || "";
        dirty = false;
    }

    function setDraft(key, value) {
        let next = Object.assign({}, draft);
        next[key] = value;
        draft = next;
        dirty = true;
    }

    function getDraft(key, fallback) {
        return (draft && draft[key] !== undefined) ? draft[key] : fallback;
    }

    function appendPersonaSnippet(snippet) {
        let cur = String(getDraft("custom_instructions", "") || "").trim();
        if (cur.indexOf(snippet) !== -1) return;
        let combined = cur.length > 0 ? (cur + " " + snippet) : snippet;
        setDraft("custom_instructions", combined);
    }

    function saveDraft(forceRestart) {
        backend.saveAllSettings(JSON.stringify(draft), draftApiKey, Boolean(forceRestart));
        dirty = false;
    }

    function getThemeSwatches() {
        let tid = getDraft("hud_theme", "apple_rainbow");
        let list = backend.hudThemes || [];
        for (let i = 0; i < list.length; i++) {
            if (list[i].id === tid && list[i].swatches && list[i].swatches.length >= 3) {
                return list[i].swatches;
            }
        }
        return ["#61D1FF", "#C775FF", "#FF8073"];
    }

    function goToWelcomeStep(targetStep) {
        if (targetStep === welcomeStep) return;
        stepDirection = targetStep > welcomeStep ? 1 : -1;
        welcomeStep = targetStep;
    }

    function switchTab(idx) {
        if (idx === currentTab) return;
        if (currentTab === 4 && idx !== 4) backend.stopMicTest();
        currentTab = idx;
        tabTransition.restart();
    }

    onInWelcomeModeChanged: {
        backend.setWelcomeWizardActive(inWelcomeMode);
        if (!inWelcomeMode) {
            tabTransition.restart();
        }
    }

    Component.onCompleted: {
        loadDraftFromBackend();
        backend.setWelcomeWizardActive(inWelcomeMode);
    }

    Connections {
        target: backend
        function onConfigChanged() {
            win.loadDraftFromBackend();
        }
        function onToastEmitted(msg, isErr) {
            win.toastText = msg;
            win.toastError = isErr;
            win.toastVisible = true;
            toastTimer.restart();
        }
    }

    Timer {
        id: toastTimer
        interval: 3600
        onTriggered: win.toastVisible = false
    }

    // ==================== Reusable Micro-Animated Components ====================

    component KCard: Rectangle {
        color: win.cBase
        radius: 14
        border.width: 1
        border.color: win.cSurface0
    }

    component KBadge: Rectangle {
        property string label: ""
        property color badgeColor: win.cMauve
        implicitWidth: badgeTxt.implicitWidth + 18
        implicitHeight: 24
        radius: 12
        color: Qt.rgba(badgeColor.r, badgeColor.g, badgeColor.b, 0.16)
        border.width: 1
        border.color: Qt.rgba(badgeColor.r, badgeColor.g, badgeColor.b, 0.35)
        Text {
            id: badgeTxt
            anchors.centerIn: parent
            text: parent.label
            color: parent.badgeColor
            font.pixelSize: 11
            font.bold: true
        }
    }

    component KButton: Rectangle {
        id: kbtn
        property string text: ""
        property bool primary: false
        property bool danger: false
        property bool subtle: false
        property bool disabled: false
        property int hPad: 16
        signal clicked()

        implicitWidth: btnText.implicitWidth + hPad * 2
        implicitHeight: 36
        radius: 10
        opacity: disabled ? 0.5 : 1.0
        scale: btnMouse.pressed && !disabled ? 0.96 : (btnMouse.containsMouse && !disabled ? 1.02 : 1.0)
        color: {
            if (primary) return btnMouse.containsMouse && !disabled ? "#D8BAFA" : win.cMauve;
            if (danger) return btnMouse.containsMouse && !disabled ? Qt.rgba(0.95, 0.55, 0.66, 0.28) : Qt.rgba(0.95, 0.55, 0.66, 0.16);
            if (subtle) return btnMouse.containsMouse && !disabled ? win.cSurface0 : "transparent";
            return btnMouse.containsMouse && !disabled ? win.cSurface1 : win.cSurface0;
        }
        border.width: subtle ? 0 : 1
        border.color: primary ? "transparent" : (danger ? Qt.rgba(0.95, 0.55, 0.66, 0.42) : (btnMouse.containsMouse ? win.cOverlay : win.cSurface1))

        Behavior on color { ColorAnimation { duration: 130 } }
        Behavior on border.color { ColorAnimation { duration: 130 } }
        Behavior on scale { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }

        Text {
            id: btnText
            anchors.centerIn: parent
            text: kbtn.text
            color: kbtn.primary ? win.cCrust : (kbtn.danger ? win.cRed : win.cText)
            font.pixelSize: 13
            font.weight: kbtn.primary ? Font.Bold : Font.DemiBold
        }

        MouseArea {
            id: btnMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: kbtn.disabled ? Qt.ArrowCursor : Qt.PointingHandCursor
            onClicked: if (!kbtn.disabled) kbtn.clicked()
        }
    }

    component KVoicePlayButton: Rectangle {
        id: vpBtn
        property bool playing: false
        signal clicked()

        implicitWidth: 34
        implicitHeight: 30
        radius: 9
        scale: vpMa.pressed ? 0.92 : (vpMa.containsMouse ? 1.06 : 1.0)
        color: playing
            ? Qt.rgba(0.80, 0.65, 0.97, 0.28)
            : (vpMa.containsMouse ? win.cSurface1 : win.cSurface0)
        border.width: 1
        border.color: playing ? win.cMauve : (vpMa.containsMouse ? win.cOverlay : win.cSurface1)

        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

        // Static play triangle when idle
        Text {
            anchors.centerIn: parent
            visible: !vpBtn.playing
            text: "▶"
            color: win.cText
            font.pixelSize: 11
        }

        // Animated 3-bar equalizer wave while voice sample plays
        Row {
            anchors.centerIn: parent
            spacing: 2
            visible: vpBtn.playing
            Repeater {
                model: [0, 140, 280]
                delegate: Rectangle {
                    width: 3
                    height: 8
                    radius: 2
                    anchors.verticalCenter: parent.verticalCenter
                    color: win.cMauve
                    SequentialAnimation on height {
                        running: vpBtn.playing
                        loops: Animation.Infinite
                        PauseAnimation { duration: modelData }
                        NumberAnimation { from: 5; to: 15; duration: 220; easing.type: Easing.InOutSine }
                        NumberAnimation { from: 15; to: 5; duration: 220; easing.type: Easing.InOutSine }
                    }
                }
            }
        }

        MouseArea {
            id: vpMa
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: vpBtn.clicked()
        }
    }

    component KSwitch: Item {
        id: ksw
        property bool checked: false
        signal toggled(bool value)
        implicitWidth: 46
        implicitHeight: 26

        Rectangle {
            anchors.fill: parent
            radius: 13
            color: ksw.checked ? win.cMauve : win.cSurface1
            Behavior on color { ColorAnimation { duration: 160 } }

            Rectangle {
                width: kswMa.pressed ? 22 : 20
                height: 20
                radius: 10
                y: 3
                x: ksw.checked ? parent.width - width - 3 : 3
                color: ksw.checked ? win.cCrust : win.cText
                Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutBack; easing.overshoot: 0.9 } }
                Behavior on width { NumberAnimation { duration: 110 } }
            }
        }

        MouseArea {
            id: kswMa
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                ksw.checked = !ksw.checked;
                ksw.toggled(ksw.checked);
            }
        }
    }

    component KSlider: ColumnLayout {
        id: ksl
        property string title: ""
        property string subtitle: ""
        property string valueText: ""
        property real from: 0
        property real to: 1
        property real stepSize: 0.05
        property real value: 0.5
        signal movedValue(real v)

        Layout.fillWidth: true
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text { text: ksl.title; color: win.cText; font.pixelSize: 13; font.weight: Font.DemiBold }
                Text { visible: ksl.subtitle !== ""; text: ksl.subtitle; color: win.cMuted; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
            KBadge { label: ksl.valueText; badgeColor: win.cBlue }
        }

        Slider {
            id: sliderCtrl
            Layout.fillWidth: true
            from: ksl.from
            to: ksl.to
            stepSize: ksl.stepSize
            value: ksl.value
            onMoved: ksl.movedValue(value)

            background: Rectangle {
                x: sliderCtrl.leftPadding
                y: sliderCtrl.topPadding + sliderCtrl.availableHeight / 2 - height / 2
                implicitWidth: 200
                implicitHeight: 6
                width: sliderCtrl.availableWidth
                height: 6
                radius: 3
                color: win.cSurface1

                Rectangle {
                    width: sliderCtrl.visualPosition * parent.width
                    height: parent.height
                    radius: 3
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: win.cCyan }
                        GradientStop { position: 1.0; color: win.cMauve }
                    }
                }
            }

            handle: Rectangle {
                x: sliderCtrl.leftPadding + sliderCtrl.visualPosition * (sliderCtrl.availableWidth - width)
                y: sliderCtrl.topPadding + sliderCtrl.availableHeight / 2 - height / 2
                implicitWidth: sliderCtrl.pressed ? 21 : 18
                implicitHeight: sliderCtrl.pressed ? 21 : 18
                radius: width / 2
                color: sliderCtrl.pressed ? "#FFFFFF" : win.cText
                border.width: 2
                border.color: win.cMauve
                Behavior on implicitWidth { NumberAnimation { duration: 110 } }
                Behavior on implicitHeight { NumberAnimation { duration: 110 } }
            }
        }
    }

    component KInput: TextField {
        color: win.cText
        placeholderTextColor: win.cMuted
        font.pixelSize: 13
        leftPadding: 12
        rightPadding: 12
        topPadding: 9
        bottomPadding: 9
        selectByMouse: true
        background: Rectangle {
            radius: 10
            color: win.cMantle
            border.width: 1.5
            border.color: parent.activeFocus ? win.cMauve : win.cSurface1
            Behavior on border.color { ColorAnimation { duration: 150 } }
        }
    }

    component KToggleRow: RowLayout {
        id: ktrow
        property string title: ""
        property string subtitle: ""
        property bool checked: false
        signal toggled(bool value)

        Layout.fillWidth: true
        spacing: 12

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { text: ktrow.title; color: win.cText; font.pixelSize: 13; font.weight: Font.DemiBold }
            Text { text: ktrow.subtitle; color: win.cMuted; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        KSwitch {
            checked: ktrow.checked
            onToggled: v => ktrow.toggled(v)
        }
    }

    // Reusable Custom Personality Drawer + Hints + Premade Example Chips
    component KCustomPersonaEditor: Rectangle {
        id: cpe
        property bool isCustomMode: win.getDraft("persona_preset", "snarky") === "custom"
        property bool expanded: true

        Layout.fillWidth: true
        implicitHeight: expanded ? (cpeCol.implicitHeight + 28) : 0
        opacity: expanded ? 1.0 : 0.0
        visible: implicitHeight > 2
        clip: true
        radius: 12
        color: isCustomMode ? Qt.rgba(0.80, 0.65, 0.97, 0.09) : win.cMantle
        border.width: isCustomMode ? 1.5 : 1
        border.color: isCustomMode ? Qt.rgba(0.80, 0.65, 0.97, 0.55) : win.cSurface0

        Behavior on implicitHeight { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 200 } }
        Behavior on border.color { ColorAnimation { duration: 180 } }

        ColumnLayout {
            id: cpeCol
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 14
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Text {
                    text: cpe.isCustomMode
                        ? "✦ Personalize Your Custom AI Personality"
                        : "Extra Personality Tweaks (Optional)"
                    color: cpe.isCustomMode ? win.cMauve : win.cText
                    font.pixelSize: 13
                    font.bold: true
                    Layout.fillWidth: true
                }
                KButton {
                    visible: String(win.getDraft("custom_instructions", "") || "").length > 0
                    text: "Clear"
                    subtle: true
                    hPad: 10
                    implicitHeight: 26
                    onClicked: win.setDraft("custom_instructions", "")
                }
            }

            Text {
                text: cpe.isCustomMode
                    ? "Describe the exact vibe, tone, pacing, or rules you want Kael to follow — or click any starter chip below to mix & match:"
                    : "Want to layer extra quirks on top of your selected preset? Add a line below or tap a starter chip:"
                color: win.cMuted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            // Premade clickable example chips
            Flow {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: backend.exampleSnippets
                    delegate: Rectangle {
                        id: chip
                        implicitWidth: chipTxt.implicitWidth + 18
                        implicitHeight: 26
                        radius: 13
                        scale: chipMa.pressed ? 0.94 : (chipMa.containsMouse ? 1.03 : 1.0)
                        color: chipMa.containsMouse
                            ? Qt.rgba(0.80, 0.65, 0.97, 0.24)
                            : Qt.rgba(0.54, 0.71, 0.98, 0.12)
                        border.width: 1
                        border.color: chipMa.containsMouse
                            ? win.cMauve
                            : Qt.rgba(0.54, 0.71, 0.98, 0.32)

                        Behavior on color { ColorAnimation { duration: 110 } }
                        Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }

                        Text {
                            id: chipTxt
                            anchors.centerIn: parent
                            text: modelData.label
                            color: chipMa.containsMouse ? win.cMauve : win.cBlue
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                        }

                        MouseArea {
                            id: chipMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: win.appendPersonaSnippet(modelData.text)
                        }
                    }
                }
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: cpe.isCustomMode ? 105 : 78
                Behavior on Layout.preferredHeight { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

                TextArea {
                    id: customArea
                    text: win.getDraft("custom_instructions", "")
                    placeholderText: cpe.isCustomMode
                        ? "Example: 'Talk like a witty cyberpunk hacker living in my Arch desktop. Keep replies short, punchy, and casually roast me when I ask obvious questions.'"
                        : "Optional extra instructions (e.g. 'Call me Captain', 'Keep answers under 10 words')..."
                    placeholderTextColor: win.cMuted
                    color: win.cText
                    font.pixelSize: 12
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    padding: 10
                    onTextChanged: {
                        if (text !== win.getDraft("custom_instructions", "")) {
                            win.setDraft("custom_instructions", text);
                        }
                    }
                    background: Rectangle {
                        radius: 10
                        color: win.cCrust
                        border.width: 1.5
                        border.color: parent.activeFocus ? win.cMauve : win.cSurface1
                        Behavior on border.color { ColorAnimation { duration: 140 } }
                    }
                }
            }

            Text {
                text: "Hint: Your tool powers (opening apps, screen vision, Hyprland control, memory) stay active automatically."
                color: win.cOverlay
                font.pixelSize: 10
                font.italic: true
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }

    // ==================== 1. FIRST-RUN WELCOME WIZARD ====================

    Item {
        id: welcomeView
        anchors.fill: parent
        visible: opacity > 0.01
        opacity: win.inWelcomeMode ? 1.0 : 0.0
        scale: win.inWelcomeMode ? 1.0 : 0.985
        clip: true
        Behavior on opacity { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }

        // Ambient drifting aurora glow orbs (shift colors smoothly with your selected HUD theme!)
        Item {
            id: auroraLayer
            anchors.fill: parent
            z: -1
            readonly property var swatches: win.getThemeSwatches()

            Rectangle {
                id: auroraOrb1
                width: 440; height: 440; radius: 220
                x: -120 + win.welcomeStep * 90
                y: -140
                opacity: 0.10
                color: auroraLayer.swatches[0]
                Behavior on x { NumberAnimation { duration: 650; easing.type: Easing.OutCubic } }
                Behavior on color { ColorAnimation { duration: 450 } }
                SequentialAnimation on y {
                    running: win.inWelcomeMode
                    loops: Animation.Infinite
                    NumberAnimation { from: -155; to: -85; duration: 4600; easing.type: Easing.InOutSine }
                    NumberAnimation { from: -85; to: -155; duration: 4600; easing.type: Easing.InOutSine }
                }
            }

            Rectangle {
                id: auroraOrb2
                width: 480; height: 480; radius: 240
                x: auroraLayer.width - 280 - win.welcomeStep * 75
                y: auroraLayer.height - 250
                opacity: 0.09
                color: auroraLayer.swatches[1]
                Behavior on x { NumberAnimation { duration: 650; easing.type: Easing.OutCubic } }
                Behavior on color { ColorAnimation { duration: 450 } }
                SequentialAnimation on y {
                    running: win.inWelcomeMode
                    loops: Animation.Infinite
                    NumberAnimation { from: auroraLayer.height - 220; to: auroraLayer.height - 300; duration: 5200; easing.type: Easing.InOutSine }
                    NumberAnimation { from: auroraLayer.height - 300; to: auroraLayer.height - 220; duration: 5200; easing.type: Easing.InOutSine }
                }
            }

            Rectangle {
                id: auroraOrb3
                width: 300; height: 300; radius: 150
                x: auroraLayer.width * 0.42 + (win.welcomeStep - 1.5) * 65
                y: auroraLayer.height * 0.22
                opacity: 0.06
                color: auroraLayer.swatches[2]
                Behavior on x { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }
                Behavior on color { ColorAnimation { duration: 450 } }
                SequentialAnimation on scale {
                    running: win.inWelcomeMode
                    loops: Animation.Infinite
                    NumberAnimation { from: 0.92; to: 1.14; duration: 3800; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 1.14; to: 0.92; duration: 3800; easing.type: Easing.InOutSine }
                }
            }
        }

        // Top animated rainbow progress track
        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 3
            color: win.cSurface0
            Rectangle {
                height: parent.height
                width: parent.width * ((win.welcomeStep + 1) / 4.0)
                Behavior on width { NumberAnimation { duration: 420; easing.type: Easing.OutExpo } }
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: win.getThemeSwatches()[0] }
                    GradientStop { position: 0.5; color: win.getThemeSwatches()[1] }
                    GradientStop { position: 1.0; color: win.getThemeSwatches()[2] }
                }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 16

            // Top Stepper Bar
            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                RowLayout {
                    spacing: 10
                    Rectangle {
                        width: 34; height: 34; radius: 10
                        color: win.cBase
                        border.width: 1.5
                        border.color: win.cMauve
                        Text { anchors.centerIn: parent; text: "K"; color: win.cMauve; font.pixelSize: 17; font.bold: true }
                    }
                    ColumnLayout {
                        spacing: 0
                        Text { text: "Kael Setup"; color: win.cText; font.pixelSize: 15; font.bold: true }
                        Text { text: backend.desktopLabel; color: win.cMuted; font.pixelSize: 11 }
                    }
                }

                KBadge {
                    visible: backend.setupModeActive
                    label: "Setup Mode · Wake-word paused"
                    badgeColor: win.cCyan
                }

                Item { Layout.fillWidth: true }

                // Step pills
                RowLayout {
                    spacing: 7
                    Repeater {
                        model: ["Welcome", "API Key", "Voice & Vibe", "Looks & Wake"]
                        delegate: Rectangle {
                            readonly property bool isCurrent: index === win.welcomeStep
                            readonly property bool isDone: index < win.welcomeStep
                            implicitWidth: stepLbl.implicitWidth + 18
                            implicitHeight: 28
                            radius: 14
                            scale: stepMa.pressed ? 0.95 : (stepMa.containsMouse ? 1.03 : 1.0)
                            color: isCurrent ? Qt.rgba(0.80, 0.65, 0.97, 0.22) : (isDone ? Qt.rgba(0.65, 0.89, 0.63, 0.14) : win.cMantle)
                            border.width: 1
                            border.color: isCurrent ? win.cMauve : (isDone ? Qt.rgba(0.65, 0.89, 0.63, 0.4) : win.cSurface0)

                            Behavior on color { ColorAnimation { duration: 180 } }
                            Behavior on border.color { ColorAnimation { duration: 180 } }
                            Behavior on scale { NumberAnimation { duration: 110 } }

                            Text {
                                id: stepLbl
                                anchors.centerIn: parent
                                text: (isDone ? "✓ " : (index + 1) + ". ") + modelData
                                color: isCurrent ? win.cMauve : (isDone ? win.cGreen : win.cMuted)
                                font.pixelSize: 11
                                font.weight: isCurrent ? Font.Bold : Font.Medium
                            }

                            MouseArea {
                                id: stepMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: win.goToWelcomeStep(index)
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                KButton {
                    text: "Skip to Settings"
                    subtle: true
                    onClicked: {
                        backend.stopVoicePreview();
                        backend.stopMicTest();
                        win.inWelcomeMode = false;
                    }
                }
            }

            // Wizard Main Content Card with True Dual-Page Sliding Carousel + Parallax Depth
            KCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                color: Qt.rgba(0.118, 0.118, 0.180, 0.92)

                Item {
                    id: wizardViewport
                    anchors.fill: parent
                    clip: true

                    Row {
                        id: wizardTrack
                        height: wizardViewport.height
                        x: -win.welcomeStep * wizardViewport.width
                        Behavior on x {
                            NumberAnimation {
                                duration: 440
                                easing.type: Easing.OutExpo
                            }
                        }

                        // ---- STEP 0: WELCOME GREETING ----
                        Item {
                            width: wizardViewport.width
                            height: wizardViewport.height
                            readonly property bool activePage: win.welcomeStep === 0
                            opacity: activePage ? 1.0 : 0.22
                            scale: activePage ? 1.0 : 0.95
                            Behavior on opacity { NumberAnimation { duration: 340; easing.type: Easing.OutCubic } }
                            Behavior on scale { NumberAnimation { duration: 380; easing.type: Easing.OutCubic } }

                            Flickable {
                                anchors.fill: parent
                                anchors.margins: 28
                                contentWidth: width
                                contentHeight: step0Col.implicitHeight
                                clip: true
                                ColumnLayout {
                                    id: step0Col
                                    width: parent.width
                                    spacing: 20

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 18

                                        // Levitating, breathing & orbiting glowing Kael Emblem
                                        Item {
                                            width: 80; height: 80
                                            Item {
                                                anchors.centerIn: parent
                                                width: 78; height: 78
                                                SequentialAnimation on y {
                                                    running: win.inWelcomeMode && win.welcomeStep === 0
                                                    loops: Animation.Infinite
                                                    NumberAnimation { from: 4; to: -4; duration: 2200; easing.type: Easing.InOutSine }
                                                    NumberAnimation { from: -4; to: 4; duration: 2200; easing.type: Easing.InOutSine }
                                                }

                                                // Slowly rotating gradient halo
                                                Rectangle {
                                                    anchors.centerIn: parent
                                                    width: 78; height: 78; radius: 24
                                                    opacity: 0.45
                                                    gradient: Gradient {
                                                        GradientStop { position: 0.0; color: win.getThemeSwatches()[0] }
                                                        GradientStop { position: 0.5; color: win.getThemeSwatches()[1] }
                                                        GradientStop { position: 1.0; color: win.getThemeSwatches()[2] }
                                                    }
                                                    RotationAnimation on rotation {
                                                        running: win.inWelcomeMode && win.welcomeStep === 0
                                                        from: 0; to: 360
                                                        duration: 9000
                                                        loops: Animation.Infinite
                                                    }
                                                    SequentialAnimation on scale {
                                                        running: win.inWelcomeMode && win.welcomeStep === 0
                                                        loops: Animation.Infinite
                                                        NumberAnimation { from: 0.95; to: 1.07; duration: 1900; easing.type: Easing.InOutSine }
                                                        NumberAnimation { from: 1.07; to: 0.95; duration: 1900; easing.type: Easing.InOutSine }
                                                    }
                                                }

                                                Rectangle {
                                                    anchors.centerIn: parent
                                                    width: 70; height: 70; radius: 21
                                                    gradient: Gradient {
                                                        GradientStop { position: 0.0; color: "#2A2444" }
                                                        GradientStop { position: 1.0; color: "#181825" }
                                                    }
                                                    border.width: 2
                                                    border.color: win.cMauve
                                                    Text {
                                                        anchors.centerIn: parent
                                                        text: "K"
                                                        font.pixelSize: 32
                                                        font.bold: true
                                                        color: win.cMauve
                                                    }
                                                }
                                            }
                                        }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 6
                                            Text {
                                                text: "Welcome to Kael"
                                                color: win.cText
                                                font.pixelSize: 28
                                                font.bold: true
                                            }
                                            Text {
                                                text: "Your always-listening Linux AI voice assistant powered by Gemini 3.8 Live, offline Vosk wake-word detection, GPU edge glow, and safe desktop automation."
                                                color: win.cSubtext
                                                font.pixelSize: 13
                                                wrapMode: Text.WordWrap
                                                Layout.fillWidth: true
                                            }
                                        }
                                    }

                                    // 4 Feature Cards with staggered entrance + hover lift
                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: 2
                                        columnSpacing: 12
                                        rowSpacing: 12

                                        Repeater {
                                            model: [
                                                { title: "Hands-Free Offline Wake Word", desc: "Local Vosk listens quietly in the background with near-zero CPU — and pauses automatically while you're in Setup Mode.", accent: "#74C7EC" },
                                                { title: "Real-Time Voice & Vision", desc: "Low-latency two-way voice with Smart Barge-In, live screen vision, and persistent memory.", accent: "#CBA6F7" },
                                                { title: "GPU Edge Glow & Captions", desc: "7 customizable Wayland shader palettes, animated dual captions, and floating image cards.", accent: "#FAB387" },
                                                { title: "Cross-Desktop Ready", desc: "Runs cleanly across Hyprland, KDE, GNOME, Sway, and PipeWire audio out of the box.", accent: "#A6E3A1" }
                                            ]
                                            delegate: Rectangle {
                                                id: featCard
                                                Layout.fillWidth: true
                                                implicitHeight: featCol.implicitHeight + 24
                                                radius: 12
                                                scale: featMa.containsMouse ? 1.016 : 1.0
                                                opacity: (win.inWelcomeMode && win.welcomeStep === 0) ? 1.0 : 0.0
                                                color: win.cMantle
                                                border.width: 1
                                                border.color: featMa.containsMouse ? modelData.accent : win.cSurface0
                                                transform: Translate {
                                                    y: (win.inWelcomeMode && win.welcomeStep === 0) ? 0 : (14 + index * 6)
                                                    Behavior on y {
                                                        SequentialAnimation {
                                                            PauseAnimation { duration: index * 65 }
                                                            NumberAnimation { duration: 360; easing.type: Easing.OutCubic }
                                                        }
                                                    }
                                                }
                                                Behavior on opacity {
                                                    SequentialAnimation {
                                                        PauseAnimation { duration: index * 65 }
                                                        NumberAnimation { duration: 320; easing.type: Easing.OutCubic }
                                                    }
                                                }
                                                Behavior on border.color { ColorAnimation { duration: 150 } }
                                                Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }

                                                ColumnLayout {
                                                    id: featCol
                                                    anchors.fill: parent
                                                    anchors.margins: 12
                                                    spacing: 4
                                                    Text { text: modelData.title; color: modelData.accent; font.pixelSize: 13; font.bold: true }
                                                    Text { text: modelData.desc; color: win.cSubtext; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                                }
                                                MouseArea { id: featMa; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                                            }
                                        }
                                    }

                                    // Live System Readiness
                                    Rectangle {
                                        Layout.fillWidth: true
                                        implicitHeight: readyCol.implicitHeight + 24
                                        radius: 12
                                        color: win.cMantle
                                        border.width: 1
                                        border.color: win.cSurface0

                                        ColumnLayout {
                                            id: readyCol
                                            anchors.fill: parent
                                            anchors.margins: 14
                                            spacing: 10
                                            Text { text: "System Readiness Check"; color: win.cText; font.pixelSize: 13; font.bold: true }

                                            GridLayout {
                                                Layout.fillWidth: true
                                                columns: 2
                                                columnSpacing: 14
                                                rowSpacing: 8
                                                Repeater {
                                                    model: backend.systemChecks
                                                    delegate: RowLayout {
                                                        Layout.fillWidth: true
                                                        spacing: 8
                                                        Rectangle {
                                                            width: 9; height: 9; radius: 5
                                                            color: modelData.ok ? win.cGreen : win.cPeach
                                                        }
                                                        ColumnLayout {
                                                            spacing: 1
                                                            Layout.fillWidth: true
                                                            Text { text: modelData.name; color: win.cText; font.pixelSize: 12; font.weight: Font.Medium }
                                                            Text { text: modelData.detail; color: win.cMuted; font.pixelSize: 11 }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // ---- STEP 1: GEMINI API KEY ----
                        Item {
                            width: wizardViewport.width
                            height: wizardViewport.height
                            readonly property bool activePage: win.welcomeStep === 1
                            opacity: activePage ? 1.0 : 0.22
                            scale: activePage ? 1.0 : 0.95
                            Behavior on opacity { NumberAnimation { duration: 340; easing.type: Easing.OutCubic } }
                            Behavior on scale { NumberAnimation { duration: 380; easing.type: Easing.OutCubic } }

                            Flickable {
                                anchors.fill: parent
                                anchors.margins: 28
                                contentWidth: width
                                contentHeight: step1Col.implicitHeight
                                clip: true
                                ColumnLayout {
                                    id: step1Col
                                    width: parent.width
                                    spacing: 18

                                    Text { text: "Connect Google Gemini AI"; color: win.cText; font.pixelSize: 22; font.bold: true }
                                    Text {
                                        text: "Kael uses Google's Gemini 3.8 Live API for ultra-fast voice conversation and screen vision. Your API key is stored locally inside a private chmod-600 .env file and never shared anywhere else."
                                        color: win.cSubtext
                                        font.pixelSize: 13
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        implicitHeight: keyBoxCol.implicitHeight + 28
                                        radius: 12
                                        color: win.cMantle
                                        border.width: 1
                                        border.color: win.cSurface0

                                        ColumnLayout {
                                            id: keyBoxCol
                                            anchors.fill: parent
                                            anchors.margins: 14
                                            spacing: 12

                                            Text { text: "Google AI Studio API Key"; color: win.cText; font.pixelSize: 13; font.bold: true }

                                            RowLayout {
                                                Layout.fillWidth: true
                                                spacing: 8
                                                KInput {
                                                    Layout.fillWidth: true
                                                    placeholderText: "Paste your GEMINI_API_KEY here (e.g. AIza... or AQ....)"
                                                    echoMode: win.revealApiKey ? TextInput.Normal : TextInput.Password
                                                    text: win.draftApiKey
                                                    onTextEdited: {
                                                        win.draftApiKey = text;
                                                        win.dirty = true;
                                                    }
                                                }
                                                KButton {
                                                    text: win.revealApiKey ? "Hide" : "Show"
                                                    onClicked: win.revealApiKey = !win.revealApiKey
                                                }
                                            }

                                            RowLayout {
                                                Layout.fillWidth: true
                                                spacing: 10
                                                KButton {
                                                    text: backend.apiTesting ? "Testing..." : "Test API Key"
                                                    primary: true
                                                    disabled: backend.apiTesting
                                                    onClicked: backend.testApiKey(win.draftApiKey)
                                                }
                                                KButton {
                                                    text: "Get a Free API Key ↗"
                                                    onClicked: backend.openUrl("https://aistudio.google.com/apikey")
                                                }
                                                Item { Layout.fillWidth: true }
                                            }

                                            Rectangle {
                                                visible: backend.apiTestMessage !== ""
                                                Layout.fillWidth: true
                                                implicitHeight: apiMsgTxt.implicitHeight + 16
                                                radius: 8
                                                color: backend.apiTestOk ? Qt.rgba(0.65, 0.89, 0.63, 0.14) : Qt.rgba(0.95, 0.55, 0.66, 0.14)
                                                border.width: 1
                                                border.color: backend.apiTestOk ? Qt.rgba(0.65, 0.89, 0.63, 0.4) : Qt.rgba(0.95, 0.55, 0.66, 0.4)
                                                Text {
                                                    id: apiMsgTxt
                                                    anchors.fill: parent
                                                    anchors.margins: 8
                                                    text: backend.apiTestMessage
                                                    color: backend.apiTestOk ? win.cGreen : win.cRed
                                                    font.pixelSize: 12
                                                    wrapMode: Text.WordWrap
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // ---- STEP 2: VOICE & PERSONALITY ----
                        Item {
                            width: wizardViewport.width
                            height: wizardViewport.height
                            readonly property bool activePage: win.welcomeStep === 2
                            opacity: activePage ? 1.0 : 0.22
                            scale: activePage ? 1.0 : 0.95
                            Behavior on opacity { NumberAnimation { duration: 340; easing.type: Easing.OutCubic } }
                            Behavior on scale { NumberAnimation { duration: 380; easing.type: Easing.OutCubic } }

                            Flickable {
                                anchors.fill: parent
                                anchors.margins: 28
                                contentWidth: width
                                contentHeight: step2Col.implicitHeight + 16
                                clip: true
                                ColumnLayout {
                                    id: step2Col
                                    width: parent.width
                                    spacing: 14

                                    Text { text: "Choose Voice & Personality"; color: win.cText; font.pixelSize: 22; font.bold: true }
                                    Text { text: "Tap ▶ to preview voices fast (wake-word is paused in Setup Mode so previews won't wake Kael!)."; color: win.cSubtext; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }

                                    Text { text: "Studio Voice"; color: win.cText; font.pixelSize: 13; font.bold: true }
                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: 3
                                        columnSpacing: 10
                                        rowSpacing: 10

                                        Repeater {
                                            model: backend.voiceCatalog.slice(0, 6)
                                            delegate: Rectangle {
                                                readonly property bool selected: win.getDraft("voice", "Schedar") === modelData.id
                                                readonly property bool isPlaying: backend.voicePreviewing && backend.previewVoiceId === modelData.id
                                                Layout.fillWidth: true
                                                implicitHeight: 70
                                                radius: 12
                                                scale: wVoiceMa.pressed ? 0.975 : (wVoiceMa.containsMouse ? 1.015 : 1.0)
                                                color: selected ? Qt.rgba(0.80, 0.65, 0.97, 0.16) : (wVoiceMa.containsMouse ? win.cSurface0 : win.cMantle)
                                                border.width: selected ? 1.5 : 1
                                                border.color: selected ? win.cMauve : (wVoiceMa.containsMouse ? win.cOverlay : win.cSurface0)

                                                Behavior on color { ColorAnimation { duration: 140 } }
                                                Behavior on border.color { ColorAnimation { duration: 140 } }
                                                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

                                                RowLayout {
                                                    anchors.fill: parent
                                                    anchors.margins: 10
                                                    spacing: 8
                                                    ColumnLayout {
                                                        Layout.fillWidth: true
                                                        spacing: 2
                                                        Text { text: (selected ? "✓ " : "") + modelData.label; color: selected ? win.cMauve : win.cText; font.pixelSize: 13; font.bold: true }
                                                        Text { text: modelData.vibe; color: win.cMuted; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                                                    }
                                                    KVoicePlayButton {
                                                        playing: isPlaying
                                                        onClicked: backend.previewVoice(modelData.id, win.draftApiKey)
                                                    }
                                                }

                                                MouseArea {
                                                    id: wVoiceMa
                                                    anchors.fill: parent
                                                    z: -1
                                                    hoverEnabled: true
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: win.setDraft("voice", modelData.id)
                                                }
                                            }
                                        }
                                    }

                                    Text { text: "Personality Preset"; color: win.cText; font.pixelSize: 13; font.bold: true }
                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: 2
                                        columnSpacing: 10
                                        rowSpacing: 10

                                        Repeater {
                                            model: backend.personaPresets
                                            delegate: Rectangle {
                                                readonly property bool selected: win.getDraft("persona_preset", "snarky") === modelData.id
                                                Layout.fillWidth: true
                                                implicitHeight: 60
                                                radius: 12
                                                scale: wPersMa.pressed ? 0.98 : (wPersMa.containsMouse ? 1.012 : 1.0)
                                                color: selected ? Qt.rgba(0.54, 0.71, 0.98, 0.16) : (wPersMa.containsMouse ? win.cSurface0 : win.cMantle)
                                                border.width: selected ? 1.5 : 1
                                                border.color: selected ? win.cBlue : (wPersMa.containsMouse ? win.cOverlay : win.cSurface0)

                                                Behavior on color { ColorAnimation { duration: 140 } }
                                                Behavior on border.color { ColorAnimation { duration: 140 } }
                                                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

                                                ColumnLayout {
                                                    anchors.fill: parent
                                                    anchors.margins: 10
                                                    spacing: 2
                                                    Text { text: (selected ? "✓ " : "") + modelData.name; color: selected ? win.cBlue : win.cText; font.pixelSize: 13; font.bold: true }
                                                    Text { text: modelData.tagline; color: win.cMuted; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                                                }

                                                MouseArea {
                                                    id: wPersMa
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: win.setDraft("persona_preset", modelData.id)
                                                }
                                            }
                                        }
                                    }

                                    // Smoothly expands right underneath when "Custom Personality" is selected!
                                    KCustomPersonaEditor {
                                        expanded: win.getDraft("persona_preset", "snarky") === "custom"
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 18
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 4
                                            Text { text: "Languages"; color: win.cText; font.pixelSize: 12; font.bold: true }
                                            KInput {
                                                Layout.fillWidth: true
                                                text: win.getDraft("languages", "English and Vietnamese")
                                                onTextEdited: win.setDraft("languages", text)
                                            }
                                        }
                                        ColumnLayout {
                                            spacing: 6
                                            KToggleRow {
                                                title: "Light casual swearing"
                                                subtitle: "Natural blunt tone"
                                                checked: Boolean(win.getDraft("allow_swearing", true))
                                                onToggled: v => win.setDraft("allow_swearing", v)
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // ---- STEP 3: LOOKS & WAKE WORD ----
                        Item {
                            width: wizardViewport.width
                            height: wizardViewport.height
                            readonly property bool activePage: win.welcomeStep === 3
                            opacity: activePage ? 1.0 : 0.22
                            scale: activePage ? 1.0 : 0.95
                            Behavior on opacity { NumberAnimation { duration: 340; easing.type: Easing.OutCubic } }
                            Behavior on scale { NumberAnimation { duration: 380; easing.type: Easing.OutCubic } }

                            Flickable {
                                anchors.fill: parent
                                anchors.margins: 28
                                contentWidth: width
                                contentHeight: step3Col.implicitHeight + 12
                                clip: true
                                ColumnLayout {
                                    id: step3Col
                                    width: parent.width
                                    spacing: 14

                                    RowLayout {
                                        Layout.fillWidth: true
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            Text { text: "Visual Look & Wake Word"; color: win.cText; font.pixelSize: 22; font.bold: true }
                                            Text { text: "Pick your edge-glow palette and wake phrase — watch the live preview below or test it full-screen!"; color: win.cSubtext; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                        }
                                        KButton {
                                            text: "✦ Full-Screen Glow"
                                            primary: true
                                            onClicked: backend.previewHud(
                                                win.getDraft("hud_theme", "apple_rainbow"),
                                                Number(win.getDraft("hud_glow_intensity", 1.0)),
                                                Number(win.getDraft("hud_glow_speed", 1.0)),
                                                Boolean(win.getDraft("hud_show_captions", true)),
                                                Number(win.getDraft("hud_caption_scale", 1.0))
                                            )
                                        }
                                    }

                                    // Live animated miniature screen-glow preview bar!
                                    Rectangle {
                                        id: miniScreenOuter
                                        Layout.fillWidth: true
                                        implicitHeight: 82
                                        radius: 14
                                        readonly property var sw: win.getThemeSwatches()
                                        readonly property real glowScale: Number(win.getDraft("hud_glow_intensity", 1.0))
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop { position: 0.0; color: miniScreenOuter.sw[0] }
                                            GradientStop { position: 0.5; color: miniScreenOuter.sw[1] }
                                            GradientStop { position: 1.0; color: miniScreenOuter.sw[2] }
                                        }

                                        // Soft animated shimmer overlay
                                        Rectangle {
                                            anchors.fill: parent
                                            radius: 14
                                            opacity: 0.35
                                            gradient: Gradient {
                                                orientation: Gradient.Horizontal
                                                GradientStop { position: 0.0; color: miniScreenOuter.sw[2] }
                                                GradientStop { position: 0.5; color: miniScreenOuter.sw[0] }
                                                GradientStop { position: 1.0; color: miniScreenOuter.sw[1] }
                                            }
                                            SequentialAnimation on opacity {
                                                running: win.inWelcomeMode && win.welcomeStep === 3
                                                loops: Animation.Infinite
                                                NumberAnimation { from: 0.1; to: 0.85; duration: 1500; easing.type: Easing.InOutSine }
                                                NumberAnimation { from: 0.85; to: 0.1; duration: 1500; easing.type: Easing.InOutSine }
                                            }
                                        }

                                        // Inner desktop screen inset (shrinks as Glow Thickness increases!)
                                        Rectangle {
                                            anchors.fill: parent
                                            anchors.margins: Math.round(3 + miniScreenOuter.glowScale * 3.5)
                                            radius: 10
                                            color: "#0F101A"
                                            Behavior on anchors.margins { NumberAnimation { duration: 150 } }

                                            // Simulated floating dual caption pill
                                            Rectangle {
                                                anchors.centerIn: parent
                                                implicitWidth: miniCapTxt.implicitWidth + 28
                                                implicitHeight: 34
                                                radius: 17
                                                color: Qt.rgba(0.06, 0.07, 0.12, 0.88)
                                                border.width: 1
                                                border.color: miniScreenOuter.sw[0]
                                                Behavior on border.color { ColorAnimation { duration: 250 } }
                                                Text {
                                                    id: miniCapTxt
                                                    anchors.centerIn: parent
                                                    text: "Kael: \"Edge glow looking crisp.\""
                                                    color: win.cText
                                                    font.pixelSize: 12
                                                    font.weight: Font.DemiBold
                                                }
                                            }
                                        }
                                    }

                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: 3
                                        columnSpacing: 10
                                        rowSpacing: 10

                                        Repeater {
                                            model: backend.hudThemes
                                            delegate: Rectangle {
                                                readonly property bool selected: win.getDraft("hud_theme", "apple_rainbow") === modelData.id
                                                Layout.fillWidth: true
                                                implicitHeight: 70
                                                radius: 12
                                                scale: wThMa.pressed ? 0.975 : (wThMa.containsMouse ? 1.015 : 1.0)
                                                color: selected ? Qt.rgba(0.80, 0.65, 0.97, 0.16) : (wThMa.containsMouse ? win.cSurface0 : win.cMantle)
                                                border.width: selected ? 1.5 : 1
                                                border.color: selected ? win.cMauve : (wThMa.containsMouse ? win.cOverlay : win.cSurface0)

                                                Behavior on color { ColorAnimation { duration: 140 } }
                                                Behavior on border.color { ColorAnimation { duration: 140 } }
                                                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

                                                ColumnLayout {
                                                    anchors.fill: parent
                                                    anchors.margins: 10
                                                    spacing: 5
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        Text { text: (selected ? "✓ " : "") + modelData.name; color: selected ? win.cMauve : win.cText; font.pixelSize: 13; font.bold: true; Layout.fillWidth: true }
                                                        Row {
                                                            spacing: 4
                                                            Repeater {
                                                                model: modelData.swatches
                                                                Rectangle { width: 11; height: 11; radius: 6; color: modelData }
                                                            }
                                                        }
                                                    }
                                                    Text { text: modelData.desc; color: win.cMuted; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                                                }

                                                MouseArea {
                                                    id: wThMa
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: win.setDraft("hud_theme", modelData.id)
                                                }
                                            }
                                        }
                                    }

                                    KSlider {
                                        title: "Edge Glow Thickness"
                                        from: 0.5; to: 1.8; stepSize: 0.05
                                        value: Number(win.getDraft("hud_glow_intensity", 1.0))
                                        valueText: Math.round(Number(win.getDraft("hud_glow_intensity", 1.0)) * 100) + "%"
                                        onMovedValue: v => win.setDraft("hud_glow_intensity", Number(v.toFixed(2)))
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 4
                                        Text { text: "Wake Words (comma-separated)"; color: win.cText; font.pixelSize: 13; font.bold: true }
                                        KInput {
                                            Layout.fillWidth: true
                                            text: win.getDraft("wake_words", "kale,kael,hey kale,hey kael")
                                            onTextEdited: win.setDraft("wake_words", text)
                                        }
                                        Text { text: "Tip: Include phonetic spellings like 'kale' alongside 'kael' for super snappy offline detection."; color: win.cMuted; font.pixelSize: 11 }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Bottom Wizard Footer with Morphing Progress Dots & Smooth Buttons
            RowLayout {
                Layout.fillWidth: true
                KButton {
                    text: "← Back"
                    opacity: win.welcomeStep > 0 ? 1.0 : 0.0
                    enabled: win.welcomeStep > 0
                    Behavior on opacity { NumberAnimation { duration: 180 } }
                    onClicked: win.goToWelcomeStep(win.welcomeStep - 1)
                }

                Item { Layout.fillWidth: true }

                // Morphing pill dot stepper
                Row {
                    spacing: 8
                    Repeater {
                        model: 4
                        delegate: Rectangle {
                            readonly property bool isCur: index === win.welcomeStep
                            width: isCur ? 26 : 8
                            height: 8
                            radius: 4
                            color: isCur ? win.cMauve : (index < win.welcomeStep ? win.cGreen : win.cSurface1)
                            Behavior on width { NumberAnimation { duration: 280; easing.type: Easing.OutExpo } }
                            Behavior on color { ColorAnimation { duration: 200 } }
                            MouseArea {
                                anchors.fill: parent
                                anchors.margins: -4
                                cursorShape: Qt.PointingHandCursor
                                onClicked: win.goToWelcomeStep(index)
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                KButton {
                    text: win.welcomeStep === 0 ? "Let's Set Up Kael →" : "Next →"
                    primary: true
                    visible: win.welcomeStep < 3
                    onClicked: win.goToWelcomeStep(win.welcomeStep + 1)
                }
                KButton {
                    text: "Save & Launch Kael ✓"
                    primary: true
                    visible: win.welcomeStep === 3
                    onClicked: {
                        backend.finishOnboarding(JSON.stringify(win.draft), win.draftApiKey);
                        win.inWelcomeMode = false;
                    }
                }
            }
        }
    }

    // ==================== 2. MAIN SETTINGS DASHBOARD ====================

    RowLayout {
        id: mainDashboard
        anchors.fill: parent
        spacing: 0
        visible: opacity > 0.01
        opacity: !win.inWelcomeMode ? 1.0 : 0.0
        scale: !win.inWelcomeMode ? 1.0 : 0.985
        Behavior on opacity { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }

        // Left Sidebar Rail
        Rectangle {
            Layout.preferredWidth: 236
            Layout.fillHeight: true
            color: win.cMantle

            Rectangle {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: 1
                color: win.cSurface0
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 8

                // App Header with live pulsing status dot
                RowLayout {
                    Layout.fillWidth: true
                    Layout.bottomMargin: 8
                    spacing: 10
                    Rectangle {
                        width: 38; height: 38; radius: 11
                        color: win.cBase
                        border.width: 1.5
                        border.color: win.cMauve
                        Text { anchors.centerIn: parent; text: "K"; color: win.cMauve; font.pixelSize: 19; font.bold: true }
                    }
                    ColumnLayout {
                        spacing: 2
                        Text { text: "Kael Settings"; color: win.cText; font.pixelSize: 15; font.bold: true }
                        RowLayout {
                            spacing: 6
                            Item {
                                width: 10; height: 10
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 10; height: 10; radius: 5
                                    visible: backend.kaelRunning && !backend.setupModeActive
                                    color: Qt.rgba(0.65, 0.89, 0.63, 0.35)
                                    SequentialAnimation on scale {
                                        running: backend.kaelRunning && !backend.setupModeActive && !win.inWelcomeMode
                                        loops: Animation.Infinite
                                        NumberAnimation { from: 0.9; to: 1.9; duration: 1300; easing.type: Easing.OutCubic }
                                    }
                                    SequentialAnimation on opacity {
                                        running: backend.kaelRunning && !backend.setupModeActive && !win.inWelcomeMode
                                        loops: Animation.Infinite
                                        NumberAnimation { from: 0.7; to: 0.0; duration: 1300; easing.type: Easing.OutCubic }
                                    }
                                }
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 8; height: 8; radius: 4
                                    color: backend.setupModeActive ? win.cCyan : (backend.kaelRunning ? win.cGreen : win.cRed)
                                    Behavior on color { ColorAnimation { duration: 180 } }
                                }
                            }
                            Text {
                                text: backend.setupModeActive ? "Setup Mode (Paused)" : (backend.kaelRunning ? "Listening" : "Stopped")
                                color: backend.setupModeActive ? win.cCyan : (backend.kaelRunning ? win.cGreen : win.cMuted)
                                font.pixelSize: 11
                            }
                        }
                    }
                }

                // Sidebar Navigation List with Smooth Sliding Active Pill!
                Item {
                    Layout.fillWidth: true
                    implicitHeight: 7 * 44

                    // Sliding glowing background indicator
                    Rectangle {
                        id: navActivePill
                        x: 0
                        y: win.currentTab * 44
                        width: parent.width
                        height: 40
                        radius: 10
                        color: Qt.rgba(0.80, 0.65, 0.97, 0.16)
                        border.width: 1
                        border.color: Qt.rgba(0.80, 0.65, 0.97, 0.38)
                        Behavior on y { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }

                        Rectangle {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 3
                            width: 3
                            height: 20
                            radius: 2
                            color: win.cMauve
                        }
                    }

                    Column {
                        anchors.fill: parent
                        spacing: 4
                        Repeater {
                            model: [
                                { label: "Overview", icon: "◈" },
                                { label: "API & Brain", icon: "⚡" },
                                { label: "Voice & Persona", icon: "♪" },
                                { label: "Appearance", icon: "✦" },
                                { label: "Wake Word & Mic", icon: "◉" },
                                { label: "Memory & Notes", icon: "▤" },
                                { label: "About", icon: "ⓘ" }
                            ]
                            delegate: Rectangle {
                                readonly property bool active: win.currentTab === index
                                width: parent.width
                                height: 40
                                radius: 10
                                color: (!active && navMa.containsMouse) ? win.cBase : "transparent"
                                Behavior on color { ColorAnimation { duration: 120 } }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 14
                                    anchors.rightMargin: 12
                                    spacing: 10
                                    Text {
                                        text: modelData.icon
                                        color: active ? win.cMauve : win.cMuted
                                        font.pixelSize: 14
                                        Behavior on color { ColorAnimation { duration: 150 } }
                                    }
                                    Text {
                                        text: modelData.label
                                        color: active ? win.cText : win.cSubtext
                                        font.pixelSize: 13
                                        font.weight: active ? Font.Bold : Font.Medium
                                        Layout.fillWidth: true
                                        Behavior on color { ColorAnimation { duration: 150 } }
                                    }
                                }

                                MouseArea {
                                    id: navMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: win.switchTab(index)
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                // Setup Quiet Mode toggle card in sidebar
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: smRow.implicitHeight + 16
                    radius: 10
                    color: backend.setupModeActive ? Qt.rgba(0.45, 0.78, 0.93, 0.12) : win.cBase
                    border.width: 1
                    border.color: backend.setupModeActive ? Qt.rgba(0.45, 0.78, 0.93, 0.42) : win.cSurface0
                    Behavior on color { ColorAnimation { duration: 180 } }
                    Behavior on border.color { ColorAnimation { duration: 180 } }

                    RowLayout {
                        id: smRow
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 8
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text { text: "Setup Mode"; color: backend.setupModeActive ? win.cCyan : win.cText; font.pixelSize: 12; font.bold: true }
                            Text { text: "Pause wake-word"; color: win.cMuted; font.pixelSize: 10 }
                        }
                        KSwitch {
                            checked: backend.setupModeManual
                            onToggled: v => backend.setSetupModeManual(v)
                        }
                    }
                }

                Text {
                    text: backend.desktopLabel
                    color: win.cMuted
                    font.pixelSize: 10
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                    Layout.leftMargin: 4
                }

                KButton {
                    Layout.fillWidth: true
                    text: "✦ Welcome Setup"
                    onClicked: {
                        backend.stopVoicePreview();
                        backend.stopMicTest();
                        win.welcomeStep = 0;
                        win.inWelcomeMode = true;
                    }
                }
            }
        }

        // Right Content Workspace
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Top Action Bar
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 62
                color: win.cCrust

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 1
                    color: win.cSurface0
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 24
                    anchors.rightMargin: 24
                    spacing: 12

                    Text {
                        text: ["Overview & Status", "API Key & Brain", "Voice & Personality", "HUD Looks & Theme", "Wake Word & Microphone", "Memory & Notes", "About Kael"][win.currentTab]
                        color: win.cText
                        font.pixelSize: 18
                        font.bold: true
                    }

                    KBadge {
                        visible: win.dirty
                        label: "Unsaved changes"
                        badgeColor: win.cPeach
                        SequentialAnimation on opacity {
                            running: win.dirty
                            loops: Animation.Infinite
                            NumberAnimation { from: 0.72; to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 1.0; to: 0.72; duration: 900; easing.type: Easing.InOutSine }
                        }
                    }

                    Item { Layout.fillWidth: true }

                    KButton {
                        text: "Preview Glow"
                        onClicked: backend.previewHud(
                            win.getDraft("hud_theme", "apple_rainbow"),
                            Number(win.getDraft("hud_glow_intensity", 1.0)),
                            Number(win.getDraft("hud_glow_speed", 1.0)),
                            Boolean(win.getDraft("hud_show_captions", true)),
                            Number(win.getDraft("hud_caption_scale", 1.0))
                        )
                    }

                    KButton {
                        text: win.dirty ? "Save & Apply ✓" : "Saved"
                        primary: win.dirty
                        onClicked: win.saveDraft(false)
                    }
                }
            }

            // Tab Pages Stack with Smooth Slide-Up + Fade Transition
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                Item {
                    id: tabAnimWrap
                    width: parent.width
                    height: parent.height
                    y: 0

                    ParallelAnimation {
                        id: tabTransition
                        NumberAnimation {
                            target: tabAnimWrap
                            property: "opacity"
                            from: 0.0; to: 1.0
                            duration: 210
                            easing.type: Easing.OutCubic
                        }
                        NumberAnimation {
                            target: tabAnimWrap
                            property: "y"
                            from: 14; to: 0
                            duration: 220
                            easing.type: Easing.OutCubic
                        }
                    }

                    StackLayout {
                        anchors.fill: parent
                        currentIndex: win.currentTab

                        // ============ TAB 0: OVERVIEW ============
                        Flickable {
                            contentWidth: width
                            contentHeight: ovCol.implicitHeight + 48
                            clip: true
                            ColumnLayout {
                                id: ovCol
                                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                anchors.margins: 24
                                spacing: 16

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: heroInner.implicitHeight + 36
                                    ColumnLayout {
                                        id: heroInner
                                        anchors.fill: parent
                                        anchors.margins: 18
                                        spacing: 14

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 14
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 4
                                                RowLayout {
                                                    spacing: 10
                                                    Text { text: win.getDraft("assistant_name", "Kael") + " Assistant"; color: win.cText; font.pixelSize: 19; font.bold: true }
                                                    KBadge {
                                                        label: backend.kaelRunning ? "ACTIVE" : "STOPPED"
                                                        badgeColor: backend.kaelRunning ? win.cGreen : win.cRed
                                                    }
                                                    KBadge {
                                                        label: backend.hudRunning ? "HUD READY" : "HUD OFF"
                                                        badgeColor: backend.hudRunning ? win.cCyan : win.cMuted
                                                    }
                                                }
                                                Text {
                                                    text: "Voice: " + win.getDraft("voice", "Schedar") + "  •  Theme: " + win.getDraft("hud_theme", "apple_rainbow") + "  •  Wake: " + win.getDraft("wake_words", "kael")
                                                    color: win.cSubtext
                                                    font.pixelSize: 12
                                                    elide: Text.ElideRight
                                                    Layout.fillWidth: true
                                                }
                                            }
                                        }

                                        RowLayout {
                                            spacing: 10
                                            KButton { text: "Wake Kael Now"; primary: true; onClicked: backend.wakeKael() }
                                            KButton { text: "Restart Services"; onClicked: backend.restartServices() }
                                            KButton { text: "Live Logs"; onClicked: backend.openLogsTerminal() }
                                            KButton { text: "Notes Folder"; onClicked: backend.openNotesFolder() }
                                        }
                                    }
                                }

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: svcCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: svcCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 14

                                        KToggleRow {
                                            title: "Run Kael & HUD daemon"
                                            subtitle: "Keeps offline wake-word listening and the Wayland GPU glow ready in the background."
                                            checked: backend.kaelRunning
                                            onToggled: v => backend.setDaemonRunning(v)
                                        }
                                        Rectangle { Layout.fillWidth: true; height: 1; color: win.cSurface0 }
                                        KToggleRow {
                                            title: "Auto-start on desktop login"
                                            subtitle: "Enables kael.service and kael-hud.service via systemd user session."
                                            checked: backend.autostartEnabled
                                            onToggled: v => backend.setAutostart(v)
                                        }
                                    }
                                }

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: chkCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: chkCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 10
                                        Text { text: "Environment Diagnostics"; color: win.cText; font.pixelSize: 14; font.bold: true }
                                        GridLayout {
                                            Layout.fillWidth: true
                                            columns: 2
                                            columnSpacing: 16
                                            rowSpacing: 10
                                            Repeater {
                                                model: backend.systemChecks
                                                delegate: RowLayout {
                                                    Layout.fillWidth: true
                                                    spacing: 8
                                                    Rectangle { width: 9; height: 9; radius: 5; color: modelData.ok ? win.cGreen : win.cPeach }
                                                    ColumnLayout {
                                                        spacing: 1
                                                        Text { text: modelData.name; color: win.cText; font.pixelSize: 12; font.weight: Font.Medium }
                                                        Text { text: modelData.detail; color: win.cMuted; font.pixelSize: 11 }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // ============ TAB 1: API & BRAIN ============
                        Flickable {
                            contentWidth: width
                            contentHeight: apiCol.implicitHeight + 48
                            clip: true
                            ColumnLayout {
                                id: apiCol
                                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                anchors.margins: 24
                                spacing: 16

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: apiCardCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: apiCardCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 12

                                        Text { text: "Google Gemini API Key"; color: win.cText; font.pixelSize: 14; font.bold: true }
                                        Text { text: "Stored locally in .env (chmod 600). Used for Gemini 3.8 Live voice & Gemini vision."; color: win.cMuted; font.pixelSize: 12 }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8
                                            KInput {
                                                Layout.fillWidth: true
                                                placeholderText: "Enter your GEMINI_API_KEY"
                                                echoMode: win.revealApiKey ? TextInput.Normal : TextInput.Password
                                                text: win.draftApiKey
                                                onTextEdited: {
                                                    win.draftApiKey = text;
                                                    win.dirty = true;
                                                }
                                            }
                                            KButton { text: win.revealApiKey ? "Hide" : "Show"; onClicked: win.revealApiKey = !win.revealApiKey }
                                        }

                                        RowLayout {
                                            spacing: 10
                                            KButton {
                                                text: backend.apiTesting ? "Testing..." : "Test Connection"
                                                primary: true
                                                disabled: backend.apiTesting
                                                onClicked: backend.testApiKey(win.draftApiKey)
                                            }
                                            KButton {
                                                text: "Open Google AI Studio ↗"
                                                onClicked: backend.openUrl("https://aistudio.google.com/apikey")
                                            }
                                        }

                                        Rectangle {
                                            visible: backend.apiTestMessage !== ""
                                            Layout.fillWidth: true
                                            implicitHeight: apiStatusTxt.implicitHeight + 16
                                            radius: 8
                                            color: backend.apiTestOk ? Qt.rgba(0.65, 0.89, 0.63, 0.14) : Qt.rgba(0.95, 0.55, 0.66, 0.14)
                                            border.width: 1
                                            border.color: backend.apiTestOk ? Qt.rgba(0.65, 0.89, 0.63, 0.4) : Qt.rgba(0.95, 0.55, 0.66, 0.4)
                                            Text {
                                                id: apiStatusTxt
                                                anchors.fill: parent
                                                anchors.margins: 8
                                                text: backend.apiTestMessage
                                                color: backend.apiTestOk ? win.cGreen : win.cRed
                                                font.pixelSize: 12
                                                wrapMode: Text.WordWrap
                                            }
                                        }
                                    }
                                }

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: brainCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: brainCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 16

                                        KSlider {
                                            title: "Idle Standby Timeout"
                                            subtitle: "Seconds of silence after a reply before Kael goes back to standby."
                                            from: 8; to: 90; stepSize: 2
                                            value: Number(win.getDraft("idle_timeout", 18))
                                            valueText: Math.round(Number(win.getDraft("idle_timeout", 18))) + "s"
                                            onMovedValue: v => win.setDraft("idle_timeout", Math.round(v))
                                        }

                                        Rectangle { Layout.fillWidth: true; height: 1; color: win.cSurface0 }

                                        KToggleRow {
                                            title: "Speaker Echo Guard + Smart Barge-In"
                                            subtitle: "Prevents Kael from hearing his own speakers while still letting you interrupt him with your voice."
                                            checked: Boolean(win.getDraft("echo_guard", true))
                                            onToggled: v => win.setDraft("echo_guard", v)
                                        }

                                        KSlider {
                                            title: "Smart Barge-In Sensitivity"
                                            subtitle: "Lower = easier to interrupt mid-sentence; higher = resists loud speaker echo."
                                            from: 0.15; to: 0.70; stepSize: 0.02
                                            value: Number(win.getDraft("barge_in_threshold", 0.32))
                                            valueText: Number(win.getDraft("barge_in_threshold", 0.32)).toFixed(2)
                                            onMovedValue: v => win.setDraft("barge_in_threshold", Number(v.toFixed(2)))
                                        }

                                        Rectangle { Layout.fillWidth: true; height: 1; color: win.cSurface0 }

                                        KToggleRow {
                                            title: "Built-in Google Search Grounding (Paid Tier)"
                                            subtitle: "Keep OFF on free-tier keys (Kael already includes free DuckDuckGo web search)."
                                            checked: Boolean(win.getDraft("google_search", false))
                                            onToggled: v => win.setDraft("google_search", v)
                                        }
                                    }
                                }
                            }
                        }

                        // ============ TAB 2: VOICE & PERSONA ============
                        Flickable {
                            contentWidth: width
                            contentHeight: vpCol.implicitHeight + 48
                            clip: true
                            ColumnLayout {
                                id: vpCol
                                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                anchors.margins: 24
                                spacing: 16

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: voiceCardCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: voiceCardCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 12

                                        RowLayout {
                                            Layout.fillWidth: true
                                            Text { text: "Gemini Studio Voices"; color: win.cText; font.pixelSize: 14; font.bold: true; Layout.fillWidth: true }
                                            Text { text: "Live-streamed & cached · wake-word auto-paused during preview"; color: win.cMuted; font.pixelSize: 11 }
                                        }

                                        GridLayout {
                                            Layout.fillWidth: true
                                            columns: 3
                                            columnSpacing: 10
                                            rowSpacing: 10

                                            Repeater {
                                                model: backend.voiceCatalog
                                                delegate: Rectangle {
                                                    readonly property bool selected: win.getDraft("voice", "Schedar") === modelData.id
                                                    readonly property bool isPlaying: backend.voicePreviewing && backend.previewVoiceId === modelData.id
                                                    Layout.fillWidth: true
                                                    implicitHeight: 74
                                                    radius: 11
                                                    scale: vCardMa.pressed ? 0.975 : (vCardMa.containsMouse ? 1.015 : 1.0)
                                                    color: selected ? Qt.rgba(0.80, 0.65, 0.97, 0.16) : (vCardMa.containsMouse ? win.cSurface0 : win.cMantle)
                                                    border.width: selected ? 1.5 : 1
                                                    border.color: selected ? win.cMauve : (vCardMa.containsMouse ? win.cOverlay : win.cSurface0)

                                                    Behavior on color { ColorAnimation { duration: 140 } }
                                                    Behavior on border.color { ColorAnimation { duration: 140 } }
                                                    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

                                                    RowLayout {
                                                        anchors.fill: parent
                                                        anchors.margins: 10
                                                        spacing: 6
                                                        ColumnLayout {
                                                            Layout.fillWidth: true
                                                            spacing: 2
                                                            Text { text: (selected ? "✓ " : "") + modelData.label; color: selected ? win.cMauve : win.cText; font.pixelSize: 13; font.bold: true }
                                                            Text { text: modelData.vibe; color: win.cBlue; font.pixelSize: 10 }
                                                            Text { text: modelData.desc; color: win.cMuted; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                                                        }
                                                        KVoicePlayButton {
                                                            playing: isPlaying
                                                            onClicked: backend.previewVoice(modelData.id, win.draftApiKey)
                                                        }
                                                    }

                                                    MouseArea {
                                                        id: vCardMa
                                                        anchors.fill: parent
                                                        z: -1
                                                        hoverEnabled: true
                                                        cursorShape: Qt.PointingHandCursor
                                                        onClicked: win.setDraft("voice", modelData.id)
                                                    }
                                                }
                                            }
                                        }

                                        KSlider {
                                            title: "AI HUD Voice FX Sheen"
                                            subtitle: "0% = pure natural Gemini studio voice; higher adds subtle holographic metallic resonance."
                                            from: 0.0; to: 1.0; stepSize: 0.05
                                            value: Number(win.getDraft("voice_fx", 0.0))
                                            valueText: Math.round(Number(win.getDraft("voice_fx", 0.0)) * 100) + "%"
                                            onMovedValue: v => win.setDraft("voice_fx", Number(v.toFixed(2)))
                                        }
                                    }
                                }

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: persCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: persCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 14

                                        Text { text: "Personality & Behavior"; color: win.cText; font.pixelSize: 14; font.bold: true }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 12
                                            ColumnLayout {
                                                Layout.preferredWidth: 180
                                                spacing: 4
                                                Text { text: "Assistant Name"; color: win.cSubtext; font.pixelSize: 12 }
                                                KInput {
                                                    Layout.fillWidth: true
                                                    text: win.getDraft("assistant_name", "Kael")
                                                    onTextEdited: win.setDraft("assistant_name", text)
                                                }
                                            }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 4
                                                Text { text: "Spoken Languages"; color: win.cSubtext; font.pixelSize: 12 }
                                                KInput {
                                                    Layout.fillWidth: true
                                                    text: win.getDraft("languages", "English and Vietnamese")
                                                    onTextEdited: win.setDraft("languages", text)
                                                }
                                            }
                                        }

                                        GridLayout {
                                            Layout.fillWidth: true
                                            columns: 2
                                            columnSpacing: 10
                                            rowSpacing: 10

                                            Repeater {
                                                model: backend.personaPresets
                                                delegate: Rectangle {
                                                    readonly property bool selected: win.getDraft("persona_preset", "snarky") === modelData.id
                                                    Layout.fillWidth: true
                                                    implicitHeight: 62
                                                    radius: 11
                                                    scale: pCardMa.pressed ? 0.98 : (pCardMa.containsMouse ? 1.012 : 1.0)
                                                    color: selected ? Qt.rgba(0.54, 0.71, 0.98, 0.16) : (pCardMa.containsMouse ? win.cSurface0 : win.cMantle)
                                                    border.width: selected ? 1.5 : 1
                                                    border.color: selected ? win.cBlue : (pCardMa.containsMouse ? win.cOverlay : win.cSurface0)

                                                    Behavior on color { ColorAnimation { duration: 140 } }
                                                    Behavior on border.color { ColorAnimation { duration: 140 } }
                                                    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

                                                    ColumnLayout {
                                                        anchors.fill: parent
                                                        anchors.margins: 10
                                                        spacing: 2
                                                        Text { text: (selected ? "✓ " : "") + modelData.name; color: selected ? win.cBlue : win.cText; font.pixelSize: 13; font.bold: true }
                                                        Text { text: modelData.tagline; color: win.cMuted; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                                                    }
                                                    MouseArea {
                                                        id: pCardMa
                                                        anchors.fill: parent
                                                        hoverEnabled: true
                                                        cursorShape: Qt.PointingHandCursor
                                                        onClicked: win.setDraft("persona_preset", modelData.id)
                                                    }
                                                }
                                            }
                                        }

                                        // Always visible here (highlights & expands further when Custom Personality is selected!)
                                        KCustomPersonaEditor {
                                            expanded: true
                                        }

                                        KToggleRow {
                                            title: "Allow light casual swearing"
                                            subtitle: "Occasional natural swearing ('damn', 'hell', 'crap') when it fits."
                                            checked: Boolean(win.getDraft("allow_swearing", true))
                                            onToggled: v => win.setDraft("allow_swearing", v)
                                        }

                                        KToggleRow {
                                            title: "Play along with silly roleplay & bits"
                                            subtitle: "Groans and roasts you, but still begrudgingly plays along."
                                            checked: Boolean(win.getDraft("comply_roleplay", true))
                                            onToggled: v => win.setDraft("comply_roleplay", v)
                                        }
                                    }
                                }
                            }
                        }

                        // ============ TAB 3: APPEARANCE (HUD LOOKS) ============
                        Flickable {
                            contentWidth: width
                            contentHeight: appCol.implicitHeight + 48
                            clip: true
                            ColumnLayout {
                                id: appCol
                                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                anchors.margins: 24
                                spacing: 16

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: themeCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: themeCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 12

                                        RowLayout {
                                            Layout.fillWidth: true
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2
                                                Text { text: "GPU Edge-Glow Theme"; color: win.cText; font.pixelSize: 14; font.bold: true }
                                                Text { text: "Changes the OpenGL screen-edge glow AND matching caption/image card borders live."; color: win.cMuted; font.pixelSize: 12 }
                                            }
                                            KButton {
                                                text: "✦ Live Preview"
                                                primary: true
                                                onClicked: backend.previewHud(
                                                    win.getDraft("hud_theme", "apple_rainbow"),
                                                    Number(win.getDraft("hud_glow_intensity", 1.0)),
                                                    Number(win.getDraft("hud_glow_speed", 1.0)),
                                                    Boolean(win.getDraft("hud_show_captions", true)),
                                                    Number(win.getDraft("hud_caption_scale", 1.0))
                                                )
                                            }
                                        }

                                        GridLayout {
                                            Layout.fillWidth: true
                                            columns: 2
                                            columnSpacing: 10
                                            rowSpacing: 10

                                            Repeater {
                                                model: backend.hudThemes
                                                delegate: Rectangle {
                                                    readonly property bool selected: win.getDraft("hud_theme", "apple_rainbow") === modelData.id
                                                    Layout.fillWidth: true
                                                    implicitHeight: 74
                                                    radius: 12
                                                    scale: thCardMa.pressed ? 0.98 : (thCardMa.containsMouse ? 1.012 : 1.0)
                                                    color: selected ? Qt.rgba(0.80, 0.65, 0.97, 0.16) : (thCardMa.containsMouse ? win.cSurface0 : win.cMantle)
                                                    border.width: selected ? 1.5 : 1
                                                    border.color: selected ? win.cMauve : (thCardMa.containsMouse ? win.cOverlay : win.cSurface0)

                                                    Behavior on color { ColorAnimation { duration: 140 } }
                                                    Behavior on border.color { ColorAnimation { duration: 140 } }
                                                    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

                                                    ColumnLayout {
                                                        anchors.fill: parent
                                                        anchors.margins: 12
                                                        spacing: 6
                                                        RowLayout {
                                                            Layout.fillWidth: true
                                                            Text { text: (selected ? "✓ " : "") + modelData.name; color: selected ? win.cMauve : win.cText; font.pixelSize: 13; font.bold: true; Layout.fillWidth: true }
                                                            Rectangle {
                                                                width: 58; height: 14; radius: 7
                                                                gradient: Gradient {
                                                                    orientation: Gradient.Horizontal
                                                                    GradientStop { position: 0.0; color: modelData.swatches[0] }
                                                                    GradientStop { position: 0.5; color: modelData.swatches[1] }
                                                                    GradientStop { position: 1.0; color: modelData.swatches[2] }
                                                                }
                                                            }
                                                        }
                                                        Text { text: modelData.desc; color: win.cMuted; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                                                    }

                                                    MouseArea {
                                                        id: thCardMa
                                                        anchors.fill: parent
                                                        hoverEnabled: true
                                                        cursorShape: Qt.PointingHandCursor
                                                        onClicked: win.setDraft("hud_theme", modelData.id)
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: hudSlidersCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: hudSlidersCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 16

                                        KSlider {
                                            title: "Glow Thickness & Bloom"
                                            subtitle: "Controls how wide and vivid the border aura extends into the screen."
                                            from: 0.5; to: 1.8; stepSize: 0.05
                                            value: Number(win.getDraft("hud_glow_intensity", 1.0))
                                            valueText: Math.round(Number(win.getDraft("hud_glow_intensity", 1.0)) * 100) + "%"
                                            onMovedValue: v => win.setDraft("hud_glow_intensity", Number(v.toFixed(2)))
                                        }

                                        KSlider {
                                            title: "Glow Flow Speed"
                                            subtitle: "Animation speed of the liquid rainbow edge waves."
                                            from: 0.4; to: 2.0; stepSize: 0.1
                                            value: Number(win.getDraft("hud_glow_speed", 1.0))
                                            valueText: Number(win.getDraft("hud_glow_speed", 1.0)).toFixed(1) + "x"
                                            onMovedValue: v => win.setDraft("hud_glow_speed", Number(v.toFixed(1)))
                                        }

                                        Rectangle { Layout.fillWidth: true; height: 1; color: win.cSurface0 }

                                        KToggleRow {
                                            title: "Show Live Dual Captions"
                                            subtitle: "Displays frosted-glass word-by-word captions of both your voice and Kael's reply."
                                            checked: Boolean(win.getDraft("hud_show_captions", true))
                                            onToggled: v => win.setDraft("hud_show_captions", v)
                                        }

                                        KSlider {
                                            title: "Caption Text Size"
                                            from: 0.8; to: 1.4; stepSize: 0.05
                                            value: Number(win.getDraft("hud_caption_scale", 1.0))
                                            valueText: Math.round(Number(win.getDraft("hud_caption_scale", 1.0)) * 100) + "%"
                                            onMovedValue: v => win.setDraft("hud_caption_scale", Number(v.toFixed(2)))
                                        }

                                        KSlider {
                                            title: "Image Card Auto-Hide Duration"
                                            subtitle: "How long floating image cards stay on screen in standby before fading out."
                                            from: 5; to: 30; stepSize: 1
                                            value: Number(win.getDraft("hud_image_duration", 14))
                                            valueText: Math.round(Number(win.getDraft("hud_image_duration", 14))) + "s"
                                            onMovedValue: v => win.setDraft("hud_image_duration", Math.round(v))
                                        }
                                    }
                                }
                            }
                        }

                        // ============ TAB 4: WAKE WORD & MIC ============
                        Flickable {
                            contentWidth: width
                            contentHeight: wwCol.implicitHeight + 48
                            clip: true
                            ColumnLayout {
                                id: wwCol
                                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                anchors.margins: 24
                                spacing: 16

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: wwCardCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: wwCardCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 14

                                        Text { text: "Offline Vosk Wake Word"; color: win.cText; font.pixelSize: 14; font.bold: true }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 4
                                            Text { text: "Wake Phrases (comma-separated)"; color: win.cSubtext; font.pixelSize: 12 }
                                            KInput {
                                                Layout.fillWidth: true
                                                text: win.getDraft("wake_words", "kale,kael,hey kale,hey kael")
                                                onTextEdited: win.setDraft("wake_words", text)
                                            }
                                            Text { text: "Changing wake words automatically restarts kael.service when you click Save & Apply."; color: win.cMuted; font.pixelSize: 11 }
                                        }

                                        KSlider {
                                            title: "Recognition Confidence Threshold"
                                            subtitle: "Higher reduces false wakes from background chatter; lower makes triggering easier."
                                            from: 0.30; to: 0.95; stepSize: 0.05
                                            value: Number(win.getDraft("wake_confidence", 0.70))
                                            valueText: Math.round(Number(win.getDraft("wake_confidence", 0.70)) * 100) + "%"
                                            onMovedValue: v => win.setDraft("wake_confidence", Number(v.toFixed(2)))
                                        }

                                        KSlider {
                                            title: "Close-Mic Loudness Gate (Min RMS)"
                                            subtitle: "Audio quieter than this level is ignored in standby (blocks distant room noise)."
                                            from: 50; to: 900; stepSize: 10
                                            value: Number(win.getDraft("wake_min_rms", 220))
                                            valueText: Math.round(Number(win.getDraft("wake_min_rms", 220))) + " RMS"
                                            onMovedValue: v => win.setDraft("wake_min_rms", Math.round(v))
                                        }
                                    }
                                }

                                // Live Mic Calibration Meter
                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: micCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: micCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 12

                                        RowLayout {
                                            Layout.fillWidth: true
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2
                                                Text { text: "Live Microphone Calibration"; color: win.cText; font.pixelSize: 14; font.bold: true }
                                                Text { text: "Say 'Kael' at normal speaking distance and make sure the bar crosses the white threshold line (wake-word is paused while testing!)."; color: win.cMuted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                            }
                                            KButton {
                                                text: backend.micTesting ? "Stop Mic Test" : "Test Microphone"
                                                primary: !backend.micTesting
                                                danger: backend.micTesting
                                                onClicked: backend.toggleMicTest()
                                            }
                                        }

                                        Item {
                                            Layout.fillWidth: true
                                            height: 28
                                            readonly property real maxScale: 1000.0
                                            readonly property real rmsNorm: Math.min(1.0, backend.micRms / maxScale)
                                            readonly property real gateNorm: Math.min(1.0, Number(win.getDraft("wake_min_rms", 220)) / maxScale)
                                            readonly property bool aboveGate: backend.micRms >= Number(win.getDraft("wake_min_rms", 220))

                                            Rectangle {
                                                anchors.fill: parent
                                                radius: 8
                                                color: win.cMantle
                                                border.width: 1
                                                border.color: win.cSurface1

                                                Rectangle {
                                                    anchors.left: parent.left
                                                    anchors.top: parent.top
                                                    anchors.bottom: parent.bottom
                                                    anchors.margins: 3
                                                    width: Math.max(0, (parent.width - 6) * parent.parent.rmsNorm)
                                                    radius: 5
                                                    color: parent.parent.aboveGate ? win.cGreen : win.cMauve
                                                    Behavior on width { NumberAnimation { duration: 55 } }
                                                    Behavior on color { ColorAnimation { duration: 100 } }
                                                }

                                                Rectangle {
                                                    x: Math.max(4, Math.min(parent.width - 6, parent.width * parent.parent.gateNorm))
                                                    y: 2
                                                    width: 2.5
                                                    height: parent.height - 4
                                                    color: "#FFFFFF"
                                                    Behavior on x { NumberAnimation { duration: 100 } }
                                                }
                                            }
                                        }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            Text {
                                                text: backend.micTesting
                                                    ? ("Live level: " + Math.round(backend.micRms) + " RMS" + (backend.micRms >= Number(win.getDraft("wake_min_rms", 220)) ? "  (Above gate ✓)" : "  (Below gate)"))
                                                    : "Click 'Test Microphone' to see your live voice level."
                                                color: backend.micTesting && backend.micRms >= Number(win.getDraft("wake_min_rms", 220)) ? win.cGreen : win.cSubtext
                                                font.pixelSize: 12
                                            }
                                            Item { Layout.fillWidth: true }
                                            Text {
                                                text: "Gate: " + Math.round(Number(win.getDraft("wake_min_rms", 220))) + " RMS"
                                                color: win.cMuted
                                                font.pixelSize: 11
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // ============ TAB 5: MEMORY & NOTES ============
                        Flickable {
                            contentWidth: width
                            contentHeight: memCol.implicitHeight + 48
                            clip: true
                            ColumnLayout {
                                id: memCol
                                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                anchors.margins: 24
                                spacing: 16

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: memCardCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: memCardCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 12

                                        RowLayout {
                                            Layout.fillWidth: true
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2
                                                Text { text: "Persistent Long-Term Memory"; color: win.cText; font.pixelSize: 14; font.bold: true }
                                                Text { text: "Facts Kael automatically remembers every time he wakes up (~/KaelNotes/kael_memory.json)."; color: win.cMuted; font.pixelSize: 12 }
                                            }
                                            KButton { text: "Open ~/KaelNotes"; onClicked: backend.openNotesFolder() }
                                        }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8
                                            KInput {
                                                id: newMemInput
                                                Layout.fillWidth: true
                                                placeholderText: "Add a memory (e.g. 'My name is Alex and I prefer dark mode')..."
                                                onAccepted: {
                                                    backend.addMemory(text);
                                                    text = "";
                                                }
                                            }
                                            KButton {
                                                text: "Add Memory"
                                                primary: true
                                                onClicked: {
                                                    backend.addMemory(newMemInput.text);
                                                    newMemInput.text = "";
                                                }
                                            }
                                        }

                                        Text {
                                            visible: backend.memories.length === 0
                                            text: "No memories saved yet. Tell Kael 'remember that...' or add one above."
                                            color: win.cMuted
                                            font.pixelSize: 12
                                            Layout.topMargin: 6
                                        }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 8
                                            Repeater {
                                                model: backend.memories
                                                delegate: Rectangle {
                                                    Layout.fillWidth: true
                                                    implicitHeight: memRow.implicitHeight + 16
                                                    radius: 10
                                                    color: win.cMantle
                                                    border.width: 1
                                                    border.color: win.cSurface0
                                                    RowLayout {
                                                        id: memRow
                                                        anchors.fill: parent
                                                        anchors.margins: 8
                                                        anchors.leftMargin: 12
                                                        spacing: 10
                                                        Text {
                                                            text: "• " + modelData
                                                            color: win.cText
                                                            font.pixelSize: 12
                                                            wrapMode: Text.WordWrap
                                                            Layout.fillWidth: true
                                                        }
                                                        KButton {
                                                            text: "Remove"
                                                            danger: true
                                                            hPad: 10
                                                            implicitHeight: 28
                                                            onClicked: backend.deleteMemory(index)
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }

                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: resetRow.implicitHeight + 32
                                    RowLayout {
                                        id: resetRow
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 12
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            Text { text: "Reset Settings to Defaults"; color: win.cText; font.pixelSize: 14; font.bold: true }
                                            Text { text: "Restores default voice, personality, glow theme, and thresholds while keeping your API key and memories safe."; color: win.cMuted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                        }
                                        KButton {
                                            text: "Reset Defaults"
                                            danger: true
                                            onClicked: backend.resetDefaults()
                                        }
                                    }
                                }
                            }
                        }

                        // ============ TAB 6: ABOUT ============
                        Flickable {
                            contentWidth: width
                            contentHeight: aboutCol.implicitHeight + 48
                            clip: true
                            ColumnLayout {
                                id: aboutCol
                                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                anchors.margins: 24
                                spacing: 16

                                // Hero Brand & Version Card
                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: aboutHero.implicitHeight + 36
                                    ColumnLayout {
                                        id: aboutHero
                                        anchors.fill: parent
                                        anchors.margins: 18
                                        spacing: 16

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 16

                                            Item {
                                                width: 72; height: 72
                                                Rectangle {
                                                    anchors.centerIn: parent
                                                    width: 72; height: 72; radius: 22
                                                    opacity: 0.42
                                                    gradient: Gradient {
                                                        GradientStop { position: 0.0; color: win.getThemeSwatches()[0] }
                                                        GradientStop { position: 0.5; color: win.getThemeSwatches()[1] }
                                                        GradientStop { position: 1.0; color: win.getThemeSwatches()[2] }
                                                    }
                                                    RotationAnimation on rotation {
                                                        running: !win.inWelcomeMode && win.currentTab === 6
                                                        from: 0; to: 360
                                                        duration: 10000
                                                        loops: Animation.Infinite
                                                    }
                                                }
                                                Rectangle {
                                                    anchors.centerIn: parent
                                                    width: 64; height: 64; radius: 19
                                                    gradient: Gradient {
                                                        GradientStop { position: 0.0; color: "#2A2444" }
                                                        GradientStop { position: 1.0; color: "#181825" }
                                                    }
                                                    border.width: 2
                                                    border.color: win.cMauve
                                                    Text {
                                                        anchors.centerIn: parent
                                                        text: "K"
                                                        font.pixelSize: 30
                                                        font.bold: true
                                                        color: win.cMauve
                                                    }
                                                }
                                            }

                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 5
                                                RowLayout {
                                                    spacing: 8
                                                    Text {
                                                        text: backend.appMeta.name + " AI Voice Assistant"
                                                        color: win.cText
                                                        font.pixelSize: 20
                                                        font.bold: true
                                                    }
                                                    KBadge { label: "v" + backend.appMeta.version; badgeColor: win.cMauve }
                                                    KBadge { label: backend.appMeta.license; badgeColor: win.cGreen }
                                                }
                                                Text {
                                                    text: "Always-listening Linux AI voice assistant with offline Vosk wake word, Gemini 3.8 Live voice & screen vision, hardware-accelerated OpenGL edge glow, and safe desktop automation."
                                                    color: win.cSubtext
                                                    font.pixelSize: 12
                                                    wrapMode: Text.WordWrap
                                                    Layout.fillWidth: true
                                                }
                                            }
                                        }

                                        Flow {
                                            Layout.fillWidth: true
                                            spacing: 10
                                            KButton {
                                                text: "GitHub Repository ↗"
                                                primary: true
                                                onClicked: backend.openUrl(backend.appMeta.repoUrl)
                                            }
                                            KButton {
                                                text: "Project Website ↗"
                                                onClicked: backend.openUrl(backend.appMeta.websiteUrl)
                                            }
                                            KButton {
                                                text: "Report an Issue ↗"
                                                onClicked: backend.openUrl(backend.appMeta.issuesUrl)
                                            }
                                            KButton {
                                                text: "Copy Debug Info"
                                                onClicked: backend.copyDiagnostics()
                                            }
                                        }
                                    }
                                }

                                // Credits & Maintenance Card
                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: credCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: credCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 12

                                        Text { text: "Credits & Maintenance"; color: win.cText; font.pixelSize: 14; font.bold: true }

                                        GridLayout {
                                            Layout.fillWidth: true
                                            columns: 2
                                            columnSpacing: 16
                                            rowSpacing: 10

                                            Repeater {
                                                model: [
                                                    { label: "Created / Coded by", value: backend.appMeta.author, accent: win.cMauve },
                                                    { label: "Maintained & Managed by", value: backend.appMeta.maintainer, accent: win.cBlue },
                                                    { label: "Version", value: "v" + backend.appMeta.version, accent: win.cCyan },
                                                    { label: "License", value: backend.appMeta.license, accent: win.cGreen }
                                                ]
                                                delegate: Rectangle {
                                                    Layout.fillWidth: true
                                                    implicitHeight: 54
                                                    radius: 10
                                                    color: win.cMantle
                                                    border.width: 1
                                                    border.color: win.cSurface0
                                                    ColumnLayout {
                                                        anchors.fill: parent
                                                        anchors.margins: 10
                                                        spacing: 2
                                                        Text { text: modelData.label; color: win.cMuted; font.pixelSize: 11 }
                                                        Text { text: modelData.value; color: modelData.accent; font.pixelSize: 13; font.bold: true }
                                                    }
                                                }
                                            }
                                        }

                                        Rectangle { Layout.fillWidth: true; height: 1; color: win.cSurface0 }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 4
                                            Text { text: "Powered By"; color: win.cSubtext; font.pixelSize: 12; font.bold: true }
                                            Text {
                                                text: "Google Gemini 3.8 Live API  •  Vosk Offline Speech Recognition  •  PipeWire / PulseAudio  •  GTK4 + OpenGL GLSL + gtk4-layer-shell  •  Qt6 QML (PyQt6)"
                                                color: win.cMuted
                                                font.pixelSize: 12
                                                wrapMode: Text.WordWrap
                                                Layout.fillWidth: true
                                            }
                                        }
                                    }
                                }

                                // Runtime & Paths Card
                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: sysMetaCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: sysMetaCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 8

                                        Text { text: "Installation & Runtime Info"; color: win.cText; font.pixelSize: 14; font.bold: true }

                                        Repeater {
                                            model: [
                                                { k: "Operating System", v: backend.appMeta.distro },
                                                { k: "Desktop Session", v: backend.appMeta.desktop },
                                                { k: "Python / Qt6", v: "Python " + backend.appMeta.pythonVersion + "  •  Qt " + backend.appMeta.qtVersion },
                                                { k: "Config File", v: backend.appMeta.configPath },
                                                { k: "Install Path", v: backend.appMeta.installDir }
                                            ]
                                            delegate: RowLayout {
                                                Layout.fillWidth: true
                                                spacing: 12
                                                Text { text: modelData.k; color: win.cMuted; font.pixelSize: 12; Layout.preferredWidth: 130 }
                                                Text { text: modelData.v; color: win.cText; font.pixelSize: 12; elide: Text.ElideMiddle; Layout.fillWidth: true }
                                            }
                                        }
                                    }
                                }

                                // Socials Footer Card
                                KCard {
                                    Layout.fillWidth: true
                                    implicitHeight: socCol.implicitHeight + 32
                                    ColumnLayout {
                                        id: socCol
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 12

                                        RowLayout {
                                            Layout.fillWidth: true
                                            Text { text: "Connect with " + backend.appMeta.maintainer; color: win.cText; font.pixelSize: 14; font.bold: true; Layout.fillWidth: true }
                                            Text { text: "Click any icon to open"; color: win.cMuted; font.pixelSize: 11 }
                                        }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 12

                                            Repeater {
                                                model: backend.socials
                                                delegate: Rectangle {
                                                    Layout.fillWidth: true
                                                    implicitHeight: 58
                                                    radius: 12
                                                    scale: socMa.pressed ? 0.96 : (socMa.containsMouse ? 1.025 : 1.0)
                                                    color: socMa.containsMouse ? win.cSurface0 : win.cMantle
                                                    border.width: 1.5
                                                    border.color: socMa.containsMouse ? modelData.accent : win.cSurface0

                                                    Behavior on color { ColorAnimation { duration: 130 } }
                                                    Behavior on border.color { ColorAnimation { duration: 140 } }
                                                    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

                                                    RowLayout {
                                                        anchors.fill: parent
                                                        anchors.leftMargin: 14
                                                        anchors.rightMargin: 14
                                                        spacing: 12

                                                        Rectangle {
                                                            width: 34; height: 34; radius: 10
                                                            color: Qt.rgba(1, 1, 1, 0.05)
                                                            Image {
                                                                anchors.centerIn: parent
                                                                width: 20; height: 20
                                                                source: modelData.icon
                                                                sourceSize: Qt.size(40, 40)
                                                                smooth: true
                                                                fillMode: Image.PreserveAspectFit
                                                            }
                                                        }

                                                        ColumnLayout {
                                                            Layout.fillWidth: true
                                                            spacing: 1
                                                            Text { text: modelData.name; color: socMa.containsMouse ? modelData.accent : win.cText; font.pixelSize: 13; font.bold: true; Behavior on color { ColorAnimation { duration: 130 } } }
                                                            Text { text: modelData.handle; color: win.cMuted; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                                                        }

                                                        Text {
                                                            text: "↗"
                                                            color: socMa.containsMouse ? modelData.accent : win.cMuted
                                                            font.pixelSize: 13
                                                            font.bold: true
                                                        }
                                                    }

                                                    MouseArea {
                                                        id: socMa
                                                        anchors.fill: parent
                                                        hoverEnabled: true
                                                        cursorShape: Qt.PointingHandCursor
                                                        onClicked: backend.openUrl(modelData.url)
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ==================== FLOATING SLIDE-UP TOAST BANNER ====================

    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 22
        anchors.bottomMargin: win.toastVisible ? 22 : 6
        visible: opacity > 0.01
        opacity: win.toastVisible ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 190; easing.type: Easing.OutCubic } }
        Behavior on anchors.bottomMargin { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

        implicitWidth: toastLbl.implicitWidth + 32
        implicitHeight: 40
        radius: 11
        color: win.toastError ? "#3B1E2A" : "#1E3028"
        border.width: 1
        border.color: win.toastError ? win.cRed : win.cGreen

        Text {
            id: toastLbl
            anchors.centerIn: parent
            text: win.toastText
            color: win.toastError ? win.cRed : win.cGreen
            font.pixelSize: 12
            font.weight: Font.DemiBold
        }
    }
}
