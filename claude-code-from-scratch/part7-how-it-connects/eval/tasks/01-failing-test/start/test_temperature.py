from temperature import c_to_f, describe, f_to_c


def test_c_to_f():
    assert c_to_f(100) == 212


def test_f_to_c():
    assert f_to_c(212) == 100
    assert f_to_c(32) == 0


def test_describe():
    assert describe(-5) == "freezing"
    assert describe(20) == "mild"
