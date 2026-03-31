from pathlib import Path

import pytest

TESTDATA_DIR = Path(__file__).parent.parent / "testdata"


@pytest.fixture
def testdata_dir() -> Path:
    return TESTDATA_DIR


@pytest.fixture
def simple_changelog(testdata_dir: Path) -> Path:
    return testdata_dir / "changelog_simple.md"


@pytest.fixture
def multi_version_changelog(testdata_dir: Path) -> Path:
    return testdata_dir / "changelog_multi_version.md"


@pytest.fixture
def cymongoose_changelog(testdata_dir: Path) -> Path:
    return testdata_dir / "changelog_cymongoose.md"
