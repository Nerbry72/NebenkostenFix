"""Release-Workflow stoesst den Deploy der Website an.

Befund: Die Website zeigte eine neue Version erst nach ihrem taeglichen Lauf,
im unguenstigsten Fall rund 24 Stunden nach dem Release. Geprueft wird, dass
release.yml nach dem Release den Deploy im Website-Repo startet und dass ein
fehlendes oder abgelaufenes Token den Release nicht rot macht.
"""
from __future__ import annotations

from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
WORKFLOW = WURZEL / '.github' / 'workflows' / 'release.yml'


def _job_website() -> str:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    start = workflow.index('\n  website:\n')
    ende = workflow.index('\n  store:\n')
    assert start < ende, 'website muss vor store stehen'
    return workflow[start:ende]


def test_die_website_wird_nach_dem_release_angestossen():
    job = _job_website()
    assert 'needs: release' in job
    assert ('gh api -X POST repos/Nerbry72/NebenkostenFix-Website/actions/workflows/'
            'deploy.yml/dispatches -f ref=main') in job
    # gh workflow run fragt per GraphQL den Default-Branch ab; das scheiterte
    # beim Release 0.17.0 am Fine-grained Token ohne Contents-Recht.
    assert 'gh workflow run' not in job
    assert 'GH_TOKEN: ${{ secrets.WEBSITE_TOKEN }}' in job
    assert 'permissions: {}' in job


def test_ohne_token_bleibt_der_release_gruen():
    job = _job_website()
    assert 'if [ -z "$GH_TOKEN" ]; then' in job
    assert 'exit 0' in job
    # Der Aufruf steht in einem if, ein Fehlschlag beendet den Schritt nicht.
    assert 'if gh api -X POST' in job
    assert 'exit 1' not in job
