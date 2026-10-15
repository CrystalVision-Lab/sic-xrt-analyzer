# Corresponding Source — GPLv3

SiC XRT Analyzer application code is GPL-3.0-only. Use, study, modify and redistribute it under LICENSE; there is no extra restriction on execution. No warranty is provided under the license.

The download website offers the installer and **matching source archive** together. The source archive records the same full source_revision and SHA-256 as the release manifest, and includes application Python/QML, installer/build scripts, tests, server/portal/web source and build documentation. Original research images, model weights and credentials are excluded.

The archive also contains verified exact Qt6.11.2 and PySide6/shiboken6.11.2 complete source archives, Temurin21.0.12.1+1 complete JDK sources, Maven source mirrors and the binary/source inventory for the unmodified portable Fiji dependencies. Each source file has provenance, version and SHA in the included inventory. The public upstream source locators remain available for additional aggregate components under their separate licenses. Third-party licenses embedded in DLL metadata/JARs/OpenJDK legal/ are retained; application GPL does not replace them.

Build application: extract application/, follow installer/README.md, install locked Python dependencies, configure the public Fiji/ImageJ runtime and Temurin JDK, then use tools/build_windows_installer.py. Rebuilding may use a newer source_revision; no byte-identical executable claim is made. Building Qt or PySide from their included sources uses the upstream configure/CMake instructions in those archives. Java libraries use their source JAR/Maven POM metadata. Source delivery is free of charge through the same release page.

Source URL is generated from the posted release ID: /portal-api/releases/<release-id>/source. An upstream temporary hostname change does not change this path. Public repository: https://github.com/CrystalVision-Lab/sic-xrt-analyzer. Preserve LICENSE, NOTICE and third-party attribution when redistributing.
