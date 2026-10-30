from pathlib import Path
import re
root = Path(__file__).resolve().parents[4]
for name, version in [('tasks/047-llm-pdf-extraction-design.md', 'v1.3'), ('docs/PROJECT_STATUS.md', 'v1.115'), ('docs/design/04-04_llm_parameter_contracts.md', 'v1.2')]:
    path = root / name
    text = path.read_text()
    assert version in text[:150] and '2026-10-30' in text[:150]
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
        if '://' in target or target.startswith('#'):
            continue
        assert (path.parent / target.split('#')[0]).resolve().exists(), (name, target)
assert 'D-PDF-04' in (root / 'docs/PROJECT_STATUS.md').read_text()
assert '262144' in (root / 'docs/design/04-04_llm_parameter_contracts.md').read_text()
print('PASS: capacity documentation versions, local link targets and decision/status consistency; not runtime acceptance')
