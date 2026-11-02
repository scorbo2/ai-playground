extends Node
## Drives the real game through a scripted scenario, printing PASS/FAIL per
## assertion. Run via: godot --headless --path . -s res://tests/boot_test.gd

var _step := 0
var _elapsed := 0.0
var _failures := 0
var _wayward: Area3D = null


func _ready() -> void:
	get_tree().create_timer(25.0).timeout.connect(_timeout)


func _check(condition: bool, description: String) -> void:
	if condition:
		print("[TEST] PASS: %s" % description)
	else:
		_failures += 1
		print("[TEST] FAIL: %s" % description)


func _timeout() -> void:
	print("[TEST] TIMEOUT at step %d" % _step)
	get_tree().quit(2)


func _process(delta: float) -> void:
	_elapsed += delta
	var tree := get_tree()
	var main := tree.current_scene
	var rocks := tree.get_nodes_in_group("asteroids")
	var player := tree.get_first_node_in_group("player")
	var manager := tree.get_first_node_in_group("manager")

	match _step:
		0:
			if _elapsed < 1.0:
				return
			_check(rocks.size() == 12, "initial asteroid count is 12 (got %d)" % rocks.size())
			var visuals_ok := true
			for rock in rocks:
				if rock.get_child_count() < 2:
					visuals_ok = false
			_check(visuals_ok, "every asteroid has a mesh visual")
			var sane_spawn := true
			for rock in rocks:
				var d: float = rock.global_position.distance_to(player.global_position)
				if d < 100.0 or d > 320.0:
					sane_spawn = false
			_check(sane_spawn, "all rocks spawned 100-320 m from player")
			_advance()
		1:
			player._fire()
			var bolts := tree.get_nodes_in_group("bullets")
			_check(bolts.size() == 2, "firing spawns two bolts (got %d)" % bolts.size())
			for bolt in bolts:
				bolt.queue_free() # keep the test deterministic
			_advance()
		2:
			var victim: Area3D = tree.get_nodes_in_group("asteroids")[0]
			victim.hit()
			_check(victim.is_queued_for_deletion(), "hit() marks the asteroid for removal from play")
			_check(manager.score == 100, "score incremented to 100 (got %d)" % manager.score)
			var fx_ok := not main.find_children("*", "GPUParticles3D", true, false).is_empty()
			_check(fx_ok, "explosion FX spawned at kill site")
			_advance()
		3:
			if _elapsed < 4.0:
				return
			var count_after := tree.get_nodes_in_group("asteroids").size()
			_check(count_after == 12, "field refills to 12 after kill (got %d)" % count_after)
			_advance()
		4:
			# Teleport a rock way out of bounds; manager should recycle it in.
			_wayward = tree.get_nodes_in_group("asteroids")[1]
			_wayward.velocity = Vector3.ZERO
			_wayward.global_position = _wayward.global_position + Vector3(1000.0, 0.0, 0.0)
			_advance()
		5:
			if _elapsed < 0.3:
				return
			var dist: float = _wayward.global_position.distance_to(player.global_position)
			_check(dist < 320.0, "out-of-bounds rock recycled back into the zone (dist %.0f)" % dist)
			_advance()
		6:
			# Crash test: park a rock inside the player hull and let physics decide.
			var crasher: Area3D = tree.get_nodes_in_group("asteroids")[2]
			crasher.velocity = Vector3.ZERO
			crasher.global_position = player.global_position
			_advance()
		7:
			if _elapsed < 0.5:
				return
			var overlay: Control = main.get_node("HUD/GameOverPanel")
			_check(overlay.visible, "ship/asteroid collision ends the game (overlay shown)")
			_check(
				not player.died.get_connections().is_empty(),
				"died signal fired on collision"
			)
			print("[TEST] RESULT: %d failure(s)" % _failures)
			tree.quit(0 if _failures == 0 else 1)


func _advance() -> void:
	_step += 1
	_elapsed = 0.0
