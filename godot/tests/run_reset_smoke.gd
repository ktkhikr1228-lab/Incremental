extends SceneTree

func _initialize() -> void:
	call_deferred("run_checks")

func next_choice_ready() -> void:
	for frame in range(3):
		await process_frame

func run_checks() -> void:
	var game = load("res://main_2d.tscn").instantiate()
	root.add_child(game)
	assert(game.get_node("EnemyTimer").timeout.is_connected(game._on_enemy_timer_timeout))
	assert(game.get_node("RetryButton").pressed.is_connected(game._on_retry_button_pressed))
	var weapon = game.first_weapons[0]
	var card = game.card_pool[1]
	game.equip_weapon(null)
	assert(not game.has_weapon)
	game.first_weapons[0] = null
	game.get_first_weapon()
	assert(not game.is_choosing_weapon and not game.get_node("WeaponChoicePanel").visible)
	game.first_weapons[0] = weapon
	game.card_pool[1] = null
	game.pending_card_picks = 1
	game.show_card_choices()
	assert(not game.is_choosing_card and game.pending_card_picks == 1)
	game.card_pool[1] = card
	game.show_card_choices()
	game.select_card(null)
	assert(game.pending_card_picks == 1)
	# Wave 9 -> 10 also grants a level: only Weapon Choice may be visible.
	game.wave = 9
	game.xp = 2
	game.hp = 1
	game.get_node("Button").pressed.emit()
	assert(game.wave == 10 and game.pending_card_picks == 2)
	assert(game.is_choosing_weapon and not game.is_choosing_card)
	assert(game.get_node("WeaponChoicePanel").visible)
	assert(not game.get_node("CardChoicePanel").visible)
	assert(not game.get_node("EnemyTimer").is_stopped())
	game.select_card(card)
	assert(game.pending_card_picks == 2)
	game.get_node("WeaponChoicePanel/WeaponButton1").pressed.emit()
	assert(game.has_weapon and game.is_choosing_card)
	assert(game.get_node("CardChoicePanel").visible)
	var hp_before = game.hp
	game.get_node("AttackTimer").timeout.emit()
	assert(game.hp < hp_before)
	game.get_node("CardChoicePanel/CardButton2").pressed.emit()
	game.get_node("CardChoicePanel/CardButton2").pressed.emit()
	assert(game.pending_card_picks == 1)
	assert(is_equal_approx(game.manual_attack_multiplier, card.value))
	await next_choice_ready()
	assert(game.is_choosing_card)
	game.get_node("CardChoicePanel/CardButton3").pressed.emit()
	assert(game.pending_card_picks == 0)
	# Actual timer expiry exercises the scene connection, during next-choice preparation.
	game.pending_card_picks = 2
	game.get_node("EnemyTimer").start(0.01)
	await create_timer(0.05).timeout
	game.get_node("EnemyTimer").wait_time = 10.0
	assert(game.is_dead)
	assert(game.pending_card_picks == 0 and not game.is_choosing_card)
	assert(not game.is_choosing_weapon and not game.is_resolving_card)
	assert(game.card_choice_1 == null and game.card_choice_2 == null and game.card_choice_3 == null)
	assert(game.weapon_choice_1 == null and game.weapon_choice_2 == null)
	assert(not game.has_weapon and game.current_weapon == null)
	assert(game.manual_attack_multiplier == 1.0 and game.auto_attack_multiplier == 1.0)
	assert(game.attack_speed_multiplier == 1.0)
	assert(not game.get_node("CardChoicePanel").visible and not game.get_node("WeaponChoicePanel").visible)
	assert(game.get_node("AttackTimer").is_stopped())
	hp_before = game.hp
	game.select_card(card)
	game.equip_weapon(weapon)
	game.attack_enemy(100)
	game.get_node("Button").pressed.emit()
	game.get_node("AttackTimer").timeout.emit()
	assert(game.hp == hp_before and not game.has_weapon and game.pending_card_picks == 0)
	game.get_node("RetryButton").pressed.emit()
	assert(not game.is_dead and game.wave == 1 and game.level == 1 and game.xp == 0)
	assert(game.hp == game.INITIAL_ENEMY_HP)
	assert(game.get_node("WeaponLabel").text == "Weapon: None")
	assert(game.get_node("AttackTimer").is_stopped())
	assert(not game.get_node("EnemyTimer").is_stopped())
	# Death during a visible Weapon Choice.
	game.get_first_weapon()
	game.get_node("EnemyTimer").timeout.emit()
	game.get_node("WeaponChoicePanel/WeaponButton1").pressed.emit()
	assert(not game.has_weapon and not game.is_choosing_weapon)
	game.get_node("RetryButton").pressed.emit()
	# Death + Retry before the old asynchronous preparation finishes.
	game.pending_card_picks = 2
	game.show_card_choices()
	game.get_node("CardChoicePanel/CardButton2").pressed.emit()
	game.get_node("EnemyTimer").timeout.emit()
	game.get_node("RetryButton").pressed.emit()
	await next_choice_ready()
	assert(game.pending_card_picks == 0 and not game.is_choosing_card)
	assert(not game.get_node("CardChoicePanel").visible)
	# Death during a visible Card Choice.
	game.pending_card_picks = 1
	game.show_card_choices()
	game.get_node("EnemyTimer").timeout.emit()
	assert(not game.get_node("CardChoicePanel").visible and game.pending_card_picks == 0)
	print("PASS: scene signals, new run reset, death guards, null resources, choice priority, double input, stale preparation")
	game.queue_free()
	quit()
