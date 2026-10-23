import importlib.util
from pathlib import Path
import pytest

MODULE = Path(__file__).resolve().parents[2] / "scripts" / "import_archives_supabase.py"
spec = importlib.util.spec_from_file_location("archive_import", MODULE)
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)

@pytest.mark.parametrize("name", ["../secret", "/absolute/path", "C:/Windows/file", "nested/../../bad"])
def test_rejects_path_traversal(name):
    with pytest.raises(ValueError):
        loader.safe_path(name)

def test_content_addressed_hash(tmp_path):
    left = tmp_path / "a.xml"
    right = tmp_path / "b.xml"
    left.write_text("<invoice>123</invoice>")
    right.write_text("<invoice>123</invoice>")
    assert loader.sha256(left) == loader.sha256(right)

def test_safe_relative_member():
    assert str(loader.safe_path("folder/invoice.xml")) == "folder/invoice.xml"
