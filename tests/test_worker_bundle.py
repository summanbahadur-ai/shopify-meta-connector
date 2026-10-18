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
        "worker.py", "app/main.py", "python_modules/dns/resolver.py",
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
