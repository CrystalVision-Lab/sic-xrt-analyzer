import QtQuick

QtObject {
    objectName: "resultPresentation"
    // Presentation only: never assign formatted values back to research data.
    function confidence(score) {
        if (typeof score !== "number" || !isFinite(score)) return "—"
        return (Math.round(score * 1000) / 10).toFixed(1).replace(/\.0$/, "") + "%"
    }
    function count(value) { return Number(value || 0).toLocaleString(Qt.locale("en_US"), "f", 0) }
    function colorFor(kind) { return kind === "BPD" ? "#efbc70" : kind === "TED" ? "#85c9ed" : "#e7a2c7" }
    function raw(score) { return typeof score === "number" ? String(score) : "—" }
}
