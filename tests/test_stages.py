from app.stages import STAGES, VALID_KINDS, create_stages

EXPECTED_KINDS = {
    "Planning": "simple",
    "Decomposition": "decompose",
    "Implementation": "parallel",
    "Tests & Validation": "parallel",
    "Code Quality": "gate",
    "Documentation": "simple",
    "Commit & PR": "commit_pr",
}


def test_each_builtin_has_expected_kind():
    by_name = {s.name: s for s in STAGES}
    assert set(by_name) == set(EXPECTED_KINDS)
    for name, kind in EXPECTED_KINDS.items():
        assert by_name[name].kind == kind
        assert by_name[name].kind in VALID_KINDS


def test_parallel_phases_have_parallel_flag_and_kind():
    by_name = {s.name: s for s in STAGES}
    for name in ("Implementation", "Tests & Validation"):
        assert by_name[name].kind == "parallel"
        assert by_name[name].parallel is True


def test_create_stages_preserves_kind_and_max_iterations():
    stages = {s.name: s for s in create_stages()}
    for name, kind in EXPECTED_KINDS.items():
        assert stages[name].kind == kind
    assert stages["Code Quality"].max_iterations == 3
