from oracle_db_agent.intent import AnalyzeAwrIntent, UnlockUserIntent, parse_intent


def test_parse_unlock_user_with_username() -> None:
    intent = parse_intent("unlock user scott")

    assert isinstance(intent, UnlockUserIntent)
    assert intent.username == "scott"


def test_parse_unlock_user_without_username() -> None:
    intent = parse_intent("unlock a database user")

    assert isinstance(intent, UnlockUserIntent)
    assert intent.username is None


def test_parse_awr_days() -> None:
    intent = parse_intent("analyze past 4 days database report")

    assert isinstance(intent, AnalyzeAwrIntent)
    assert intent.days == 4


def test_parse_awr_days_is_capped() -> None:
    intent = parse_intent("analyze past 100 days database report")

    assert isinstance(intent, AnalyzeAwrIntent)
    assert intent.days == 31
