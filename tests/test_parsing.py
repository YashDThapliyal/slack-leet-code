import pytest

from leetbot.parsing import Adjust, AdjustUsageError, Command, Solve, normalize_problem, parse


@pytest.mark.parametrize(
    "name, key",
    [
        ("Two Sum", "two sum"),
        ("1. Two Sum", "two sum"),
        ("1) two-sum", "two sum"),
        ("  TWO   SUM!! ", "two sum"),
        ("#1 Two Sum", "two sum"),
        ("Pascal's Triangle", "pascals triangle"),
        ("3Sum", "3sum"),
        ("15. 3Sum", "3sum"),
        ("Pow(x, n)", "pow x n"),
        ("24 Game", "24 game"),
        ("01 Matrix", "01 matrix"),
        ("https://leetcode.com/problems/two-sum/description/", "two sum"),
    ],
)
def test_normalize_problem(name, key):
    assert normalize_problem(name) == key


@pytest.mark.parametrize(
    "word, difficulty",
    [("easy", "easy"), ("E", "easy"), ("ez", "easy"), ("med", "medium"), ("m", "medium"), ("Medium", "medium"),
     ("mid", "medium"), ("h", "hard"), ("HARD", "hard"), ("(hard)", "hard")],
)
def test_difficulty_aliases(word, difficulty):
    solve = parse(f"leet Two Sum {word}", has_image=True)
    assert solve == Solve("Two Sum", "two sum", difficulty, True)


def test_points_by_difficulty():
    assert [parse(f"leet x {d}", True).points for d in ("easy", "medium", "hard")] == [1, 2, 3]


def test_missing_difficulty_defaults_to_easy():
    assert parse("leet Two Sum", has_image=True) == Solve("Two Sum", "two sum", "easy", False)


def test_problem_named_like_command_logs_with_screenshot():
    assert isinstance(parse("leet Add Binary easy", has_image=True), Solve)
    assert isinstance(parse("leet Remove Element e", has_image=True), Solve)
    assert isinstance(parse("leet board", has_image=True), Solve)


def test_slack_link_uses_its_label():
    solve = parse("leet <https://leetcode.com/problems/two-sum/|Two Sum> medium", has_image=True)
    assert solve.problem == "Two Sum"


def test_not_a_leet_message():
    assert parse("let me know", has_image=False) is None
    assert parse("leetcode is fun", has_image=False) is None
    assert parse("", has_image=False) is None


@pytest.mark.parametrize("text", ["leet board", "LEET  Board", "leet bord", "leet borad", "leet leaderboard", "leet lb"])
def test_board_command_is_typo_tolerant(text):
    assert parse(text, has_image=False) == Command("board", ())


def test_board_all():
    assert parse("leet board all", has_image=False) == Command("board", ("all",))


@pytest.mark.parametrize("text, name", [("leet me", "me"), ("leet stats", "me"), ("leet help", "help"), ("leet", "help")])
def test_other_commands(text, name):
    assert parse(text, has_image=False).name == name


def test_unknown_word_without_screenshot_is_a_solve_attempt():
    assert isinstance(parse("leet Two Sum easy", has_image=False), Solve)


def test_admin_add_and_remove():
    assert parse("leet add <@U123> 2 forgot to log", False) == Adjust(1, "U123", 2, "forgot to log")
    assert parse("leet remove <@U123|alex> 3 fake screenshot", True) == Adjust(-1, "U123", 3, "fake screenshot")


@pytest.mark.parametrize(
    "text",
    ["leet add <@U123>", "leet add <@U123> two oops", "leet remove <@U123> 2", "leet add <@U1> 0 x",
     "leet add <@U1> ² x", "leet add <@U1> 5000 x"],
)
def test_admin_usage_errors(text):
    assert isinstance(parse(text, False), AdjustUsageError)


def test_pasted_link_matches_typed_title():
    linked = parse("leet <https://leetcode.com/problems/two-sum/> e", has_image=True)
    assert linked.problem_key == parse("leet Two Sum e", has_image=True).problem_key


@pytest.mark.parametrize("text", ["leeet board", "Lete board", "leat board", "leet: board"])
def test_prefix_typos(text):
    assert parse(text, has_image=False) == Command("board", ())


@pytest.mark.parametrize("text", ["let me know", "left the meeting", "meet board"])
def test_ordinary_words_are_not_the_prefix(text):
    assert parse(text, has_image=False) is None


def test_typo_commands_need_to_be_the_whole_message():
    assert parse("leet bord all", has_image=False) == Command("board", ("all",))
    assert isinstance(parse("leet stars graph m", has_image=False), Solve)
    assert isinstance(parse("leet bored game e", has_image=False), Solve)
