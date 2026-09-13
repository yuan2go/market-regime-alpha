"""Git/wheel source identity is checked before Artifact publication."""

from pathlib import Path
import subprocess

import pytest

from market_regime_alpha.interfaces.historical_study_build import verify_historical_build


@pytest.mark.parametrize("ignored", (False, True))
def test_untracked_source_cannot_be_attested_as_the_committed_implementation(tmp_path, ignored):
    def git(*args):
        return subprocess.check_output(["git","-C",str(tmp_path),*args],text=True,stderr=subprocess.PIPE).strip()
    git("init","--initial-branch=fixture")
    (tmp_path/"src/market_regime_alpha").mkdir(parents=True)
    (tmp_path/"src/market_regime_alpha/__init__.py").write_text("")
    (tmp_path/"uv.lock").write_text("fixture locked identity\n")
    (tmp_path/".gitignore").write_text("untracked.py\n" if ignored else "")
    git("add","src","uv.lock",".gitignore")
    git("-c","user.email=fixture@example.invalid","-c","user.name=Fixture","commit","-m","isolated source fixture")
    (tmp_path/"src/market_regime_alpha/untracked.py").write_text("unrecorded = True\n")
    with pytest.raises(ValueError,match="committed implementation"):
        verify_historical_build(wheel=Path("absent-wheel-must-not-be-read"),lockfile=tmp_path/"uv.lock",
            source_checkout=tmp_path,code_sha=git("rev-parse","HEAD"))
