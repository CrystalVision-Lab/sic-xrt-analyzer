import QtQuick

QtObject {
    objectName: "resultPresentation"
    readonly property QtObject palette: Theme {}
    // Presentation only: never assign formatted values back to research data.
    function confidence(score) {
        if (typeof score !== "number" || !isFinite(score)) return "—"
        return (Math.round(score * 1000) / 10).toFixed(1).replace(/\.0$/, "") + "%"
    }
    function count(value) { return Number(value || 0).toLocaleString(Qt.locale("en_US"), "f", 0) }
    function colorFor(kind) { return kind === "BPD" ? palette.classBpd : kind === "TED" ? palette.classTed : kind === "TSD" ? palette.classTsd : palette.classOther }
    function shapeFor(kind) { return kind === "BPD" ? "◆" : kind === "TED" ? "▲" : kind === "TSD" ? "■" : "●" }
    function raw(score) { return typeof score === "number" ? String(score) : "—" }
}
