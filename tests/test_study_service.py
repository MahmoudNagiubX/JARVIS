from __future__ import annotations

from pathlib import Path

from jarvis.computer.file_access import FileAccessPolicy
from jarvis.contracts import StudyResolutionStatus
from jarvis.study.service import StudyService


def test_study_resolves_one_approved_lecture_to_an_opaque_reference(tmp_path: Path) -> None:
    lecture = tmp_path / "Computer Vision Lecture 4.pdf"
    lecture.write_bytes(b"fixture")
    service = StudyService(FileAccessPolicy((tmp_path.resolve(),)))

    result = service.resolve("owner-1", "Computer Vision lecture 4")

    assert result.status is StudyResolutionStatus.RESOLVED
    assert result.selected_ref == result.candidates[0].candidate_ref
    assert str(lecture) not in str(result)
    assert service.path_for_open("owner-1", result.resolution_id, result.selected_ref) == lecture.resolve()


def test_study_fails_closed_on_ambiguity_and_owner_mismatch(tmp_path: Path) -> None:
    first = tmp_path / "a" / "Computer Vision Lecture 4.pdf"
    second = tmp_path / "b" / "Computer Vision Lecture 4.pdf"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    service = StudyService(FileAccessPolicy((tmp_path.resolve(),)))

    result = service.resolve("owner-1", "Computer Vision lecture 4")

    assert result.status is StudyResolutionStatus.AMBIGUOUS
    assert len(result.candidates) == 2
    assert service.path_for_open("owner-2", result.resolution_id, result.candidates[0].candidate_ref) is None
    assert service.path_for_open("owner-1", result.resolution_id) is None
    assert service.path_for_open("owner-1", result.resolution_id, result.candidates[0].candidate_ref) in {first.resolve(), second.resolve()}


def test_study_uses_only_configured_roots_and_marks_optional_steps_truthfully(tmp_path: Path) -> None:
    lecture = tmp_path / "Lecture 4.md"
    lecture.write_text("fixture", encoding="utf-8")
    service = StudyService(FileAccessPolicy((tmp_path.resolve(),)))

    plan = service.prepare(
        "owner-1",
        "Lecture 4",
        notes_target="OneNote:JARVIS Study:Computer Vision",
        research_query="bounded robotics resources",
    )
    missing = StudyService(FileAccessPolicy()).prepare("owner-1", "Lecture 4")

    assert plan.status == "ready"
    assert [step.kind for step in plan.steps[:5]] == ["lecture", "notes", "research", "video", "music"]
    assert plan.steps[1].status == "configured"
    assert plan.steps[3].status == "not_configured"
    assert len(plan.steps) == 8
    assert missing.status == "blocked"
    assert missing.resolution.status is StudyResolutionStatus.NOT_CONFIGURED
