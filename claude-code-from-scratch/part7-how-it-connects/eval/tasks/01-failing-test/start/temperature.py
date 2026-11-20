"""Convert temperatures between Celsius and Fahrenheit."""


def c_to_f(celsius):
    return celsius * 9 / 5 + 32


def f_to_c(fahrenheit):
    return fahrenheit - 32 * 5 / 9


def describe(celsius):
    if celsius < 0:
        return "freezing"
    if celsius < 15:
        return "cold"
    if celsius < 25:
        return "mild"
    return "hot"
