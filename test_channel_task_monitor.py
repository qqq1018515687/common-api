from storage.database.channel_task_monitor import MONITORED_MODELS, TaskSignal, decide_action


NOW = 1_000_000_000
MODEL = "gpt_image_2_tudou"


def signal(status: str, seconds_ago: int, reason: str = "provider_failed") -> TaskSignal:
    return TaskSignal(MODEL, "GPT Image 2", status, reason, NOW - seconds_ago * 1000)


def test_three_consecutive_provider_failures_raise_alert():
    events = [signal("failed", 20), signal("failed", 60), signal("failed", 120)]
    assert decide_action(events, None, NOW) == "alert"


def test_all_current_t_models_are_monitored():
    assert MONITORED_MODELS == {
        "banana2_tudou",
        "banana_pro_tudou",
        "gpt_image_2_tudou",
        "gpt_image_2_5_flare_tudou",
        "gpt_image_2_5_sunburst_tudou",
    }


def test_other_failures_and_success_break_failure_streak():
    events = [signal("failed", 20), signal("failed", 60, "recovery_timeout_failed"), signal("failed", 120)]
    assert decide_action(events, None, NOW) is None
    assert decide_action([signal("completed", 10), *events], None, NOW) is None


def test_stale_failures_do_not_raise_alert():
    events = [signal("failed", 601), signal("failed", 602), signal("failed", 603)]
    assert decide_action(events, None, NOW) is None


def test_three_successes_after_cooldown_recover():
    events = [signal("completed", 10), signal("completed", 60), signal("completed", 120)]
    assert decide_action(events, NOW - 6 * 60 * 1000, NOW) == "recover"
    assert decide_action(events, NOW - 3 * 60 * 1000, NOW) is None


def test_recent_failure_or_no_samples_keeps_alert_active():
    events = [signal("completed", 10), signal("completed", 60), signal("completed", 120), signal("failed", 180)]
    assert decide_action(events, NOW - 6 * 60 * 1000, NOW) is None
    assert decide_action([], NOW - 6 * 60 * 1000, NOW) is None
