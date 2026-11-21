# Capstone_Project

## EXAMFLOW: Online Exam Proctoring Result Engine
**Project:** AI-056  
**Problem Statement:** PS-072 – Online Exam Proctoring Result Engine with Negative Marking, Sectional Cut-offs and Shift Normalisation.

### Core Backend Architecture
- **Framework:** FastAPI (Python 3.11+)
- **Database:** PostgreSQL (SQLAlchemy 2.0 Async + Alembic Migrations)
- **Validation:** Pydantic v2
- **Testing:** Pytest (covering 20 mandatory boundary test cases)
- **Deployment:** Docker & Google Cloud Run ready

### Key Engines
1. **Deterministic Scoring Engine:** Rule 1 & 2 (correct, negative marks, dropped questions, multiple-correct options)
2. **Proctoring Penalty Engine:** Rule 5 (severity-based deductions and malpractice disqualifications)
3. **Shift Normalisation Engine:** Rules 6 & 7 (shift statistics, small-shift pooling, zero-denominator guard)
4. **Qualification Engine:** Rules 3, 4, 8 & 10 (sectional & overall cut-offs, category relaxation, minimum attempt validation)
5. **Merit List Engine:** Rules 9 & 10 (multi-tier deterministic tie-breaking and category allocation)
6. **Re-Evaluation Service:** Rule 11 (strict one-time re-evaluation restriction with audit trail)

### Repository Structure
```
CapStone_Project/
├── README.md
├── .gitignore
├── examflow_backend/
│   ├── app/
│   │   ├── api/v1/         # REST API endpoints & routers
│   │   ├── core/           # Security, config & database
│   │   ├── engines/        # Pure deterministic calculation engines
│   │   ├── models/         # 20 relational database entities
│   │   ├── repositories/   # Data access layer
│   │   ├── schemas/        # Pydantic input/output schemas
│   │   └── services/       # Transactional business services
│   ├── alembic/            # Schema migration versions
│   ├── scripts/            # Database seed script for runnable demo
│   ├── tests/              # 20 mandatory boundary test cases
│   ├── Dockerfile          # Multi-stage production container
│   ├── docker-compose.yml  # Local developer environment
│   └── requirements.txt
```
