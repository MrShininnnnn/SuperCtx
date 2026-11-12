"""Released pointer compatibility and backup-independent wording.

released_shims.json was captured by running generate_shim from git archives of
v0.1.4 and v0.2.5 (not from the renderer under test), for both backup flags.
"""
import json
from pathlib import Path

import pytest
from superctx import add, core, guard, shim, sync
from test_v2_migration_safety import snapshot

RELEASED = json.loads((Path(__file__).parent / 'fixtures/released_shims.json').read_text())
PATHS = ['AGENTS.md', '.claude/CLAUDE.md']
NEUTRAL = 'Expected original backup location (if available):'


def setup(project, rel, backup=True):
    (project / 'CLAUDE.md').write_text('Shared instructions.\n')
    sync.run(project)
    if backup:
        live = project / rel
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_text('Original instructions.\n')
    add.run(project, rel, create_if_missing=not backup)


@pytest.mark.parametrize('rel', PATHS)
@pytest.mark.parametrize('backup', [True, False])
@pytest.mark.parametrize('tag', ['v0.1.4', 'v0.2.5'])
def test_released_pointer_refresh_preserves_owned_data(tmp_path, rel, backup, tag):
    setup(tmp_path, rel, backup)
    live = tmp_path / rel
    old = RELEASED[tag][f'{rel}:{backup}']
    live.write_text(old)
    assert shim.is_generated_pointer(old, rel, backup)
    code, message = guard.handle_pre_tool_use({'cwd': str(tmp_path), 'tool_input': {'file_path': str(live)}})
    assert code == 2 and '.ctx/SUPERCTX.md' in message
    owned = snapshot(tmp_path / '.ctx')
    sync.run(tmp_path)
    text = live.read_text()
    if backup:
        assert NEUTRAL in text
        assert 'backed up at' not in text
    else:
        assert 'Created by SuperCtx; no original content existed to back up.' in text
    prefix = '../' if rel.startswith('.') else ''
    assert prefix + '.ctx/SUPERCTX.md' in text
    if backup:
        assert prefix + '.ctx/sources/' + rel in text
    assert snapshot(tmp_path / '.ctx') == owned
    before = snapshot(tmp_path)
    assert sync.run(tmp_path)['mutated'] is False
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('rel', PATHS)
@pytest.mark.parametrize('tag', ['v0.1.4', 'v0.2.5'])
@pytest.mark.parametrize('missing_backup', [False, True])
def test_edited_released_pointer_is_preserved(tmp_path, rel, tag, missing_backup):
    setup(tmp_path, rel)
    if missing_backup:
        (core.sources_dir(tmp_path) / rel).unlink()
    (tmp_path / rel).write_text(RELEASED[tag][f'{rel}:True'] + 'User edit.\n')
    before = snapshot(tmp_path)
    result = sync.run(tmp_path)
    assert {'path': rel, 'reason': 'native_edited'} in result['unresolved']
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('rel', PATHS)
def test_backup_presence_does_not_change_pointer_or_hide_warning(tmp_path, rel):
    setup(tmp_path, rel)
    live = tmp_path / rel
    backup = core.sources_dir(tmp_path) / rel
    original = backup.read_bytes()
    backup.unlink()
    live.write_text(RELEASED['v0.2.5'][f'{rel}:True'])
    owned = snapshot(tmp_path / '.ctx')
    result = sync.run(tmp_path)
    assert {'path': rel, 'reason': 'missing_backup'} in result['warnings']
    assert NEUTRAL in live.read_text()
    assert snapshot(tmp_path / '.ctx') == owned
    pointer = snapshot(live)
    backup.write_bytes(original)
    assert sync.run(tmp_path)['mutated'] is False
    assert snapshot(live) == pointer
    backup.unlink()
    result = sync.run(tmp_path)
    assert result['mutated'] is False
    assert {'path': rel, 'reason': 'missing_backup'} in result['warnings']
    assert snapshot(live) == pointer and not backup.exists()
    live.unlink()
    result = sync.run(tmp_path)
    assert rel in result['repaired']
    assert NEUTRAL in live.read_text() and not backup.exists()
