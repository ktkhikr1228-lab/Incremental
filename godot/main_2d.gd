# ファイル名: main_2d.gd

extends Node2D

@export var first_weapons: Array[WeaponData]
@export var card_pool: Array[CardData]

# --- F2_採用推奨 バランス定数（W1〜W100 Vertical Slice + W5000拡張土台） ---
const GODOT_HP_SCALE: float = 4.0
const MANUAL_BASE_DAMAGE: float = 2.0

# Sim基準の通常敵HPアンカー（get_enemy_hpで GODOT_HP_SCALE を乗算）
const HP_ANCHORS: Array = [
	[1, 4.8],
	[10, 19.5],
	[30, 145.0],
	[50, 580.0],
	[100, 4400.0],
]

# 10WaveごとのBoss倍率（W10は15秒制限に合わせて1.35倍）
const BOSS_MULT: Dictionary = {
	10: 1.35, 20: 1.65, 30: 1.80, 40: 1.85, 50: 1.95,
	60: 1.95, 70: 2.00, 80: 2.05, 90: 2.10, 100: 2.25,
}

# Lv1〜20 必要XPテーブル（Lv21以降は ×1.30）
const XP_COSTS: Array[float] = [
	3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 14.0, 17.0,
	21.0, 26.0, 32.0, 40.0, 50.0, 62.0, 78.0, 98.0, 125.0, 160.0,
]

# --- Run状態 ---
var hp: BigNumber = BigNumber.from_float(19.2)
var max_hp: BigNumber = BigNumber.from_float(19.2)
var wave: int = 1
var has_weapon: bool = false
var current_weapon: WeaponData = null
var is_dead: bool = false

var weapon_choice_1: WeaponData = null
var weapon_choice_2: WeaponData = null
var is_choosing_weapon: bool = false

var card_choice_1: CardData = null
var card_choice_2: CardData = null
var card_choice_3: CardData = null
var pending_picks: int = 0

var manual_attack_multiplier: float = 1.0
var auto_attack_multiplier: float = 1.0
var attack_speed_multiplier: float = 1.0
var all_damage_multiplier: float = 1.0
var crit_rate: float = 0.01
var crit_multiplier: float = 2.0
var xp_multiplier: float = 1.0

var xp: float = 0.0
var level: int = 1
var xp_to_level: float = 3.0

# 60fps超の攻撃速度にも対応するアキュムレータ（$AttackTimer上限を撤廃）
var attack_accumulator: float = 0.0
var game_speed: float = 1.0


func _ready() -> void:
	randomize()
	# シーン側シグナル未接続時の安全フォールバック
	if not $EnemyTimer.timeout.is_connected(_on_enemy_timer_timeout):
		$EnemyTimer.timeout.connect(_on_enemy_timer_timeout)
	if not $RetryButton.pressed.is_connected(_on_retry_button_pressed):
		$RetryButton.pressed.connect(_on_retry_button_pressed)

	$RetryButton.text = "Retry"
	$StatusLabel.text = ""
	$RetryButton.hide()
	$CardChoicePanel.hide()
	$WeaponChoicePanel.hide()
	$AttackTimer.stop()

	start_new_run()


func start_new_run() -> void:
	is_dead = false
	wave = 1
	has_weapon = false
	current_weapon = null
	is_choosing_weapon = false
	pending_picks = 0

	manual_attack_multiplier = 1.0
	auto_attack_multiplier = 1.0
	attack_speed_multiplier = 1.0
	all_damage_multiplier = 1.0
	crit_rate = 0.01
	crit_multiplier = 2.0
	xp_multiplier = 1.0

	xp = 0.0
	level = 1
	xp_to_level = get_xp_to_level(level)
	attack_accumulator = 0.0

	$StatusLabel.text = ""
	$WeaponLabel.text = "Weapon: None"
	$RetryButton.hide()
	$CardChoicePanel.hide()
	$WeaponChoicePanel.hide()

	spawn_wave(wave)
	update_ui()


func _process(_delta: float) -> void:
	if not is_dead:
		$TimeLabel.text = "Time: " + str(ceil($EnemyTimer.time_left))


func _physics_process(delta: float) -> void:
	if is_dead or not has_weapon or current_weapon == null:
		return

	var aps: float = attack_speed_multiplier / maxf(current_weapon.attack_interval, 0.001)
	attack_accumulator += aps * delta * game_speed
	var hits: int = floori(attack_accumulator)
	if hits <= 0:
		return
	attack_accumulator -= float(hits)

	var base_auto: float = current_weapon.damage * auto_attack_multiplier * all_damage_multiplier
	if hits <= 8:
		for _i in range(hits):
			if is_dead:
				break
			attack_enemy(BigNumber.from_float(base_auto * roll_crit_multiplier()))
	else:
		# 高AS帯（>480回/秒相当）は期待値バッチ評価でO(1)処理
		var expected_crit: float = 1.0 + crit_rate * (crit_multiplier - 1.0)
		attack_enemy(BigNumber.from_float(base_auto * expected_crit).mul_float(float(hits)))


func _on_button_pressed() -> void:
	if not is_dead:
		var dmg: float = MANUAL_BASE_DAMAGE * manual_attack_multiplier * all_damage_multiplier * roll_crit_multiplier()
		attack_enemy(BigNumber.from_float(dmg))


func _on_attack_timer_timeout() -> void:
	# 自動攻撃は _physics_process のアキュムレータへ移行済み
	pass


func attack_enemy(damage: BigNumber) -> void:
	if is_dead:
		return
	hp.sub_in_place(damage)

	if hp.is_leq_zero():
		xp += get_kill_xp(wave)
		wave += 1
		check_level_up()
		spawn_wave(wave)

		if wave >= 10 and not has_weapon and not is_choosing_weapon:
			get_first_weapon()

	update_ui()


func spawn_wave(w: int) -> void:
	max_hp = get_enemy_hp(w)
	hp = max_hp.duplicate_bn()
	$EnemyTimer.wait_time = get_wave_time_limit(w)
	$EnemyTimer.start()


func is_boss_wave(w: int) -> bool:
	return w % 10 == 0


func get_wave_time_limit(w: int) -> float:
	return 15.0 if is_boss_wave(w) else 10.0


func get_enemy_hp(w: int = wave) -> BigNumber:
	var sim_hp: float = HP_ANCHORS[0][1]
	if w <= 100:
		for i in range(HP_ANCHORS.size() - 1):
			var a: float = HP_ANCHORS[i][0]
			var x: float = HP_ANCHORS[i][1]
			var b: float = HP_ANCHORS[i + 1][0]
			var y: float = HP_ANCHORS[i + 1][1]
			if w <= b:
				var frac: float = (float(w) - a) / (b - a)
				sim_hp = pow(10.0, (log(x) + (log(y) - log(x)) * frac) / log(10.0))
				break
		if is_boss_wave(w):
			sim_hp *= float(BOSS_MULT.get(w, 1.95))
		return BigNumber.from_float(sim_hp * GODOT_HP_SCALE)

	# W101以降は5幕マスターペーシング曲線（W100: 4.20 -> W5000: 308.00）へ滑らかに接続
	var log_hp: float = 4.20 + (float(w - 100) / 4900.0) * (308.0 - 4.20)
	if not is_boss_wave(w):
		log_hp -= 0.45
	return BigNumber.from_log10(log_hp)


func get_xp_to_level(lv: int) -> float:
	var idx: int = lv - 1
	if idx < XP_COSTS.size():
		return XP_COSTS[idx]
	return round(XP_COSTS[-1] * pow(1.30, idx - (XP_COSTS.size() - 1)))


func get_kill_xp(w: int) -> float:
	var base_xp: float = float(1 + int((w - 1) / 10))
	var boss_factor: float = 10.0 if (w % 100 == 0) else (3.0 if is_boss_wave(w) else 1.0)
	return base_xp * boss_factor * xp_multiplier


func roll_crit_multiplier() -> float:
	return crit_multiplier if randf() < crit_rate else 1.0


func get_first_weapon() -> void:
	if first_weapons.size() < 2:
		print("first_weapons requires at least 2 entries")
		return

	is_choosing_weapon = true
	weapon_choice_1 = first_weapons[0]
	weapon_choice_2 = first_weapons[1]

	$WeaponChoicePanel/WeaponButton1.text = (
		weapon_choice_1.weapon_name
		+ "\nDamage: " + str(weapon_choice_1.damage)
		+ "\nInterval: " + str(weapon_choice_1.attack_interval) + "s"
	)
	$WeaponChoicePanel/WeaponButton2.text = (
		weapon_choice_2.weapon_name
		+ "\nDamage: " + str(weapon_choice_2.damage)
		+ "\nInterval: " + str(weapon_choice_2.attack_interval) + "s"
	)

	$WeaponChoicePanel.show()


func _on_enemy_timer_timeout() -> void:
	is_dead = true
	pending_picks = 0
	$AttackTimer.stop()
	$CardChoicePanel.hide()
	$WeaponChoicePanel.hide()
	$StatusLabel.text = "Defeated (Wave " + str(wave) + ")"
	$RetryButton.show()


func _on_retry_button_pressed() -> void:
	start_new_run()


func update_ui() -> void:
	var boss_tag: String = " [BOSS]" if is_boss_wave(wave) else ""
	$Label.text = "HP: " + hp.format_short() + " / " + max_hp.format_short()
	$WaveLabel.text = "Wave: " + str(wave) + boss_tag
	$LevelLabel.text = "Level: " + str(level) + (" (Pick x" + str(pending_picks) + ")" if pending_picks > 0 else "")
	$XPLabel.text = "XP: " + str(floori(xp)) + "/" + str(roundi(xp_to_level))

	$ManualMultiplierLabel.text = "Manual Attack: x%.2f" % manual_attack_multiplier
	$AutoMultiplierLabel.text = "Auto Attack: x%.2f" % auto_attack_multiplier
	$AttackSpeedMultiplierLabel.text = "Attack Speed: x%.2f" % attack_speed_multiplier


func equip_weapon(weapon: WeaponData) -> void:
	has_weapon = true
	is_choosing_weapon = false
	current_weapon = weapon
	attack_accumulator = 0.0

	$WeaponLabel.text = "Weapon: " + current_weapon.weapon_name
	$WeaponChoicePanel.hide()
	update_ui()


func _on_weapon_button_1_pressed() -> void:
	if weapon_choice_1 != null:
		equip_weapon(weapon_choice_1)


func _on_weapon_button_2_pressed() -> void:
	if weapon_choice_2 != null:
		equip_weapon(weapon_choice_2)


func is_card_eligible(card: CardData) -> bool:
	match card.effect_type:
		"auto_attack", "attack_speed", "weapon_atk":
			return has_weapon
		"salvage":
			return wave >= 30
		"crit_momentum":
			return wave >= 25 or crit_rate >= 0.25
		_:
			return true


func show_card_choices() -> void:
	if pending_picks <= 0 or is_dead:
		$CardChoicePanel.hide()
		return

	var eligible: Array[CardData] = []
	for c in card_pool:
		if c != null and is_card_eligible(c):
			eligible.append(c)

	# 序盤で適格カードが3枚未満の場合はプール全体から補完（クラッシュ防止）
	if eligible.size() < 3:
		for c in card_pool:
			if c != null and not eligible.has(c):
				eligible.append(c)
	if eligible.size() < 3:
		print("Need at least 3 cards in card_pool")
		return

	eligible.shuffle()
	card_choice_1 = eligible[0]
	card_choice_2 = eligible[1]
	card_choice_3 = eligible[2]

	$CardChoicePanel/CardButton1.text = card_choice_1.card_name + "\n" + card_choice_1.description
	$CardChoicePanel/CardButton2.text = card_choice_2.card_name + "\n" + card_choice_2.description
	$CardChoicePanel/CardButton3.text = card_choice_3.card_name + "\n" + card_choice_3.description
	$CardChoicePanel.show()


func select_card(card: CardData) -> void:
	if card == null or is_dead:
		return

	match card.effect_type:
		"manual_attack":
			manual_attack_multiplier *= card.value
		"auto_attack":
			auto_attack_multiplier *= card.value
		"attack_speed":
			attack_speed_multiplier *= card.value
		"all_damage":
			all_damage_multiplier *= card.value
		"crit_rate":
			crit_rate += card.value
		"crit_multiplier":
			crit_multiplier += card.value
		"xp_gain":
			xp_multiplier *= card.value

	pending_picks = maxi(0, pending_picks - 1)
	update_ui()

	if pending_picks > 0:
		show_card_choices()
	else:
		$CardChoicePanel.hide()


func _on_card_button_1_pressed() -> void:
	select_card(card_choice_1)


func _on_card_button_2_pressed() -> void:
	select_card(card_choice_2)


func _on_card_button_3_pressed() -> void:
	select_card(card_choice_3)


func check_level_up() -> void:
	while xp + 1e-6 >= xp_to_level:
		xp -= xp_to_level
		level += 1
		xp_to_level = get_xp_to_level(level)
		pending_picks += 1

	if pending_picks > 0 and not $CardChoicePanel.visible and not is_dead:
		show_card_choices()
