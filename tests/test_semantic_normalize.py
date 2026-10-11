import semantic_normalize as sn


def make_stats():
    return sn.Stats()


class TestIsBlockStarter:
    def test_heading(self):
        assert sn.is_block_starter("## 标题") is True

    def test_table_row(self):
        assert sn.is_block_starter("| a | b |") is True

    def test_plain_paragraph_not_starter(self):
        assert sn.is_block_starter("这是一段普通正文文字。") is False


class TestFixTableBlock:
    def test_adds_outer_pipes_and_separator(self):
        stats = make_stats()
        rows = sn.fix_table_block(["名称, 数量", "苹果, 3"], stats)
        assert rows[0] == "| 名称, 数量 |"
        assert "---" in rows[1]
        assert stats.table_repairs == 1

    def test_pads_ragged_columns(self):
        stats = make_stats()
        rows = sn.fix_table_block(["| a | b |", "| 1 |"], stats)
        assert rows[2] == "| 1 |  |"

    def test_complete_table_untouched(self):
        stats = make_stats()
        rows = ["| a | b |", "| --- | --- |", "| 1 | 2 |"]
        assert sn.fix_table_block(list(rows), stats) == rows
        assert stats.table_repairs == 0


class TestListContinuation:
    def test_indented_continuation(self):
        assert sn.is_list_continuation("- 第一项", "  续行内容") is True

    def test_new_block_not_continuation(self):
        assert sn.is_list_continuation("- 第一项", "## 新标题") is False

    def test_unindented_not_continuation(self):
        assert sn.is_list_continuation("- 第一项", "普通正文") is False
