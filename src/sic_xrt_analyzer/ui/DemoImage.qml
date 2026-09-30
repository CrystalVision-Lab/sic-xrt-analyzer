import QtQuick

Item {
    id: root
    property QtObject theme

    Canvas {
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            const w = width
            const h = height
            ctx.reset()
            ctx.fillStyle = "#303a40"
            ctx.fillRect(0, 0, w, h)
            const cx = w * 0.5
            const cy = h * 0.5
            const radius = Math.min(w * 0.37, h * 0.43)
            ctx.save()
            ctx.beginPath()
            ctx.arc(cx, cy, radius, 0, Math.PI * 2)
            ctx.clip()
            ctx.fillStyle = "#899398"
            ctx.fillRect(cx - radius, cy - radius, radius * 2, radius * 2)
            for (let i = 0; i < 70; i++) {
                const y = cy - radius + i * radius * 2 / 70
                ctx.fillStyle = i % 4 === 0 ? "rgba(30,44,50,0.18)" : "rgba(235,244,245,0.06)"
                ctx.fillRect(cx - radius, y, radius * 2, Math.max(1, h / 500))
            }
            for (let i = 0; i < 85; i++) {
                const angle = i * 2.39996
                const radial = Math.sqrt((i + 0.5) / 85) * radius * 0.93
                const x = cx + Math.cos(angle) * radial
                const y = cy + Math.sin(angle) * radial
                ctx.beginPath()
                ctx.arc(x, y, Math.max(1.2, radius * (i % 8 + 2) / 390), 0, Math.PI * 2)
                ctx.fillStyle = i % 3 === 0 ? "rgba(35,49,54,0.30)" : "rgba(228,238,240,0.15)"
                ctx.fill()
            }
            ctx.restore()
            ctx.strokeStyle = "#b8c6c9"
            ctx.lineWidth = Math.max(1, w / 600)
            ctx.beginPath()
            ctx.arc(cx, cy, radius, 0, Math.PI * 2)
            ctx.stroke()
            ctx.fillStyle = "#303a40"
            ctx.fillRect(cx - radius * 0.13, cy - radius - 2, radius * 0.26, radius * 0.10)
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 14
        width: watermark.implicitWidth + 20
        height: 28
        radius: 3
        color: "#cf243039"
        Text {
            id: watermark
            anchors.centerIn: parent
            text: "데모 이미지 · 합성 샘플"
            color: "#ffffff"
            font.family: theme.fontFamily
            font.pixelSize: theme.smallSize
            font.weight: Font.DemiBold
        }
    }
}
