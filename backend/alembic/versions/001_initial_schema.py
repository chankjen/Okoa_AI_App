"""Initial schema for OKOA AI

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-28 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('user_uuid', sa.String(length=36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('consent_status', sa.Enum('pending', 'granted', 'withdrawn', name='consent_status'), nullable=False),
        sa.Column('opt_out', sa.Boolean(), nullable=False, default=False),
        sa.Column('data_purged', sa.Boolean(), nullable=False, default=False),
    )

    # 2. identity_vault (PII lives only here encrypted)
    op.create_table(
        'identity_vault',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('blind_index', sa.String(length=64), nullable=False),
        sa.Column('user_uuid', sa.String(length=36), nullable=False),
        sa.Column('cipher_nonce', sa.LargeBinary(length=12), nullable=False),
        sa.Column('ciphertext', sa.LargeBinary(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('purged_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_identity_vault_blind_index', 'identity_vault', ['blind_index'], unique=True)
    op.create_index('ix_identity_vault_user_uuid', 'identity_vault', ['user_uuid'], unique=True)

    # 3. chat_sessions
    op.create_table(
        'chat_sessions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_uuid', sa.String(length=36), sa.ForeignKey('users.user_uuid'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_chat_sessions_user_uuid', 'chat_sessions', ['user_uuid'])

    # 4. messages
    op.create_table(
        'messages',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('session_id', sa.String(length=36), sa.ForeignKey('chat_sessions.id'), nullable=False),
        sa.Column('direction', sa.Enum('inbound', 'outbound', name='msg_direction'), nullable=False),
        sa.Column('kind', sa.Enum('user_text', 'canned_reply', 'crisis_response', 'consent_prompt', 'system', name='msg_kind'), nullable=False),
        sa.Column('wa_message_id', sa.String(length=64), unique=True, nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('risk_label', sa.String(length=16), nullable=True),
    )
    op.create_index('ix_messages_session_id', 'messages', ['session_id'])
    op.create_index('ix_messages_session_created', 'messages', ['session_id', 'created_at'])

    # 5. risk_assessments
    op.create_table(
        'risk_assessments',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('message_id', sa.String(length=36), sa.ForeignKey('messages.id'), nullable=True),
        sa.Column('user_uuid', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=True),
        sa.Column('label', sa.Enum('safe', 'distressed', 'crisis', name='risk_label'), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('crisis_prob', sa.Float(), nullable=False, default=0.0),
        sa.Column('distress_prob', sa.Float(), nullable=False, default=0.0),
        sa.Column('model_version', sa.String(length=32), nullable=False, default='rules-v1'),
        sa.Column('features_json', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Float(), nullable=True),
        sa.Column('intercepted', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_risk_assessments_user_uuid', 'risk_assessments', ['user_uuid'])
    op.create_index('ix_risk_assessments_user_created', 'risk_assessments', ['user_uuid', 'created_at'])

    # 6. escalations
    op.create_table(
        'escalations',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_uuid', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('trigger_message_id', sa.String(length=36), sa.ForeignKey('messages.id'), nullable=True),
        sa.Column('risk_score', sa.Float(), nullable=False, default=0.0),
        sa.Column('risk_label', sa.Enum('safe', 'distressed', 'crisis', name='escalation_risk_label'), nullable=False),
        sa.Column('status', sa.Enum('open', 'claimed', 'handed_over', 'resolved', 'muted', name='escalation_status'), nullable=False, default='open'),
        sa.Column('claimed_by', sa.String(length=36), nullable=True),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_response_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.Enum('helpline_confirmed', 'counselor_contacted', 'false_positive', 'unreachable', 'other', name='escalation_outcome'), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_escalations_user_uuid', 'escalations', ['user_uuid'])
    op.create_index('ix_escalations_session_id', 'escalations', ['session_id'])
    op.create_index('ix_escalations_status', 'escalations', ['status'])
    op.create_index('ix_escalations_open_priority', 'escalations', ['status', 'risk_score'])

    # 7. session_controls (handover)
    op.create_table(
        'session_controls',
        sa.Column('user_uuid', sa.String(length=36), primary_key=True),
        sa.Column('mode', sa.Enum('bot_active', 'counselor_active', name='handover_mode'), nullable=False, default='bot_active'),
        sa.Column('active_escalation_id', sa.String(length=36), sa.ForeignKey('escalations.id'), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('changed_by', sa.String(length=36), nullable=True),
    )

    # 8. counselors
    op.create_table(
        'counselors',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('username', sa.String(length=64), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(length=128), nullable=False),
        sa.Column('display_name', sa.String(length=128), nullable=False),
        sa.Column('phone_e164', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=256), nullable=True),
        sa.Column('is_on_duty', sa.Boolean(), default=False, nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_counselors_username', 'counselors', ['username'], unique=True)
    op.create_index('ix_counselors_is_on_duty', 'counselors', ['is_on_duty'])

    # 9. audit_log
    op.create_table(
        'audit_log',
        sa.Column('seq', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('actor_type', sa.String(length=16), nullable=False),
        sa.Column('actor_id', sa.String(length=36), nullable=True),
        sa.Column('action', sa.Enum(
            'escalation_created', 'escalation_claimed', 'escalation_unclaimed',
            'handover_started', 'handover_ended', 'counselor_replied',
            'escalation_resolved', 'escalation_muted', 'notification_sent',
            'notification_failed', 'login_success', 'login_failure',
            'drill_recorded', name='audit_action'
        ), nullable=False),
        sa.Column('subject_uuid', sa.String(length=36), nullable=True),
        sa.Column('details_json', sa.Text(), nullable=False, default='{}'),
        sa.Column('prev_hash', sa.String(length=64), nullable=False, default=''),
        sa.Column('entry_hash', sa.String(length=64), nullable=False, default=''),
    )
    op.create_index('ix_audit_log_subject_uuid', 'audit_log', ['subject_uuid'])

    # 10. response_drills
    op.create_table(
        'response_drills',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('performed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('scenario', sa.String(length=128), nullable=False),
        sa.Column('seconds_to_first_response', sa.Float(), nullable=False),
        sa.Column('participants', sa.String(length=256), nullable=True),
        sa.Column('passed', sa.Boolean(), default=False, nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
    )
    op.create_index('ix_response_drills_performed_at', 'response_drills', ['performed_at'])


def downgrade() -> None:
    op.drop_table('response_drills')
    op.drop_table('audit_log')
    op.drop_table('counselors')
    op.drop_table('session_controls')
    op.drop_table('escalations')
    op.drop_table('risk_assessments')
    op.drop_table('messages')
    op.drop_table('chat_sessions')
    op.drop_table('identity_vault')
    op.drop_table('users')
