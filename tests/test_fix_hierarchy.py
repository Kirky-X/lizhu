import fix_mineru_hierarchy as fx


class TestStripChapterPrefix:
    def test_numeric_prefix(self):
        assert fx.strip_chapter_prefix("10..达克效应") == "达克效应"

    def test_chapter_word(self):
        assert fx.strip_chapter_prefix("第3章 引言") == "引言"

    def test_chinese_enum(self):
        assert fx.strip_chapter_prefix("一、概述") == "概述"

    def test_plain_text_unchanged(self):
        assert fx.strip_chapter_prefix("开窍") == "开窍"


class TestClassify:
    def test_empty_is_front(self):
        assert fx.classify("") == "front"

    def test_generic_front_matter(self):
        assert fx.classify("ISBN 978-7-5001-0000-0") == "front"
        assert fx.classify("图书在版编目(CIP)数据") == "front"
        assert fx.classify("定价：59.00 元") == "front"

    def test_publisher_line_not_front(self):
        # 过拟合修复回归：出版社/书名/作者专属条目已从清单移除，不再误判为前置页
        assert fx.classify("北京联合出版公司") != "front"
        assert fx.classify("Psychologie des Foules") != "front"
        assert fx.classify("所长林超著") != "front"

    def test_part(self):
        assert fx.classify("第一部分 认知升级") == "part"

    def test_chapter(self):
        assert fx.classify("第3章 心智模型") == "chapter"
        assert fx.classify("原则1 拥抱现实") == "chapter"

    def test_subsection(self):
        assert fx.classify("01 什么是思维模型") == "subsection"

    def test_sub_sub(self):
        assert fx.classify("一、背景") == "sub_sub"
        assert fx.classify("第一步 明确问题") == "sub_sub"

    def test_short_heading_is_chapter(self):
        assert fx.classify("开窍") == "chapter"

    def test_long_text_is_content(self):
        assert fx.classify("这是一个很长很长的正文段落远远超过十五个字的限制") == "content"


class TestMdformatArtifact:
    def test_single_char(self):
        assert fx.is_mdformat_artifact("的") is True

    def test_english_short(self):
        assert fx.is_mdformat_artifact("ab") is True

    def test_real_heading(self):
        assert fx.is_mdformat_artifact("心智模型的力量") is False


class TestFindBookTitle:
    def test_empty_hint_returns_none(self):
        assert fx.find_book_title(["第一章"], "") is None

    def test_exact_match(self):
        assert fx.find_book_title(["开窍", "第一章 开窍"], "开窍") == "开窍"

    def test_fallback_to_hint(self):
        assert fx.find_book_title(["第1章 导论", "1.1 背景"], "不存在的书名") == "不存在的书名"
