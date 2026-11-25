# ファイル名: main_2d.gd

extends Node2D

@export var first_weapons: Array[WeaponData]
@export var card_pool: Array[CardData]

var hp: int = 5
var wave: int = 1
var has_weapon: bool = false
var current_weapon: WeaponData
var is_dead: bool = false
var weapon_choice_1: WeaponData
var weapon_choice_2: WeaponData
var is_choosing_weapon: bool = false
var card_choice_1: CardData
var card_choice_2: CardData
var card_choice_3: CardData
var manual_attack_multiplier: float =1.0
var auto_attack_multiplier: float = 1.0
var attack_speed_multiplier: float = 1.0
var xp: int =0
var level: int = 1
var xp_to_level: int = 3
var card_qualities: Array = []
var card_rolled_values: Array = []
var card_bonus_types: Array = []
const BONUS_VALUE: float = 1.10


func _ready() -> void:
	$RetryButton.hide()
	$CardChoicePanel.hide()
	$WeaponChoicePanel.hide()

	$EnemyTimer.start()
	update_ui()

func _process(_delta: float) -> void:
	if not is_dead:
		$TimeLabel.text = "Time: " + str(ceil($EnemyTimer.time_left))

func _on_button_pressed() -> void:
	if not is_dead:
		attack_enemy(roundi(2 * manual_attack_multiplier))

func _on_attack_timer_timeout() -> void:
	if has_weapon and not is_dead:
		attack_enemy(roundi(current_weapon.damage * auto_attack_multiplier))

func attack_enemy(damage: int) -> void:
	hp -= damage

	if hp <= 0:
		xp += 1
		print("XP gained:", xp)
		wave += 1
		check_level_up()
		hp = get_enemy_hp()
		$EnemyTimer.start()

		if wave >= 10 and not has_weapon and not is_choosing_weapon:
			get_first_weapon()

	update_ui()

func get_enemy_hp() -> int:
	#return (5+hp)*2
	return 10

func get_first_weapon() -> void:
	if first_weapons.size() < 2:
		print("first_weapon is empty")
		return

	is_choosing_weapon =true

	weapon_choice_1 = first_weapons[0]
	weapon_choice_2 = first_weapons[1]

	$WeaponChoicePanel/WeaponButton1.text =(
		weapon_choice_1.weapon_name
		+ "\nDamage: " + str(weapon_choice_1.damage)
		+ "\nInterval: " + str(weapon_choice_1.attack_interval) + "s"
	)
	$WeaponChoicePanel/WeaponButton2.text =(
		weapon_choice_2.weapon_name
		+ "\nDamage: " + str(weapon_choice_2.damage)
		+ "\nInterval: " + str(weapon_choice_2.attack_interval) + "s"
	)

	$WeaponChoicePanel.show()

func _on_enemy_timer_timeout() -> void:
	is_dead = true

	$AttackTimer.stop()
	$StatusLabel.text = "Defeated"
	$RetryButton.show()

func _on_retry_button_pressed() -> void:
	is_dead = false
	hp = get_enemy_hp()

	$StatusLabel.text = ""
	$RetryButton.hide()

	$EnemyTimer.start()

	if has_weapon:
		$AttackTimer.start()

	update_ui()

func update_ui() -> void:
	$Label.text = "HP: " + str(hp)
	$WaveLabel.text = "Wave: " + str(wave)

	$LevelLabel.text = "Level:" + str(level)
	$XPLabel.text = "XP:" + str(xp) + "/" + str(xp_to_level)

	$ManualMultiplierLabel.text = (
		"Manual Attack: x" + str(manual_attack_multiplier)
	)

	$AutoMultiplierLabel.text = (
		"Auto Attack: x" + str(auto_attack_multiplier)
	)

	$AttackSpeedMultiplierLabel.text = (
		"Attack Speed: x" + str(attack_speed_multiplier)
	)

func equip_weapon(weapon: WeaponData) -> void:
	has_weapon = true
	is_choosing_weapon = false
	current_weapon = weapon

	$WeaponLabel.text = "Weapon:" + current_weapon.weapon_name
	$AttackTimer.wait_time = current_weapon.attack_interval / attack_speed_multiplier
	$AttackTimer.start()
	$WeaponChoicePanel.hide()


func _on_weapon_button_1_pressed() -> void:
	equip_weapon(weapon_choice_1)


func _on_weapon_button_2_pressed() -> void:
	equip_weapon(weapon_choice_2)

func show_card_choices() -> void:
	if card_pool.size() < 3:
		print("Need at least 3 cards")
		return
	card_choice_1 = card_pool[0]
	card_choice_2 = card_pool[1]
	card_choice_3 = card_pool[2]
	var cards: Array = [card_choice_1, card_choice_2, card_choice_3]
	var buttons: Array = [$CardChoicePanel/CardButton1, $CardChoicePanel/CardButton2, $CardChoicePanel/CardButton3]
	card_qualities.clear()
	card_rolled_values.clear()
	card_bonus_types.clear()
	for n in range(3):
		var quality: Array = roll_quality()
		var rolled_value: float = 1.0 + (cards[n].value - 1.0) * float(quality[1])
		card_qualities.append(str(quality[0]))
		card_rolled_values.append(rolled_value)
		var bonus_type: String = ""
		if str(quality[0]) == "特上":
			bonus_type = bonus_type_for(cards[n].effect_type)
		card_bonus_types.append(bonus_type)
		var text: String = cards[n].card_name
		if str(quality[0]) != "並":
			text += " [" + str(quality[0]) + "]"
		text += "\n" + effect_label(cards[n].effect_type) + " x" + str(snapped(rolled_value, 0.01))
		if bonus_type != "":
			text += "\nBonus: " + effect_label(bonus_type) + " x" + str(BONUS_VALUE)
		buttons[n].text = text
		if str(quality[0]) == "特上":
			buttons[n].add_theme_color_override("font_color", Color(1.0, 0.84, 0.0))
		elif str(quality[0]) == "良":
			buttons[n].add_theme_color_override("font_color", Color(0.55, 0.8, 1.0))
		else:
			buttons[n].remove_theme_color_override("font_color")
	$CardChoicePanel.show()

func roll_quality() -> Array:
	var r: float = randf()
	if r < 0.08:
		return ["特上", 1.45]
	elif r < 0.30:
		return ["良", 1.2]
	return ["並", 1.0]

func bonus_type_for(effect_type: String) -> String:
	if effect_type == "manual_attack":
		return "attack_speed"
	elif effect_type == "auto_attack":
		return "manual_attack"
	return "auto_attack"

func effect_label(effect_type: String) -> String:
	if effect_type == "manual_attack":
		return "Manual Attack"
	elif effect_type == "auto_attack":
		return "Auto Attack"
	return "Attack Speed"

func apply_effect(effect_type: String, value: float) -> void:
	if effect_type == "manual_attack":
		manual_attack_multiplier *= value
		print("Manual Attack: ", manual_attack_multiplier)
	elif effect_type == "auto_attack":
		auto_attack_multiplier *= value
		print("Auto Attack:", auto_attack_multiplier)
	elif effect_type == "attack_speed":
		attack_speed_multiplier *= value
		print("Attack Speed: ", attack_speed_multiplier)
		if has_weapon:
			$AttackTimer.wait_time = current_weapon.attack_interval / attack_speed_multiplier

func select_card(card: CardData) -> void:
	var index: int = [card_choice_1, card_choice_2, card_choice_3].find(card)
	var rolled_value: float = card.value
	var bonus_type: String = ""
	if index >= 0 and card_rolled_values.size() == 3:
		rolled_value = card_rolled_values[index]
		bonus_type = card_bonus_types[index]
	print("Select card: ", card.card_name)
	apply_effect(card.effect_type, rolled_value)
	if bonus_type != "":
		print("Bonus effect: ", bonus_type)
		apply_effect(bonus_type, BONUS_VALUE)
	update_ui()
	$CardChoicePanel.hide()

func _on_card_button_1_pressed() -> void:
	select_card(card_choice_1)


func _on_card_button_2_pressed() -> void:
	select_card(card_choice_2)


func _on_card_button_3_pressed() -> void:
	select_card(card_choice_3)

func check_level_up() -> void:
	if xp >= xp_to_level:
		xp = 0
		level += 1
		show_card_choices()
