"""
EXAMFLOW – Initial Database Migration
Creates all 20 entities from the PS-072 specification.

Revision ID: 0001
Revises: None
Create Date: 2026-11-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ENUMs first
    op.execute("""
        CREATE TYPE role_name_enum AS ENUM (
            'SUPER_ADMIN','EXAM_ADMIN','EVALUATOR','PROCTOR','CANDIDATE','AUDITOR'
        );
        CREATE TYPE candidate_category_enum AS ENUM ('GEN','OBC','SC','ST','EWS');
        CREATE TYPE response_status_enum AS ENUM ('OPTION_SELECTED','NOT_ATTEMPTED','MARKED_FOR_REVIEW');
        CREATE TYPE question_type_enum AS ENUM ('SINGLE_CORRECT','MULTIPLE_CORRECT');
        CREATE TYPE challenge_decision_enum AS ENUM ('PENDING','ACCEPTED','REJECTED');
        CREATE TYPE evaluation_status_enum AS ENUM ('PENDING','IN_PROGRESS','COMPLETED','FAILED');
        CREATE TYPE qualification_status_enum AS ENUM ('QUALIFIED','NOT_QUALIFIED','DISQUALIFIED');
        CREATE TYPE merit_list_status_enum AS ENUM ('DRAFT','PUBLISHED','ARCHIVED');
        CREATE TYPE re_evaluation_status_enum AS ENUM ('REQUESTED','IN_PROGRESS','COMPLETED','REJECTED');
        CREATE TYPE audit_action_enum AS ENUM (
            'CREATE','UPDATE','DELETE','EVALUATE','RE_EVALUATE','LOGIN','LOGOUT','EXPORT'
        );
    """)

    # roles
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", postgresql.ENUM(name="role_name_enum", create_type=False), unique=True, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(150), unique=True, nullable=False),
        sa.Column("email", sa.String(254), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(300), nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])

    # examinations
    op.create_table(
        "examinations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("exam_code", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("evaluation_locked", sa.Boolean, default=False, nullable=False),
        sa.Column("normalisation_enabled", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("duration_minutes > 0", name="ck_exam_duration_positive"),
    )
    op.create_index("ix_examinations_exam_code", "examinations", ["exam_code"])

    # examination_sections
    op.create_table(
        "examination_sections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("examination_id", sa.Integer, sa.ForeignKey("examinations.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("section_code", sa.String(50), nullable=False),
        sa.Column("section_order", sa.Integer, nullable=False),
        sa.Column("total_questions", sa.Integer, nullable=False),
        sa.Column("max_marks", sa.Numeric(10, 2), nullable=False),
        sa.Column("marks_per_correct", sa.Numeric(10, 2), nullable=False),
        sa.Column("negative_marks_per_wrong", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("cutoff_gen", sa.Numeric(10, 5)),
        sa.Column("cutoff_obc", sa.Numeric(10, 5)),
        sa.Column("cutoff_sc", sa.Numeric(10, 5)),
        sa.Column("cutoff_st", sa.Numeric(10, 5)),
        sa.Column("cutoff_ews", sa.Numeric(10, 5)),
        sa.Column("is_mandatory", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("examination_id", "section_code", name="uq_exam_section_code"),
        sa.CheckConstraint("total_questions > 0", name="ck_section_questions_positive"),
        sa.CheckConstraint("max_marks > 0", name="ck_section_max_marks_positive"),
        sa.CheckConstraint("marks_per_correct > 0", name="ck_section_correct_marks_positive"),
        sa.CheckConstraint("negative_marks_per_wrong >= 0", name="ck_section_neg_marks_non_negative"),
    )
    op.create_index("ix_exam_section_exam_id", "examination_sections", ["examination_id"])

    # shifts
    op.create_table(
        "shifts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("examination_id", sa.Integer, sa.ForeignKey("examinations.id"), nullable=False),
        sa.Column("shift_code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("shift_date", sa.Date, nullable=False),
        sa.Column("shift_start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shift_end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answer_key_version", sa.String(50), nullable=False, server_default="v1"),
        sa.Column("is_pooled", sa.Boolean, default=False, nullable=False),
        sa.Column("pool_shift_ids", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("examination_id", "shift_code", name="uq_shift_code_per_exam"),
        sa.CheckConstraint("shift_end_time > shift_start_time", name="ck_shift_end_after_start"),
    )

    # candidates
    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("roll_number", sa.String(50), nullable=False),
        sa.Column("full_name", sa.String(300), nullable=False),
        sa.Column("date_of_birth", sa.Date, nullable=False),
        sa.Column("category", postgresql.ENUM(name="candidate_category_enum", create_type=False), nullable=False),
        sa.Column("is_pwd", sa.Boolean, default=False, nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("phone", sa.String(20)),
        sa.Column("examination_id", sa.Integer, sa.ForeignKey("examinations.id"), nullable=False),
        sa.Column("shift_id", sa.Integer, sa.ForeignKey("shifts.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("roll_number", "examination_id", name="uq_roll_exam"),
    )
    op.create_index("ix_candidates_roll_number", "candidates", ["roll_number"])

    # answer_key_versions
    op.create_table(
        "answer_key_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("examination_id", sa.Integer, sa.ForeignKey("examinations.id"), nullable=False),
        sa.Column("version_tag", sa.String(50), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("is_official", sa.Boolean, default=False, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("examination_id", "version_tag", name="uq_answer_key_version_tag"),
    )

    # answer_keys
    op.create_table(
        "answer_keys",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("section_id", sa.Integer, sa.ForeignKey("examination_sections.id"), nullable=False),
        sa.Column("version_id", sa.Integer, sa.ForeignKey("answer_key_versions.id"), nullable=False),
        sa.Column("question_number", sa.Integer, nullable=False),
        sa.Column("question_type", postgresql.ENUM(name="question_type_enum", create_type=False), nullable=False),
        sa.Column("correct_options", sa.String(500), nullable=False),
        sa.Column("is_dropped", sa.Boolean, default=False, nullable=False),
        sa.Column("dropped_marks_rule", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("section_id", "question_number", "version_id", name="uq_answer_key_question_version"),
    )
    op.create_index("ix_answer_key_section_version", "answer_keys", ["section_id", "version_id"])

    # candidate_responses
    op.create_table(
        "candidate_responses",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("section_id", sa.Integer, sa.ForeignKey("examination_sections.id"), nullable=False),
        sa.Column("question_number", sa.Integer, nullable=False),
        sa.Column("selected_option", sa.String(500)),
        sa.Column("status", postgresql.ENUM(name="response_status_enum", create_type=False), nullable=False),
        sa.Column("effective_status", postgresql.ENUM(name="response_status_enum", create_type=False), nullable=False),
        sa.Column("response_timestamp", sa.DateTime(timezone=True)),
        sa.Column("is_late", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "section_id", "question_number", name="uq_candidate_question_response"),
    )
    op.create_index("ix_candidate_response_candidate_section", "candidate_responses", ["candidate_id", "section_id"])

    # question_challenges
    op.create_table(
        "question_challenges",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("section_id", sa.Integer, sa.ForeignKey("examination_sections.id"), nullable=False),
        sa.Column("question_number", sa.Integer, nullable=False),
        sa.Column("answer_key_version_id", sa.Integer, sa.ForeignKey("answer_key_versions.id"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("proposed_answer", sa.String(500)),
        sa.Column("decision", postgresql.ENUM(name="challenge_decision_enum", create_type=False), nullable=False),
        sa.Column("decision_reason", sa.Text),
        sa.Column("decided_by_user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "section_id", "question_number", "answer_key_version_id",
                            name="uq_challenge_per_candidate_question_version"),
    )

    # dropped_questions
    op.create_table(
        "dropped_questions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("section_id", sa.Integer, sa.ForeignKey("examination_sections.id"), nullable=False),
        sa.Column("question_number", sa.Integer, nullable=False),
        sa.Column("answer_key_version_id", sa.Integer, sa.ForeignKey("answer_key_versions.id"), nullable=False),
        sa.Column("marks_rule", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("dropped_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("section_id", "question_number", "answer_key_version_id", name="uq_dropped_question_per_version"),
    )

    # proctoring_events
    op.create_table(
        "proctoring_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.Integer, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("is_confirmed_malpractice", sa.Boolean, default=False, nullable=False),
        sa.Column("confirmed_by_user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("severity >= 1 AND severity <= 10", name="ck_severity_range"),
    )
    op.create_index("ix_proctoring_candidate_id", "proctoring_events", ["candidate_id"])

    # evaluation_results
    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("answer_key_version_id", sa.Integer, sa.ForeignKey("answer_key_versions.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", postgresql.ENUM(name="evaluation_status_enum", create_type=False), nullable=False),
        sa.Column("raw_score", sa.Numeric(14, 6)),
        sa.Column("total_correct", sa.Integer, default=0),
        sa.Column("total_wrong", sa.Integer, default=0),
        sa.Column("total_not_attempted", sa.Integer, default=0),
        sa.Column("total_marked_review_no_option", sa.Integer, default=0),
        sa.Column("negative_marks_deducted", sa.Numeric(14, 6), server_default="0"),
        sa.Column("proctoring_penalty_percentage", sa.Numeric(5, 2), server_default="0"),
        sa.Column("proctoring_penalty_marks", sa.Numeric(14, 6), server_default="0"),
        sa.Column("score_after_proctoring", sa.Numeric(14, 6)),
        sa.Column("normalised_score", sa.Numeric(20, 10)),
        sa.Column("is_normalised", sa.Boolean, default=False),
        sa.Column("attempt_percentage", sa.Numeric(7, 4)),
        sa.Column("error_message", sa.Text),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "version", name="uq_eval_result_candidate_version"),
    )
    op.create_index("ix_eval_result_candidate_id", "evaluation_results", ["candidate_id"])

    # section_results
    op.create_table(
        "section_results",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("evaluation_result_id", sa.BigInteger, sa.ForeignKey("evaluation_results.id"), nullable=False),
        sa.Column("section_id", sa.Integer, sa.ForeignKey("examination_sections.id"), nullable=False),
        sa.Column("raw_section_score", sa.Numeric(14, 6), nullable=False),
        sa.Column("correct_count", sa.Integer, default=0),
        sa.Column("wrong_count", sa.Integer, default=0),
        sa.Column("not_attempted_count", sa.Integer, default=0),
        sa.Column("negative_marks", sa.Numeric(14, 6), server_default="0"),
        sa.Column("is_section_qualified", sa.Boolean),
        sa.Column("cutoff_applied", sa.Numeric(10, 5)),
        sa.Column("failure_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("evaluation_result_id", "section_id", name="uq_section_result_eval_section"),
    )

    # shift_statistics
    op.create_table(
        "shift_statistics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("shift_id", sa.Integer, sa.ForeignKey("shifts.id"), nullable=False, unique=True),
        sa.Column("candidate_count", sa.Integer, nullable=False),
        sa.Column("mean_raw_score", sa.Numeric(20, 10)),
        sa.Column("std_dev_raw_score", sa.Numeric(20, 10)),
        sa.Column("pooled_mean", sa.Numeric(20, 10)),
        sa.Column("pooled_std_dev", sa.Numeric(20, 10)),
        sa.Column("top_score", sa.Numeric(14, 6)),
        sa.Column("computed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # qualification_decisions
    op.create_table(
        "qualification_decisions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("evaluation_result_id", sa.BigInteger, sa.ForeignKey("evaluation_results.id"), nullable=False),
        sa.Column("status", postgresql.ENUM(name="qualification_status_enum", create_type=False), nullable=False),
        sa.Column("reasons", sa.Text),
        sa.Column("overall_cutoff_applied", sa.Numeric(10, 5)),
        sa.Column("category_relaxation_percentage", sa.Numeric(5, 2)),
        sa.Column("effective_cutoff", sa.Numeric(10, 5)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "evaluation_result_id", name="uq_qual_decision_candidate_eval"),
    )

    # merit_lists
    op.create_table(
        "merit_lists",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("examination_id", sa.Integer, sa.ForeignKey("examinations.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", postgresql.ENUM(name="merit_list_status_enum", create_type=False), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("examination_id", "version", name="uq_merit_list_exam_version"),
    )

    # merit_list_entries
    op.create_table(
        "merit_list_entries",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("merit_list_id", sa.Integer, sa.ForeignKey("merit_lists.id"), nullable=False),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("evaluation_result_id", sa.BigInteger, sa.ForeignKey("evaluation_results.id"), nullable=False),
        sa.Column("overall_rank", sa.Integer, nullable=False),
        sa.Column("category_rank", sa.Integer),
        sa.Column("final_score", sa.Numeric(20, 10), nullable=False),
        sa.Column("tie_breaker_applied", sa.String(100)),
        sa.Column("is_allocated", sa.Boolean, default=False, nullable=False),
        sa.Column("allocation_category", sa.String(10)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("merit_list_id", "candidate_id", name="uq_merit_entry_list_candidate"),
    )
    op.create_index("ix_merit_list_entry_rank", "merit_list_entries", ["merit_list_id", "overall_rank"])

    # re_evaluation_requests
    op.create_table(
        "re_evaluation_requests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id"), nullable=False, unique=True),
        sa.Column("initiated_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("previous_result_id", sa.BigInteger, sa.ForeignKey("evaluation_results.id"), nullable=False),
        sa.Column("new_result_id", sa.BigInteger, sa.ForeignKey("evaluation_results.id")),
        sa.Column("answer_key_version_id", sa.Integer, sa.ForeignKey("answer_key_versions.id"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", postgresql.ENUM(name="re_evaluation_status_enum", create_type=False), nullable=False),
        sa.Column("request_count", sa.Integer, default=1, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("request_count <= 1", name="ck_re_eval_max_one_per_candidate"),
    )

    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("action", postgresql.ENUM(name="audit_action_enum", create_type=False), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(100)),
        sa.Column("description", sa.Text),
        sa.Column("old_value", sa.Text),
        sa.Column("new_value", sa.Text),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_log_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_log_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_log_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    # Drop tables in reverse dependency order
    tables = [
        "audit_logs", "re_evaluation_requests", "merit_list_entries", "merit_lists",
        "qualification_decisions", "shift_statistics", "section_results",
        "evaluation_results", "proctoring_events", "dropped_questions",
        "question_challenges", "candidate_responses", "answer_keys",
        "answer_key_versions", "candidates", "shifts", "examination_sections",
        "examinations", "users", "roles",
    ]
    for table in tables:
        op.drop_table(table)

    op.execute("""
        DROP TYPE IF EXISTS audit_action_enum;
        DROP TYPE IF EXISTS re_evaluation_status_enum;
        DROP TYPE IF EXISTS merit_list_status_enum;
        DROP TYPE IF EXISTS qualification_status_enum;
        DROP TYPE IF EXISTS evaluation_status_enum;
        DROP TYPE IF EXISTS challenge_decision_enum;
        DROP TYPE IF EXISTS question_type_enum;
        DROP TYPE IF EXISTS response_status_enum;
        DROP TYPE IF EXISTS candidate_category_enum;
        DROP TYPE IF EXISTS role_name_enum;
    """)
