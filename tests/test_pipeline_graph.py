from app.pipeline_graph import gate_loopback_target, rerun_order, stage_prev
from app.stages import Stage, create_stages


def test_rerun_order_is_names_in_order():
    stages = create_stages()
    assert rerun_order(stages) == [s.name for s in stages]
    assert rerun_order(stages)[0] == "Planning"


def test_stage_prev_maps_first_to_none_and_others_to_predecessor():
    prev = stage_prev(create_stages())
    assert prev["Planning"] is None
    assert prev["Decomposition"] == "Planning"
    assert prev["Implementation"] == "Decomposition"


def test_gate_loopback_target_finds_nearest_preceding_decompose():
    stages = create_stages()
    names = [s.name for s in stages]
    target = gate_loopback_target(stages, names.index("Code Quality"))
    assert names[target] == "Decomposition"


def test_gate_loopback_target_none_when_no_decompose_precedes():
    stages = [
        Stage(name="Planning", prompt_template="", kind="simple"),
        Stage(name="Code Quality", prompt_template="", kind="gate"),
    ]
    assert gate_loopback_target(stages, 1) is None
