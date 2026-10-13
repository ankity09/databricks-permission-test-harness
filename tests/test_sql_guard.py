from app.sql_guard import assert_read_only, ReadOnlyViolation
import pytest

def test_allowed_select():
    assert_read_only('SELECT * FROM t')
    assert_read_only('select 1')
    assert_read_only('  SELECT 1')
    assert_read_only('WITH x AS (SELECT 1) SELECT * FROM x')
    assert_read_only('SHOW TABLES IN c.s')
    assert_read_only('DESCRIBE EXTENDED c.s.t')
    assert_read_only('DESC c.s.t')
    assert_read_only('EXPLAIN SELECT 1')
    assert_read_only('-- a comment\nSELECT 1')
    assert_read_only('/* c */ SELECT 1')
    assert_read_only('SELECT 1;')

def test_blocked_non_read_only():
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('INSERT INTO t VALUES (1)')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('UPDATE t SET a=1')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('DELETE FROM t')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('MERGE INTO t ...')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('DROP TABLE t')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('CREATE TABLE t (a int)')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('ALTER TABLE t ...')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('TRUNCATE TABLE t')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('GRANT SELECT ON t TO u')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('REVOKE SELECT ON t FROM u')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('SELECT 1; DROP TABLE x')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('-- c\nDROP TABLE x')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('/* c */ delete from x')
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('USE CATALOG c')