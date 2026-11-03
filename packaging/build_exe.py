"""Automated build script for packaging NovaBank into a standalone Windows binary."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SPEC_FILE = PROJECT_ROOT / "packaging" / "novabank.spec"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
EXE_PATH = DIST_DIR / "NovaBank" / "NovaBank.exe"


def clean_previous_builds() -> None:
    """Clean dist/ and build/ folders before packaging."""
    import shutil

    print("[*] Cleaning build artifacts...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
    if (DIST_DIR / "NovaBank").exists():
        shutil.rmtree(DIST_DIR / "NovaBank", ignore_errors=True)


def build_binary(clean: bool = True) -> int:
    """Invoke PyInstaller to compile standalone Windows executable."""
    if clean:
        clean_previous_builds()

    pyinstaller_bin = Path(sys.executable).parent / "pyinstaller.exe"
    if not pyinstaller_bin.exists():
        pyinstaller_bin = Path(sys.executable).parent / "pyinstaller"

    if not pyinstaller_bin.exists():
        print(f"[-] PyInstaller binary not found at {pyinstaller_bin}", file=sys.stderr)
        return 1

    cmd = [
        str(pyinstaller_bin),
        str(SPEC_FILE),
        "--clean",
        "--noconfirm",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
    ]

    print(f"[*] Executing PyInstaller: {' '.join(cmd)}")
    start_time = time.time()
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=False)
    duration = time.time() - start_time

    if result.returncode != 0:
        print(f"[-] Build failed with exit code {result.returncode}", file=sys.stderr)
        return result.returncode

    if not EXE_PATH.exists():
        print(f"[-] Build finished but executable not found at {EXE_PATH}", file=sys.stderr)
        return 1

    # Measure output directory size
    total_size = sum(f.stat().st_size for f in (DIST_DIR / "NovaBank").rglob("*") if f.is_file())
    size_mb = total_size / (1024 * 1024)

    print("\n" + "=" * 60)
    print(" [OK] Build Successful!")
    print(f" Binary: {EXE_PATH}")
    print(f" Bundle Size: {size_mb:.2f} MB")
    print(f" Build Time: {duration:.2f} seconds")
    print("=" * 60)

    return 0


def verify_binary_smoke() -> bool:
    """Verify built binary executes and responds to version flag."""
    if not EXE_PATH.exists():
        print(f"[-] Executable does not exist: {EXE_PATH}", file=sys.stderr)
        return False

    print("[*] Running executable smoke test: NovaBank.exe --version ...")
    try:
        res = subprocess.run(
            [str(EXE_PATH), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        print(f"[*] Output: {res.stdout.strip()}")
        return res.returncode == 0 and "NovaBank v1.0.0" in res.stdout
    except Exception as exc:
        print(f"[-] Smoke test failed: {exc}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Build NovaBank Windows Executable")
    parser.add_argument("--no-clean", action="store_true", help="Skip cleaning previous builds")
    parser.add_argument("--smoke-only", action="store_true", help="Only run smoke test on existing binary")
    args = parser.parse_args()

    if args.smoke_only:
        return 0 if verify_binary_smoke() else 1

    code = build_binary(clean=not args.no_clean)
    if code == 0:
        if verify_binary_smoke():
            print("[OK] Smoke verification passed!")
            return 0
        else:
            print("[-] Smoke verification failed!", file=sys.stderr)
            return 1
    return code


if __name__ == "__main__":
    sys.exit(main())

