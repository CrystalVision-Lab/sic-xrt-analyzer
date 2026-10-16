"""Conservative Windows x64 packaging exclusions; runtime capabilities stay intact.

No Python import-based tree shaking: Fiji/JPype/QML load dependencies dynamically.
Keep Java's complete module image, javac, legal notices, all common and win64 JARs,
all image codecs and QtQuick3D/Fluent assets. Sources ship separately.
"""

import json
from pathlib import Path, PurePosixPath

FOREIGN_FIJI = {"linux64", "linux-arm64", "macos64", "macos-arm64", "macosx"}


def exclusion_reason(destination):
    parts = PurePosixPath(str(destination).replace("\\", "/").lower()).parts
    if len(parts) >= 5 and parts[:3] == ("runtimes", "fiji", "jars") and parts[3] in FOREIGN_FIJI:
        return "Fiji native library for a different OS/architecture"
    if parts[:3] == ("runtimes", "openjdk", "jmods"):
        return "Java linker input; complete runtime module image retained"
    if parts == ("runtimes", "openjdk", "lib", "src.zip"):
        return "Java source supplied in corresponding-source archive"
    if parts and parts[0] == "pyside6":
        if len(parts) >= 3 and parts[1] == "qml" and parts[2] in {"qtwebengine", "qtwebview"}:
            return "Unused embedded web browser QML plugin"
        if len(parts) >= 3 and parts[1:3] == ("plugins", "webview"):
            return "Unused embedded web browser platform plugin"
        name = parts[-1]
        if name.startswith(("qt6webengine", "qt6webview", "qtwebengineprocess", "qtwebengine_")):
            return "Unused embedded web browser runtime"
    return None


def slim_toc(entries):
    kept, removed = [], []
    for entry in entries:
        reason = exclusion_reason(entry[0])
        if reason:
            removed.append({"path": entry[0], "bytes": Path(entry[1]).stat().st_size, "reason": reason})
        else:
            kept.append(entry)
    return kept, removed


def validate_retained_imports(entries, removed):
    """Fail the build if any retained Windows binary imports a removed DLL."""
    import pefile

    removed_dlls = {PurePosixPath(r["path"].replace("\\", "/")).name.lower()
                    for r in removed if r["path"].lower().endswith(".dll")}
    for destination, source, kind in entries:
        if kind != "BINARY" or Path(source).suffix.lower() not in {".dll", ".pyd", ".exe"}:
            continue
        with pefile.PE(str(source), fast_load=True) as pe:
            pe.parse_data_directories(directories=[
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
            ])
            imports = [*getattr(pe, "DIRECTORY_ENTRY_IMPORT", []),
                       *getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", [])]
            broken = {item.dll.decode("ascii").lower() for item in imports} & removed_dlls
            if broken:
                raise RuntimeError(f"Retained binary {destination} needs excluded DLLs: {sorted(broken)}")


def write_report(path, removed):
    Path(path).write_text(json.dumps({
        "schema": "xrt_windows_bundle_selection/v1", "platform": "windows-x64",
        "excluded_bytes": sum(row["bytes"] for row in removed), "excluded": removed,
        "preserved": ["Java complete module image and compiler", "Fiji common and win64 plugins",
                      "Image codecs", "QtQuick3D", "FluentWinUI3", "licenses and corresponding source"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
