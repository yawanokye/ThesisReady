from app.action_items import detach_action_items


def test_inline_actions_are_removed_from_academic_prose_and_listed_separately():
    text = "1.1 Introduction\n\nSome details require confirmation: [confirm school type], and [insert policy source]. The study examines assessment."
    out = detach_action_items(text)
    assert "[confirm school type]" not in out.split("USER ACTIONS REQUIRED")[0]
    assert "[ACTION REQUIRED 1:" in out
    assert "[ACTION REQUIRED 2:" in out
    assert "The study examines assessment." in out


def test_action_items_are_deduplicated():
    out = detach_action_items("Text [insert source].\n\nMore text [insert source].")
    assert out.count("[ACTION REQUIRED") == 1
