from autogis.ai_analyzer import analyze_task
from autogis.guidance import build_guidance
from autogis.operation_catalog import build_operation_modules
from autogis.planner import plan_task


def _titles(items):
    return [item.title for item in items]


def test_vector_move_does_not_expand_to_site_selection():
    task = "将道路要素向东移动10米，检查移动后属性是否保留。"

    guidance = build_guidance(task)
    workflow = plan_task(task)
    analysis = analyze_task(task).to_dict()
    modules = build_operation_modules(task, {}, analysis=analysis)

    assert guidance.task_category == "要素编辑/几何处理"
    assert _titles(guidance.recommended_route) == ["移动/平移要素"]
    assert workflow.task_types == ["vector_edit_geometry"]
    assert _titles(workflow.steps) == ["数据检查", "移动/平移要素"]
    assert [op.name for op in analyze_task(task).operations] == ["平移几何"]
    assert "vector_overlay_area" not in [module.id for module in modules]
    assert [module.title for module in modules if module.id == "vector_edit_geometry"] == ["移动/平移要素"]


def test_road_noise_distance_still_routes_to_site_selection():
    task = "根据道路噪声影响距离筛选建设适宜区域，并通过缓冲和擦除得到候选区。"

    guidance = build_guidance(task)
    workflow = plan_task(task)
    modules = build_operation_modules(task, {}, analysis={"ok": True, "guidance": guidance.to_dict()})

    assert guidance.task_category == "选址/约束筛选"
    assert workflow.task_types == ["site_selection"]
    assert "缓冲区" in _titles(workflow.steps)
    assert "vector_overlay_area" in [module.id for module in modules]


if __name__ == "__main__":
    test_vector_move_does_not_expand_to_site_selection()
    test_road_noise_distance_still_routes_to_site_selection()
    print("routing-regression-ok")
