"""Tests for SQL tokenizer (A2: sql_guard bypass prevention)."""

import pytest
from app.sql_guard import assert_read_only, ReadOnlyViolation


class TestBypassesBlocked:
    """SQL injection bypasses that must be blocked."""

    def test_cte_before_insert_is_blocked(self):
        """CTE followed by INSERT is not allowed."""
        with pytest.raises(ReadOnlyViolation):
            assert_read_only("WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x")

    def test_cte_before_delete_is_blocked(self):
        """CTE followed by DELETE is not allowed."""
        with pytest.raises(ReadOnlyViolation):
            assert_read_only("WITH x AS (SELECT 1) DELETE FROM t")

    def test_cte_before_update_is_blocked(self):
        """CTE followed by UPDATE is not allowed."""
        with pytest.raises(ReadOnlyViolation):
            assert_read_only("WITH x AS (SELECT 1) UPDATE t SET a=1")

    def test_nested_block_comments_bypass(self):
        """Nested block comments that hide DELETE."""
        with pytest.raises(ReadOnlyViolation):
            assert_read_only("/* /* */ DELETE FROM t SELECT 1 */")

    def test_string_containing_semicolon_allowed(self):
        """Semicolon inside string literal is allowed."""
        assert_read_only("SELECT ';' AS x")

    def test_string_containing_double_dash_allowed(self):
        """Double-dash inside string literal is allowed."""
        assert_read_only("SELECT '--' AS x")

    def test_string_containing_drop_keyword_allowed(self):
        """DROP keyword inside string literal is allowed."""
        assert_read_only("SELECT 'DROP TABLE' AS note")

    def test_double_quoted_string_with_semicolon_allowed(self):
        """Semicolon inside double-quoted string is allowed."""
        assert_read_only('SELECT ";" AS x')

    def test_backtick_quoted_keyword_allowed(self):
        """Keyword in backtick quotes is allowed."""
        assert_read_only("SELECT `update` FROM t")
        assert_read_only("SELECT `delete` FROM t")

    def test_multiple_statements_with_semicolon_blocked(self):
        """Multiple statements separated by semicolon are blocked."""
        with pytest.raises(ReadOnlyViolation):
            assert_read_only("SELECT 1; DROP TABLE t")

    def test_execute_immediate_blocked(self):
        """EXECUTE IMMEDIATE is blocked."""
        with pytest.raises(ReadOnlyViolation):
            assert_read_only("EXECUTE IMMEDIATE 'DROP TABLE t'")

    def test_begin_drop_end_blocked(self):
        """BEGIN block with DROP is blocked."""
        with pytest.raises(ReadOnlyViolation):
            assert_read_only("BEGIN DROP TABLE t; END")

    def test_line_comment_with_delete_blocked(self):
        """Line comment followed by DELETE is blocked."""
        with pytest.raises(ReadOnlyViolation):
            assert_read_only("-- SELECT\nDELETE FROM t")


class TestValidQueriesAllowed:
    """Valid read-only queries that must be allowed."""

    def test_simple_select(self):
        """Simple SELECT is allowed."""
        assert_read_only("SELECT * FROM t")

    def test_with_clause_select(self):
        """WITH clause followed by SELECT is allowed."""
        assert_read_only("WITH a AS (SELECT 1) SELECT * FROM a")

    def test_with_multiple_ctes(self):
        """Multiple CTEs with SELECT is allowed."""
        assert_read_only("WITH a AS (SELECT 1), b AS (SELECT 2) SELECT * FROM a JOIN b")

    def test_show_tables(self):
        """SHOW TABLES is allowed."""
        assert_read_only("SHOW TABLES IN c.s")

    def test_describe_table(self):
        """DESCRIBE TABLE is allowed."""
        assert_read_only("DESCRIBE EXTENDED c.s.t")

    def test_desc_table(self):
        """DESC TABLE is allowed."""
        assert_read_only("DESC c.s.t")

    def test_explain_select(self):
        """EXPLAIN SELECT is allowed."""
        assert_read_only("EXPLAIN SELECT 1")

    def test_select_with_line_comment_before(self):
        """Line comment before SELECT is allowed."""
        assert_read_only("-- a comment\nSELECT 1")

    def test_select_with_block_comment_before(self):
        """Block comment before SELECT is allowed."""
        assert_read_only("/* c */ SELECT 1")

    def test_select_with_trailing_semicolon(self):
        """SELECT with trailing semicolon is allowed."""
        assert_read_only("SELECT 1;")

    def test_select_with_multiple_comments(self):
        """SELECT with multiple comments is allowed."""
        assert_read_only("-- comment1\n/* comment2 */ SELECT 1")

    def test_select_with_update_in_string(self):
        """SELECT with UPDATE keyword in string is allowed."""
        assert_read_only("SELECT 'UPDATE t SET' AS col FROM t")

    def test_select_from_table_named_delete(self):
        """SELECT from table named delete (in backticks) is allowed."""
        assert_read_only("SELECT * FROM `delete`")

    def test_explain_with_cte(self):
        """EXPLAIN WITH CTE is allowed."""
        assert_read_only("EXPLAIN WITH a AS (SELECT 1) SELECT * FROM a")

    def test_show_databases(self):
        """SHOW DATABASES is allowed."""
        assert_read_only("SHOW DATABASES")

    def test_show_with_line_comment(self):
        """SHOW with line comment is allowed."""
        assert_read_only("-- comment\nSHOW TABLES")
