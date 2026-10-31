"""Keep local planning, credentials and recording sources out of published Git content."""
from pathlib import Path
import subprocess
import pytest


def test_current_index_and_all_local_reachable_refs_exclude_private_content():
    root = Path(__file__).resolve().parents[1]
    probe = subprocess.run(['git','rev-parse','--show-toplevel'],cwd=root,capture_output=True,text=True)
    if probe.returncode or Path(probe.stdout.strip()).resolve() != root:
        pytest.skip('Source archives have no repository metadata; check the actual Git checkout before publication.')
    private = {'project.md','projec.md','prekey_handoff.md','project_audit.md','review_fixes.md',
               'prd.md','spec.md','scope.md','event-brief.md','release-plan.md','notes.md','agents.md','claude.md'}
    index = subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines()
    history = subprocess.check_output(['git','rev-list','--objects','--all'],cwd=root,text=True).splitlines()
    paths = set(index) | {line.split(' ',1)[1] for line in history if ' ' in line}
    exposed = set()
    for path in paths:
        name = Path(path).name.casefold()
        if (name in private or path.startswith(('data/','submission/video/'))
            or any(part in {'.claude','.codex','.agents'} for part in Path(path).parts)
            or (name.endswith('.md') and ('dialog' in name or 'voiceover' in name))
            or (name.startswith('.env') and name != '.env.example')):
            exposed.add(path)
    assert not exposed, 'Private paths in publishable Git content: ' + ', '.join(sorted(exposed))
