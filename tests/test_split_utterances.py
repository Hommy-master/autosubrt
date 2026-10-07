"""分句：只按句末标点断句，逗号、顿号等句内标点留在句子内部"""

import service


def timeline(text):
    """按文案造逐字时间线：chars 不含空白，标点也带时间戳（与 asr 的结果一致）"""
    chars = [char for char in text if not char.isspace()]
    timestamps = [[i * 100, i * 100 + 100] for i in range(len(chars))]
    return chars, timestamps


def split(text):
    """返回分句后的文本列表"""
    return [utterance["text"] for utterance in service.split_utterances(*timeline(text), text)]


def test_sentence_end_punctuations_split():
    assert split("第一点。第二点！第三点？") == ["第一点。", "第二点！", "第三点？"]


def test_clause_punctuations_do_not_split():
    assert split("第一点，第二点、第三点；第四点：收尾。") == ["第一点，第二点、第三点；第四点：收尾。"]


def test_english_sentence_uses_half_width_punctuations():
    assert split("This is a test. And more!") == ["This is a test.", " And more!"]


def test_no_sentence_end_punctuation_keeps_one_utterance():
    assert split("第一点，第二点，第三点") == ["第一点，第二点，第三点"]


def test_long_silence_does_not_split():
    """静音不再兜底断句：没有句末标点就是一句"""
    words = list("你好我好")
    timestamps = [[0, 100], [100, 200], [10_000, 10_100], [10_100, 10_200]]
    assert [u["text"] for u in service.split_utterances(words, timestamps, "你好我好")] == ["你好我好"]


def test_leading_punctuation_does_not_form_empty_utterance():
    assert split("。你好。") == ["。你好。"]


def test_join_equals_full_text():
    text = "你们应该都听过啊，羊毛羊绒当中的软黄金。真的吗？"
    assert "".join(split(text)) == text


def test_words_exclude_punctuation():
    utterances = service.split_utterances(*timeline("你好。"), "你好。")
    assert [word["text"] for word in utterances[0]["words"]] == ["你", "好"]


def test_missing_timestamp_falls_back_to_previous_end():
    """时间戳缺失时退化为上一个字的结束时间，跨句也不冒出 0 时间"""
    words = ["你", "好", "我", "好"]
    timestamps = [[0, 100], None, None, [500, 600]]
    utterances = service.split_utterances(words, timestamps, "你好。我好")

    assert utterances[0]["words"][1]["end_time"] == 100
    assert utterances[1]["words"][0]["start_time"] == 100


def test_unknown_punctuation_is_kept_without_breaking_alignment():
    """标点模型插入标点表之外的标点（如引号）时，不应整段退回无标点序列"""
    words, timestamps = timeline("你好我。好。")
    utterances = service.split_utterances(words, timestamps, "「你好」我。好。")

    assert [u["text"] for u in utterances] == ["「你好」我。", "好。"]
    assert "".join(u["text"] for u in utterances) == "「你好」我。好。"
