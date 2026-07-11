import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ldplayer_restore import resolve_backup_for_instance


def test_backup_resolves_alt_profile_name_when_ld_hint_differs():
    backup_files = {
        "Earl Grey": Path("Earl Grey.ldbk"),
        "earlgrey": Path("Earl Grey.ldbk"),
    }
    path = resolve_backup_for_instance(
        {"index": 18, "name": "Mike"},
        backup_files,
        {},
        {18: "Mike"},
        extra_names=["Earl Grey", "Lil Mike"],
    )
    assert path == Path("Earl Grey.ldbk")


def test_backup_resolves_archer_file_for_rick_slot():
    backup_files = {"Archer": Path("Archer.ldbk"), "archer": Path("Archer.ldbk")}
    path = resolve_backup_for_instance(
        {"index": 0, "name": "Rick"},
        backup_files,
        {},
        {0: "Rick"},
        extra_names=["Rick", "Archer"],
    )
    assert path == Path("Archer.ldbk")


if __name__ == "__main__":
    test_backup_resolves_alt_profile_name_when_ld_hint_differs()
    test_backup_resolves_archer_file_for_rick_slot()
    print("ok")
