# ファイル名: main_2d.gd

extends Node2D

var hp: int = 5
var wave: int = 1
var has_weapon: bool = false
var weapon_name: String = ""
var weapon_damage: int = 0
var is_dead: bool = false

func _ready() -> void:
	$RetryButton.hide()
	$EnemyTimer.start()
	update_ui()

func _process(_delta: float) -> void:
	if not is_dead:
		$TimeLabel.text = "Time: " + str(ceil($EnemyTimer.time_left))

func _on_button_pressed() -> void:
	if not is_dead:
		attack_enemy(1)

func _on_attack_timer_timeout() -> void:
	if has_weapon and not is_dead:
		attack_enemy(weapon_damage)

func attack_enemy(damage: int) -> void:
	hp -= damage

	if hp <= 0:
		wave += 1
		hp = get_enemy_hp()
		$EnemyTimer.start()

		if wave >= 10 and not has_weapon:
			get_first_weapon()

	update_ui()

func get_enemy_hp() -> int:
	#return (5+hp)*2
	return 3

func get_first_weapon() -> void:
	has_weapon = true
	weapon_name = "Old Sword"
	weapon_damage = 1

	$WeaponLabel.text = "Weapon: " + weapon_name
	$AttackTimer.start()

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
