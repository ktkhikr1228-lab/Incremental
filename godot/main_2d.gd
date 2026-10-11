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

	$CardChoicePanel/CardButton1.text = (
		card_choice_1.card_name
		+ "\n"
		+ card_choice_1.description
	)
	$CardChoicePanel/CardButton2.text = (
		card_choice_2.card_name
		+ "\n"
		+ card_choice_2.description
	)
	$CardChoicePanel/CardButton3.text = (
		card_choice_3.card_name
		+ "\n"
		+ card_choice_3.description
	)
	$CardChoicePanel.show()


func select_card(card: CardData) -> void:
	print("Select card: ", card.card_name)

	if card.effect_type == "manual_attack":
		manual_attack_multiplier *= card.value
		print("Manual Attack: ", manual_attack_multiplier)

	elif card.effect_type == "auto_attack":
		auto_attack_multiplier *= card.value
		print("Auto Attack:",auto_attack_multiplier)

	elif card.effect_type == "attack_speed":
		attack_speed_multiplier *= card.value
		print("Attack Speed: " , attack_speed_multiplier)

		if has_weapon:
			$AttackTimer.wait_time =(
				current_weapon.attack_interval / attack_speed_multiplier
			)
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
