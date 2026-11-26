# ファイル名: big_number.gd
# 1e308超対応の正規化大数値クラス（仮数 m: float + 64bit指数 e: int）

class_name BigNumber
extends RefCounted

var m: float = 0.0  # 0.0 または 1.0 <= abs(m) < 10.0
var e: int = 0      # 10進指数（64bit int: 1e308超でもオーバーフローしない）


func _init(mantissa: float = 0.0, exponent: int = 0) -> void:
	m = mantissa
	e = exponent
	normalize()


func normalize() -> void:
	if m == 0.0 or is_nan(m) or is_inf(m):
		m = 0.0
		e = 0
		return
	var a: float = absf(m)
	if a >= 10.0 or a < 1.0:
		var shift: int = floori(log(a) / log(10.0))
		m /= pow(10.0, shift)
		e += shift
		if absf(m) >= 10.0:
			m *= 0.1
			e += 1


static func from_float(value: float) -> BigNumber:
	return BigNumber.new(value, 0)


static func from_log10(log_val: float) -> BigNumber:
	var exp_part: int = floori(log_val)
	return BigNumber.new(pow(10.0, log_val - exp_part), exp_part)


func duplicate_bn() -> BigNumber:
	return BigNumber.new(m, e)


func mul(other: BigNumber) -> BigNumber:
	return BigNumber.new(m * other.m, e + other.e)


func mul_float(scalar: float) -> BigNumber:
	return BigNumber.new(m * scalar, e)


func add(other: BigNumber) -> BigNumber:
	if m == 0.0:
		return BigNumber.new(other.m, other.e)
	if other.m == 0.0:
		return BigNumber.new(m, e)
	var diff: int = e - other.e
	if diff > 15:
		return BigNumber.new(m, e)
	if diff < -15:
		return BigNumber.new(other.m, other.e)
	if diff >= 0:
		return BigNumber.new(m + other.m * pow(10.0, -diff), e)
	return BigNumber.new(other.m + m * pow(10.0, diff), other.e)


func sub(other: BigNumber) -> BigNumber:
	return add(BigNumber.new(-other.m, other.e))


func sub_in_place(other: BigNumber) -> void:
	var res: BigNumber = sub(other)
	m = res.m
	e = res.e


func is_leq_zero() -> bool:
	return m <= 0.0


func ratio_to(max_val: BigNumber) -> float:
	if m <= 0.0 or max_val.m <= 0.0:
		return 0.0
	var diff: int = e - max_val.e
	if diff < -300:
		return 0.0
	if diff > 300:
		return 1.0
	return clampf((m / max_val.m) * pow(10.0, diff), 0.0, 1.0)


func format_short() -> String:
	if m <= 0.0:
		return "0"
	if e < 3:
		return "%.1f" % (m * pow(10.0, e))
	if e < 6:
		return str(roundi(m * pow(10.0, e)))
	return "%.2fe%d" % [m, e]
