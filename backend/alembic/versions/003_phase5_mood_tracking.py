"""Phase 5 schema — Mood Tracking, Schedules, Micro-surveys, and Recovery Milestones

Revision ID: 003_phase5_mood_tracking
Revises: 002_cbt_rag_schema
Create Date: 2026-10-01 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_phase5_mood_tracking'
down_revision: Union[str, None] = '002_cbt_rag_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. mood_entries
    op.create_table(
        'mood_entries',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_uuid', sa.String(length=36), sa.ForeignKey('users.user_uuid'), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=32), nullable=False),
        sa.Column('trigger_category', sa.String(length=64), nullable=True),
        sa.Column('raw_selection', sa.String(length=128), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_mood_entries_user_uuid', 'mood_entries', ['user_uuid'])
    op.create_index('ix_mood_entries_user_created', 'mood_entries', ['user_uuid', sa.text('created_at DESC')])

    # 2. checkin_schedules
    op.create_table(
        'checkin_schedules',
        sa.Column('user_uuid', sa.String(length=36), sa.ForeignKey('users.user_uuid'), primary_key=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('preferred_hour_eat', sa.Integer(), nullable=False, default=9),
        sa.Column('last_prompted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('streak_count', sa.Integer(), nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 3. micro_survey_responses
    op.create_table(
        'micro_survey_responses',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_uuid', sa.String(length=36), sa.ForeignKey('users.user_uuid'), nullable=False),
        sa.Column('survey_type', sa.String(length=32), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('responses_json', sa.Text(), nullable=False, default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_micro_survey_responses_user_uuid', 'micro_survey_responses', ['user_uuid'])
    op.create_index('ix_micro_survey_responses_survey_type', 'micro_survey_responses', ['survey_type'])

    # 4. recovery_trackers
    op.create_table(
        'recovery_trackers',
        sa.Column('user_uuid', sa.String(length=36), sa.ForeignKey('users.user_uuid'), primary_key=True),
        sa.Column('target_habit', sa.String(length=64), nullable=False, default='substances'),
        sa.Column('start_date', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('current_streak_days', sa.Integer(), nullable=False, default=0),
        sa.Column('longest_streak_days', sa.Integer(), nullable=False, default=0),
        sa.Column('last_checkin_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('milestones_reached_json', sa.Text(), nullable=False, default='[]'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('recovery_trackers')
    op.drop_table('micro_survey_responses')
    op.drop_table('checkin_schedules')
    op.drop_table('mood_entries')
