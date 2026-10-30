import hashlib,json,subprocess
from pathlib import Path
root=Path.cwd(); ev=Path(__file__).resolve().parent
scope=["backend/src/rpb/adapters/paper_screening.py","backend/src/rpb/adapters/runs.py","backend/src/rpb/api/runs.py","backend/src/rpb/bootstrap/business.py","backend/tests/integration/test_browser_runs.py","contracts/p0.coverage.json","contracts/p0.openapi.json","docs/PROJECT_STATUS.md","docs/design/04-01_p0_operation_contracts.md","frontend/src/ConstructionRuns.tsx","scripts/run_business_demo.py","scripts/tests/test_construction_contracts.py","backend/src/rpb/adapters/paper_analysis.py","backend/src/rpb/adapters/paper_analysis_provider.py","backend/src/rpb/adapters/paper_analysis_worker.py","backend/src/rpb/modules/construction/domain/analysis.py","backend/tests/integration/test_browser_analysis.py","backend/tests/integration/test_paper_analysis.py","backend/tests/unit/test_analysis_provider.py","backend/tests/unit/test_paper_analysis.py","frontend/src/PaperAnalysis.tsx","tasks/048-paper-analysis.md"]
manifest=json.loads((ev/"handoff-snapshot/source-manifest.json").read_text())
records={"docs/PROJECT_STATUS.md","tasks/048-paper-analysis.md"}
assert all(hashlib.sha256(Path(x).read_bytes()).hexdigest()==manifest[x] for x in scope if x not in records)
assert not subprocess.check_output(["git","diff","--cached","--name-only"])
for batch in ["final-regression","unit4","contract-tests3","contract3","static4","types4","format3","build4","final-static","final-format","closeout-check","review-storage2"]:
    assert json.loads((ev/batch/"run.json").read_text())["exit_code"]==0,batch
    scope.extend(str(x.relative_to(root)) for x in (ev/batch).iterdir() if x.is_file())
for name in ["review-s3.md","review-s6.md","reviewer-design-audit.md","final-regression-tests.xml","unit4-tests.xml","final-regression-junit-summary.json","unit4-junit-summary.json","final-tested-drift.json","final-records-diff.json","commit-acceptance-diff.json","handoff-snapshot/source-manifest.json","final-test-snapshot/source-manifest.json","commit-ledger.json","commit_prepare.py","run_check.py"]:
    scope.append(str((ev/name).relative_to(root)))
# Persist scope and protect all existing tracked and untracked files outside this evidence directory.
allpaths=subprocess.check_output(["git","ls-files","-co","--exclude-standard","-z"]).decode().split("\0")
protected={x:hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in set(allpaths) if x and Path(x).is_file() and x not in scope and not x.startswith(str(ev.relative_to(root))+"/")}
(ev/"commit-protected.json").write_text(json.dumps(protected,indent=2))
(ev/"commit-scope.json").write_text(json.dumps(sorted(scope),indent=2))
subprocess.run(["git","diff","--check","--",*scope],check=True)
subprocess.run(["python3",str(ev/"check_closeout.py")],check=True)
report={"head":subprocess.check_output(["git","rev-parse","HEAD"]).decode().strip(),"scope_files":len(scope),"accepted_business_files":len(scope[:22])-len(records),"business_hash_mismatches":[],"record_only_changes":sorted(records),"protected_files":len(protected),"business_tests_rerun":False}
(ev/"commit-preflight.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
