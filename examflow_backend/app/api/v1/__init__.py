"""
EXAMFLOW – API v1 Router aggregator
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    candidates,
    examinations,
    answer_keys,
    challenges,
    evaluation,
    normalisation,
    qualification,
    merit_list,
    proctoring,
    re_evaluation,
    reports,
    users,
)

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
router.include_router(users.router, prefix="/users", tags=["Users"])
router.include_router(examinations.router, prefix="/examinations", tags=["Examinations"])
router.include_router(candidates.router, prefix="/candidates", tags=["Candidates"])
router.include_router(answer_keys.router, prefix="/answer-keys", tags=["Answer Keys"])
router.include_router(challenges.router, prefix="/challenges", tags=["Challenges"])
router.include_router(proctoring.router, prefix="/proctoring", tags=["Proctoring"])
router.include_router(evaluation.router, prefix="/evaluation", tags=["Evaluation"])
router.include_router(normalisation.router, prefix="/normalisation", tags=["Normalisation"])
router.include_router(qualification.router, prefix="/qualification", tags=["Qualification"])
router.include_router(merit_list.router, prefix="/merit-lists", tags=["Merit Lists"])
router.include_router(re_evaluation.router, prefix="/re-evaluation", tags=["Re-Evaluation"])
router.include_router(reports.router, prefix="/reports", tags=["Reports"])
