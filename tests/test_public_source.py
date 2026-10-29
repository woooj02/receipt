"""Prevent publishing local-only files again; cached GitHub objects need Support."""
from pathlib import Path
import subprocess
import pytest


def test_current_index_and_all_local_reachable_refs_exclude_private_content():
    root = Path(__file__).resolve().parents[1]
    probe = subprocess.run(['git','rev-parse','--show-toplevel'],cwd=root,capture_output=True,text=True)
    if probe.returncode or Path(probe.stdout.strip()).resolve() != root:
        pytest.skip('Source archives have no repository metadata; check the actual Git checkout before publication.')
    private = {'project.md','PREKEY_HANDOFF.md','PROJECT_AUDIT.md','REVIEW_FIXES.md',
               'prd.md','spec.md','scope.md','event-brief.md','submission/release-plan.md','submission/VOICEOVER.md'}
    index = subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines()
    history = subprocess.check_output(['git','rev-list','--objects','--all'],cwd=root,text=True).splitlines()
    paths = set(index) | {line.split(' ',1)[1] for line in history if ' ' in line}
    exposed = {path for path in paths if path in private or path.startswith(('data/','submission/video/'))
               or (path.startswith('.env') and path != '.env.example')}
    assert not exposed, 'Private paths in publishable Git content: ' + ', '.join(sorted(exposed))
