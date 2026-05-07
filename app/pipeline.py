"""Pipeline chain definition for CV analysis."""
from celery import chain, signature

from app.celery_app import celery_app  # noqa: F401 — ensures app is loaded first


def run_analysis_pipeline(
    job_id: str,
    file_path: str,
    file_type: str,
    job_description: str | None,
) -> None:
    """Enqueue the full analysis pipeline as a Celery chain."""
    context: dict = {
        "job_id": job_id,
        "file_path": file_path,
        "file_type": file_type,
        "job_description": job_description,
        "warnings": [],
        "step_timings": {},
    }

    pipeline = chain(
        signature("app.tasks.ingest_cv.ingest_cv", args=(context,)),
        signature("app.tasks.extract_cv_structure.extract_cv_structure"),
        signature("app.tasks.compute_score.compute_score"),
        signature("app.tasks.score_ats.score_ats"),
        signature("app.tasks.estimate_salary.estimate_salary"),
        signature("app.tasks.generate_explanation.generate_explanation"),
        signature("app.tasks.analyze_cv_content.analyze_cv_content"),
        signature("app.tasks.assemble_output.assemble_output"),
    )

    pipeline.apply_async(task_id=job_id)
