import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).parent
MANAGER_SOURCE = ROOT.joinpath(
    "src/storage/database/mars_special_quota_manager.py"
).read_text(encoding="utf-8")
TASK_SOURCE = ROOT.joinpath("src/storage/database/task_manager.py").read_text(encoding="utf-8")
PLATFORM_SOURCE = ROOT.joinpath(
    "src/config/third_party_platforms.py"
).read_text(encoding="utf-8")
REFERRAL_SOURCE = ROOT.joinpath(
    "src/storage/database/referral_manager.py"
).read_text(encoding="utf-8")
NODE_SOURCE = ROOT.joinpath(
    "src/graphs/nodes/mars_special_quota_node.py"
).read_text(encoding="utf-8")
MAIN_SOURCE = ROOT.joinpath("src/main.py").read_text(encoding="utf-8")
API_TASK_SOURCE = ROOT.joinpath("src/api/tasks.py").read_text(encoding="utf-8")
MIGRATION_SOURCE = ROOT.joinpath(
    "migrations/versions/marsquota002_backfill_legacy_usage.py"
).read_text(encoding="utf-8")
HTTP_RUN_SOURCE = ROOT.joinpath("scripts/http_run.sh").read_text(encoding="utf-8")


class MarsSpecialQuotaContractTests(unittest.TestCase):
    def test_quota_source_priority_and_internal_unlimited(self):
        self.assertIn('if unlimited:\n            return "internal"', MANAGER_SOURCE)
        self.assertIn('if daily_used < DAILY_LIMIT:\n            return "daily"', MANAGER_SOURCE)
        self.assertIn('if permanent_remaining > 0:\n            return "permanent"', MANAGER_SOURCE)

    def test_special_manager_owns_transaction_boundaries(self):
        self.assertNotIn("TaskManager(", MANAGER_SOURCE)
        self.assertNotIn("db.commit()", MANAGER_SOURCE)
        self.assertNotIn("db.rollback()", MANAGER_SOURCE)

    def test_unknown_stays_reserved_and_reconcile_skips_it(self):
        mark_unknown_section = MANAGER_SOURCE.split("def mark_unknown", 1)[1].split(
            "def reconcile_reserved", 1
        )[0]
        self.assertNotIn('usage.status = "unknown"', mark_unknown_section)
        self.assertIn('"unknown": True', mark_unknown_section)
        reconcile_section = MANAGER_SOURCE.split("def reconcile_reserved", 1)[1]
        self.assertIn('status == "reserved"', reconcile_section)
        query_section = reconcile_section.split(".all()", 1)[0]
        self.assertIn('extra_data["unknown"].as_boolean()', query_section)
        self.assertIn("func.coalesce", query_section)
        self.assertIn("UNKNOWN_RECONCILE_HOURS = 24", MANAGER_SOURCE)
        self.assertIn('"unknown_resolution": "consumed_after_timeout"', reconcile_section)

    def test_reconcile_locks_task_and_usage_then_rechecks_reserved(self):
        reconcile_section = MANAGER_SOURCE.split("def reconcile_reserved", 1)[1]
        self.assertGreaterEqual(reconcile_section.count("with_for_update()"), 2)
        self.assertIn('row.status != "reserved"', reconcile_section)
        self.assertIn("_grant_referral_if_needed(db, task)", reconcile_section)

    def test_generic_task_update_no_longer_rewards_referrals(self):
        self.assertNotIn("process_first_completed_task_reward", TASK_SOURCE)
        self.assertNotIn("referral-reward", TASK_SOURCE)
        self.assertIn('db_task.platform == "local_sub2api"', TASK_SOURCE)
        self.assertIn("火星特供任务只能通过专用接口更新", TASK_SOURCE)
        self.assertIn("db_task.user_id != user_id", TASK_SOURCE)
        self.assertIn("user_id: str = Field(...", API_TASK_SOURCE)

    def test_complete_requires_media_but_idempotent_complete_repairs_reward(self):
        complete_section = MANAGER_SOURCE.split("def complete", 1)[1].split("def fail", 1)[0]
        self.assertIn("_has_valid_result(effective_result)", complete_section)
        self.assertIn("task.result = result", complete_section)
        self.assertIn("_grant_referral_if_needed(db, task)", complete_section)

    def test_deleted_tasks_are_guarded_for_all_special_updates(self):
        lock_section = MANAGER_SOURCE.split("def _lock_task_and_usage", 1)[1].split(
            "def acquire_submission", 1
        )[0]
        self.assertIn("if task.is_deleted", lock_section)

    def test_submission_claim_is_persisted_and_required_for_acceptance(self):
        claim_section = MANAGER_SOURCE.split("def acquire_submission", 1)[1].split(
            "def provider_accepted", 1
        )[0]
        accepted_section = MANAGER_SOURCE.split("def provider_accepted", 1)[1].split(
            "def _grant_account", 1
        )[0]
        self.assertIn('"submission_claim_token": claim_token', claim_section)
        self.assertIn('"submission_lease_expires_at"', claim_section)
        self.assertIn("hmac.compare_digest(claim_token, expected_claim_token)", accepted_section)

    def test_submission_can_be_renewed_by_current_token(self):
        renew_section = MANAGER_SOURCE.split("def renew_submission", 1)[1].split(
            "def _grant_account", 1
        )[0]
        self.assertIn("hmac.compare_digest", renew_section)
        self.assertIn('"submission_lease_expires_at": lease_expires_at.isoformat()', renew_section)
        self.assertIn('operation == "renew_submission"', NODE_SOURCE)

    def test_provider_acceptance_is_idempotent_only_for_same_provider_id(self):
        accepted_section = MANAGER_SOURCE.split("def provider_accepted", 1)[1].split(
            "def renew_submission", 1
        )[0]
        idempotent_position = accepted_section.index('extra.get("provider_accepted_at")')
        self.assertNotIn("lease_expires_at <= cls._now()", accepted_section)
        self.assertIn('MarsSpecialQuotaError("provider_task_id 不能为空")', accepted_section)
        self.assertIn('extra.get("provider_task_id") or task.platform_task_id', accepted_section)
        self.assertIn('"provider_task_id": clean_provider_task_id', accepted_section)
        self.assertIn('MarsSpecialQuotaError("provider_task_id 与已确认任务冲突", 409)', accepted_section)

    def test_referral_policy_is_mars_first_success_only(self):
        reward_section = MANAGER_SOURCE.split("def _grant_referral_if_needed", 1)[1].split(
            "def _has_valid_result", 1
        )[0]
        self.assertIn('Tasks.platform == "local_sub2api"', reward_section)
        self.assertIn('Tasks.status == "completed"', reward_section)
        self.assertIn("REFERRAL_GRANT = 20", MANAGER_SOURCE)
        self.assertIn('policy == "mars_quota_v2"', reward_section)
        self.assertNotIn("gold_credits", reward_section)

    def test_mark_unknown_persists_provider_result(self):
        unknown_section = MANAGER_SOURCE.split("def mark_unknown", 1)[1].split(
            "def reconcile_reserved", 1
        )[0]
        self.assertIn("if result is not None", unknown_section)
        self.assertIn("task.result = result", unknown_section)

    def test_recursive_log_redaction(self):
        self.assertIn('"service_secret"', MAIN_SOURCE)
        self.assertIn('"claim_token"', MAIN_SOURCE)
        self.assertIn('"submission_claim_token"', MAIN_SOURCE)
        self.assertIn("class SensitiveLogFilter", MAIN_SOURCE)
        self.assertIn("record.exc_text = _redact_log_value", MAIN_SOURCE)

    def test_migration_backfills_legacy_usage_idempotently(self):
        self.assertIn("FROM tasks", MIGRATION_SOURCE)
        self.assertIn("WHERE tasks.platform = 'local_sub2api'", MIGRATION_SOURCE)
        self.assertIn("'legacy'", MIGRATION_SOURCE)
        self.assertIn("WHEN tasks.status = 'completed' THEN 'consumed'", MIGRATION_SOURCE)
        self.assertIn("WHEN tasks.status IN ('failed', 'cancelled') THEN 'released'", MIGRATION_SOURCE)
        self.assertIn("ELSE 'reserved'", MIGRATION_SOURCE)
        self.assertIn("json_build_object('platform', 'local_sub2api', 'legacy', true)", MIGRATION_SOURCE)
        self.assertIn("ON CONFLICT DO NOTHING", MIGRATION_SOURCE)

    def test_migration_failure_stops_http_startup(self):
        failure_branch = HTTP_RUN_SOURCE.split('if [ "$ALEMBIC_OK" -ne 1 ]; then', 1)[1].split(
            "fi", 1
        )[0]
        self.assertIn("exit 1", failure_branch)
        self.assertNotIn("continue with runtime DDL fallback", HTTP_RUN_SOURCE)
        self.assertNotIn("mars_billing_2024", HTTP_RUN_SOURCE)

    def test_reserved_local_task_cannot_be_deleted(self):
        delete_section = TASK_SOURCE.split("def delete_task", 1)[1].split(
            "def delete_tasks_by_user_id", 1
        )[0]
        self.assertIn('db_task.platform == "local_sub2api"', delete_section)
        self.assertIn('MarsSpecialQuotaTransactions.status == "reserved"', delete_section)
        self.assertIn("仍有预占次数，不能删除", delete_section)

    def test_generic_update_requires_backend_auth_and_limits_legacy_compat(self):
        update_api = API_TASK_SOURCE.split("async def update_task", 1)[1].split(
            '@router.delete("/tasks/{task_id}")', 1
        )[0]
        update_manager = TASK_SOURCE.split("def update_task", 1)[1].split(
            "def delete_task", 1
        )[0]
        self.assertIn("authorization: Optional[str] = Header(default=None)", update_api)
        self.assertIn("require_backend_authorization(authorization)", update_api)
        self.assertIn("MARS_SPECIAL_QUOTA_LEGACY_UPDATE_COMPAT", update_manager)
        self.assertIn('MarsSpecialQuotaTransactions.source == "legacy"', update_manager)

    def test_task_delete_requires_backend_auth(self):
        delete_api = API_TASK_SOURCE.split("async def delete_task", 1)[1]
        self.assertIn("authorization: Optional[str] = Header(default=None)", delete_api)
        self.assertIn("require_backend_authorization(authorization)", delete_api)

    def test_referral_overview_keeps_gold_and_adds_quota_totals(self):
        self.assertIn('"reward_count": int(reward_count)', REFERRAL_SOURCE)
        self.assertIn('"quota_reward_count": int(quota_reward_count)', REFERRAL_SOURCE)
        self.assertIn('"quota_reward_total": int(quota_reward_total)', REFERRAL_SOURCE)

    def test_local_sub2api_is_not_in_timeout_platforms(self):
        self.assertIn('THIRD_PARTY_PLATFORMS = ("bltcy", "tudou")', PLATFORM_SOURCE)
        self.assertNotIn("local_sub2api", PLATFORM_SOURCE)

    def test_registration_has_no_gold_bonus_or_late_binding(self):
        self.assertNotIn("REGISTER_INVITE_GOLD_BONUS", REFERRAL_SOURCE)
        self.assertNotIn("bind_referral_code", REFERRAL_SOURCE)
        self.assertIn('reward_policy_version="mars_quota_v2"', REFERRAL_SOURCE)

    def test_historical_reward_records_never_receive_quota_backfill(self):
        reward_section = MANAGER_SOURCE.split("def _grant_referral_if_needed", 1)[1].split(
            "def complete", 1
        )[0]
        self.assertIn("ReferralRewardRecords.relation_id == relation.id", reward_section)
        self.assertIn('relation.reward_status = "rewarded"', reward_section)
        historical_branch = reward_section.split("if historical_reward:", 1)[1].split(
            "policy =", 1
        )[0]
        self.assertIn("return []", historical_branch)

    def test_node_has_required_three_parameter_signature(self):
        tree = ast.parse(NODE_SOURCE)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "mars_special_quota_node"
        )
        self.assertEqual([arg.arg for arg in function.args.args], ["state", "config", "runtime"])
        self.assertIsNotNone(function.returns)


if __name__ == "__main__":
    unittest.main()
