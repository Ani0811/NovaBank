"""Inno Setup installer build runner and validator for NovaBank."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
ISS_FILE = PROJECT_ROOT / "packaging" / "installer.iss"
SOURCE_PAYLOAD_DIR = PROJECT_ROOT / "dist" / "NovaBank"
EXE_FILE = SOURCE_PAYLOAD_DIR / "NovaBank.exe"
OUTPUT_INSTALLER_DIR = PROJECT_ROOT / "dist" / "installer"

POSSIBLE_ISCC_PATHS = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
]


def find_iscc() -> Path | None:
    """Locate Inno Setup command-line compiler ISCC.exe."""
    which_iscc = shutil.which("ISCC.exe") or shutil.which("ISCC")
    if which_iscc:
        return Path(which_iscc)

    for p in POSSIBLE_ISCC_PATHS:
        if p.exists():
            return p

    return None


def validate_installer_prerequisites() -> bool:
    """Verify installer specification and binary payload are ready for compilation."""
    if not ISS_FILE.exists():
        print(f"[-] Inno Setup script missing: {ISS_FILE}", file=sys.stderr)
        return False

    if not EXE_FILE.exists():
        print(f"[-] Binary payload missing: {EXE_FILE}. Run packaging/build_exe.py first.", file=sys.stderr)
        return False

    # Check ISS contents
    content = ISS_FILE.read_text(encoding="utf-8")
    required_sections = ["[Setup]", "[Files]", "[Icons]", "[Run]"]
    for sec in required_sections:
        if sec not in content:
            print(f"[-] Invalid ISS script: missing section {sec}", file=sys.stderr)
            return False

    print(f"[OK] Inno Setup script validated: {ISS_FILE.name}")
    print(f"[OK] Binary payload verified: {EXE_FILE} ({EXE_FILE.stat().st_size / (1024*1024):.2f} MB)")
    return True


def compile_installer() -> int:
    """Compile Inno Setup installer script into self-extracting setup wizard."""
    if not validate_installer_prerequisites():
        return 1

    iscc_path = find_iscc()
    if not iscc_path:
        print("\n[!] Inno Setup compiler (ISCC.exe) is not installed on this system.")
        print("[*] To compile the installer:")
        print("    1. Download and install Inno Setup 6 from: https://jrsoftware.org/isdl.php")
        print(f"    2. Run: ISCC.exe {ISS_FILE.resolve()}")
        print("[*] The installer specification and standalone binary payload are 100% prepared.")
        return 0

    OUTPUT_INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [str(iscc_path), str(ISS_FILE)]

    print(f"[*] Compiling installer via {iscc_path} ...")
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=False)
    if res.returncode == 0:
        print("\n" + "=" * 60)
        print(" [OK] Inno Setup Installer Built Successfully!")
        print(f" Output Folder: {OUTPUT_INSTALLER_DIR}")
        print("=" * 60)
        return 0
    else:
        print(f"[-] ISCC compilation failed with code {res.returncode}", file=sys.stderr)
        return res.returncode


if __name__ == "__main__":
    sys.exit(compile_installer())

