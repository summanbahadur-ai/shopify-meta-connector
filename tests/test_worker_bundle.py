from pathlib import Path
import subprocess
import sys

from scripts.check_worker_bundle import check_bundle, load_config


def tree(root, names):
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")


def config(root):
    source = Path(__file__).resolve().parents[1] / "wrangler.jsonc"
    (root / "wrangler.jsonc").write_text(source.read_text(), encoding="utf-8")


def test_exclusions_keep_full_number_data_and_short_package(tmp_path, capsys):
    config(tmp_path)
    tree(tmp_path, [
        "worker.py", ".cache/worker-source/app/main.py", "python_modules/dns/resolver.py",
        "python_modules/phonenumbers/shortdata/region_US.py",
        "python_modules/phonenumbers/shortdata/__init__.py",
        "python_modules/phonenumbers/data/region_US.py",
        "python_modules/pkg/module.py", "python_modules/pkg/module.pyi",
        "python_modules/pkg/py.typed", "python_modules/pkg/__pycache__/module.pyc",
        "python_modules/pkg-1.dist-info/METADATA",
    ])
    assert check_bundle(tmp_path) == 0
    output = capsys.readouterr().out
    assert "raw=9 excluded=5 included=4" in output
    assert "estimated_parts=22" in output


def test_missing_vendor_and_conservative_guard(tmp_path, capsys):
    config(tmp_path)
    assert check_bundle(tmp_path) == 1
    assert "missing or empty" in capsys.readouterr().err
    tree(tmp_path, [f"python_modules/pkg/file{i}.py" for i in range(934)])
    (tmp_path / ".cache/worker-source/app").mkdir(parents=True)
    assert check_bundle(tmp_path) == 1
    assert "estimated_parts=950" in capsys.readouterr().out


def test_jsonc_comments_trailing_comma_and_urls(tmp_path):
    path = tmp_path / "wrangler.jsonc"
    path.write_text('{// comment\n"url":"https://example.com/*x*/",/* block */"python_modules":{"exclude":["**/*.pyc",],},}', encoding="utf-8")
    assert load_config(path)["url"] == "https://example.com/*x*/"


def test_email_and_international_phone_validation_without_excluded_modules():
    code = r'''
import importlib.abc
import sys
class ExcludedImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "dns" or fullname.startswith("dns.") or fullname.startswith("phonenumbers.shortdata.region_"):
            raise ModuleNotFoundError("Excluded deployment module: " + fullname)
sys.meta_path.insert(0, ExcludedImports())
import phonenumbers
from app.schemas.order_status import email_forms, normalize_phone
assert email_forms("Person@b\u00fccher.de") == ("person@xn--bcher-kva.de", "person@b\u00fccher.de")
assert email_forms("person+tag@example.com") == ("person+tag@example.com",)
count = 0
for region in phonenumbers.SUPPORTED_REGIONS:
    number = phonenumbers.example_number(region)
    if number is not None:
        value = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
        assert normalize_phone(value) == value, region
        count += 1
assert count >= 240, count
print(count)
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_source_staging_omits_environments_tests_and_caches(tmp_path):
    from scripts.prepare_worker_source import prepare_source_tree

    config(tmp_path)
    tree(tmp_path, ["worker.py", "app/__init__.py", "app/main.py",
        "app/__pycache__/main.pyc", ".venv/lib/unwanted.py", "tests/test_main.py", ".env"])
    staged = prepare_source_tree(tmp_path)
    files = {p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file()}
    assert files == {"app/__init__.py", "app/main.py"}
    assert (tmp_path / ".env").exists()


def test_source_staging_removes_deleted_app_modules(tmp_path):
    from scripts.prepare_worker_source import prepare_source_tree

    config(tmp_path)
    tree(tmp_path, ["worker.py", "app/main.py", "app/deleted.py"])
    staged = prepare_source_tree(tmp_path)
    (tmp_path / "app/deleted.py").unlink()
    prepare_source_tree(tmp_path)
    assert not (staged / "app/deleted.py").exists()
    assert (staged / "app/main.py").exists()


def test_source_staging_rejects_path_outside_workspace(tmp_path):
    import json
    import pytest
    from scripts.prepare_worker_source import prepare_source_tree

    tree(tmp_path, ["worker.py", "app/main.py"])
    (tmp_path / "wrangler.jsonc").write_text(json.dumps({"base_dir": "../outside", "main": "worker.py"}))
    with pytest.raises(ValueError):
        prepare_source_tree(tmp_path)


def test_preflight_rejects_project_root_as_source_scan(tmp_path, capsys):
    import json
    from scripts.check_worker_bundle import check_bundle

    tree(tmp_path, ["worker.py", "app/main.py", "python_modules/pkg/__init__.py"])
    (tmp_path / "wrangler.jsonc").write_text(json.dumps({"main": "worker.py"}))
    assert check_bundle(tmp_path) == 1
    assert "Unsafe source scan root" in capsys.readouterr().err


def test_actual_bundle_guard_rejects_virtual_environment_files(tmp_path, capsys):
    from scripts.check_worker_bundle import check_built_bundle

    tree(tmp_path, ["worker.py", "app/main.py", "python_modules/pkg/__init__.py",
                    ".venv/lib/unwanted.py"])
    assert check_built_bundle(tmp_path) == 1
    assert ".venv/lib/unwanted.py" in capsys.readouterr().err


def test_actual_bundle_guard_reports_only_deployment_files(tmp_path, capsys):
    from scripts.check_worker_bundle import check_built_bundle

    tree(tmp_path, ["worker.py", "app/main.py", "python_modules/pkg/__init__.py", "README.md"])
    assert check_built_bundle(tmp_path) == 0
    assert "files=3" in capsys.readouterr().out
