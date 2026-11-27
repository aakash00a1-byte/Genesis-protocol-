"""The roadmap may not invent progress, and the system may not claim awareness.

The live Space once reported an 87.7% "average progress" on a roadmap with zero
completed milestones and zero interactions, because the auto-updater computed
"progress" from elapsed calendar time. These tests make that impossible to
reintroduce quietly.
"""

import json
from pathlib import Path

from genesis_protocol.gluten.identity import EVOLUTION_CHAIN, NAME
from genesis_protocol.infinity.future_roadmap import NON_CLAIMS, FutureRoadmap


def test_a_fresh_roadmap_claims_nothing(tmp_path):
    status = FutureRoadmap(str(tmp_path)).get_status()
    assert status["average_progress"] == 0.0
    assert status["completed_milestones"] == 0
    assert status["evidence_backed_milestones"] == 0
    assert status["progress_basis"] == "evidence"
    assert status["current_stage"] == NAME


def test_self_awareness_is_not_a_milestone_anywhere(tmp_path):
    roadmap = FutureRoadmap(str(tmp_path))
    blob = json.dumps([m.to_dict() for m in roadmap.get_milestones()]).lower()
    assert "consciousness" not in blob
    assert "self-aware" not in blob
    assert any("self-awareness" in claim.lower() for claim in NON_CLAIMS)


def test_progress_cannot_be_set_by_a_caller(tmp_path):
    roadmap = FutureRoadmap(str(tmp_path))
    assert roadmap.update_milestone_progress("research_cycle", 100) is False
    assert roadmap.get_status()["average_progress"] == 0.0


def test_evidence_moves_progress_and_verification_completes_it(tmp_path):
    roadmap = FutureRoadmap(str(tmp_path))
    roadmap.record_evidence("research_cycle", "draft: reports/cycle.md", verified=False)
    assert roadmap.get_status()["average_progress"] == 12.5      # 50 / 4 objectives
    roadmap.record_evidence("research_cycle", "tests/test_research_cycle.py", verified=True)
    status = roadmap.get_status()
    assert status["completed_milestones"] == 1
    assert roadmap.get_milestones("completed")[0].id == "research_cycle"


def test_a_stale_progress_number_on_disk_is_ignored(tmp_path):
    path = Path(tmp_path) / "roadmap.json"
    path.write_text(json.dumps({
        "goals": [],
        "milestones": {"research_cycle": {"progress": 100, "status": "completed",
                                          "evidence": []}},
    }))
    roadmap = FutureRoadmap(str(tmp_path))
    milestone = roadmap.milestones["research_cycle"]
    assert milestone.progress == 0
    assert milestone.status == "planned"
    assert roadmap.get_status()["average_progress"] == 0.0


def test_evidence_survives_a_reload_but_progress_is_recomputed(tmp_path):
    roadmap = FutureRoadmap(str(tmp_path))
    roadmap.record_evidence("benchmark_verified", "13/13 with controls", verified=True)
    reloaded = FutureRoadmap(str(tmp_path))
    assert reloaded.milestones["benchmark_verified"].progress == 100
    assert reloaded.milestones["benchmark_verified"].verified_evidence[0]["reference"] == \
        "13/13 with controls"


def test_no_milestone_carries_a_target_date(tmp_path):
    for milestone in FutureRoadmap(str(tmp_path)).get_milestones():
        assert milestone.target_date is None
        assert milestone.to_dict()["target_date"] is None


def test_the_evolution_path_is_the_real_lineage(tmp_path):
    stages = FutureRoadmap(str(tmp_path)).get_evolution_path()
    assert [s["stage"] for s in stages] == list(EVOLUTION_CHAIN)
    assert [s["stage"] for s in stages if s["current"]] == [NAME]


def test_the_auto_updater_no_longer_derives_progress_from_the_clock():
    source = Path(__file__).parent.parent / "genesis_protocol" / "infinity" / "auto_updater.py"
    text = source.read_text()
    assert "_update_roadmap_progress" not in text
    assert "time_progress" not in text


def test_the_live_status_route_reports_an_evidence_basis():
    from web.app import app

    client = app.test_client()
    response = client.get("/api/infinity/status")
    assert response.status_code == 200
    roadmap = response.get_json()["components"]["future_roadmap"]
    assert roadmap["progress_basis"] == "evidence"
    assert roadmap["non_claims"]


def test_constitution_and_research_routes_answer():
    from web.app import app

    client = app.test_client()
    constitution = client.get("/api/constitution")
    assert constitution.status_code == 200
    assert len(constitution.get_json()["principles"]) == 12

    research = client.get("/api/research/status")
    assert research.status_code == 200
    body = research.get_json()
    assert body["capabilities"]["generates_hypotheses"] is False
    assert isinstance(body["lean_available"], bool)


def test_the_benchmark_route_is_owner_only():
    from web.app import app

    response = app.test_client().get("/api/research/benchmark")
    assert response.status_code in {401, 403}
