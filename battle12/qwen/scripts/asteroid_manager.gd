extends Node3D
## Keeps the rock population constant: when a bullet clears an asteroid,
## a replacement spawns elsewhere around the player. Rocks that drift too
## far are teleported back into the engagement zone - nothing ever leaves play.

@export var asteroid_scene: PackedScene
@export var target_count := 12
@export var min_spawn_dist := 170.0
@export var max_spawn_dist := 300.0
@export var recycle_dist := 380.0

const ASTEROID_MESHES: Array[PackedScene] = [
	preload("res://assets/asteroid_1.glb"),
	preload("res://assets/asteroid_2.glb"),
	preload("res://assets/asteroid_3.glb"),
	preload("res://assets/asteroid_4.glb"),
]

signal score_changed(new_score: int)

var score := 0
var spawn_enabled := true
var _respawn_pending := 0


func _ready() -> void:
	add_to_group("manager")
	for i in target_count:
		_spawn()


func add_score(points: int) -> void:
	score += points
	score_changed.emit(score)


func _process(_delta: float) -> void:
	var player := get_tree().get_first_node_in_group("player")
	if player == null:
		return
	var player_pos: Vector3 = player.global_position

	var active := get_tree().get_nodes_in_group("asteroids")
	for rock in active:
		if rock.global_position.distance_to(player_pos) > recycle_dist:
			_reposition(rock, player_pos)

	# Refill the field on a drip so arrivals feel random, not volleys.
	var missing := target_count - active.size() - _respawn_pending
	if spawn_enabled and missing > 0 and _respawn_pending == 0:
		_respawn_pending += 1
		var delay := randf_range(0.4, 1.2)
		get_tree().create_timer(delay).timeout.connect(_spawn_after_delay)


func _spawn_after_delay() -> void:
	_respawn_pending -= 1
	if spawn_enabled:
		_spawn()


func _spawn() -> void:
	if asteroid_scene == null:
		push_error("AsteroidManager: asteroid_scene not assigned")
		return
	var player := get_tree().get_first_node_in_group("player")
	var center: Vector3 = player.global_position if player else Vector3.ZERO

	var rock: Area3D = asteroid_scene.instantiate()
	add_child(rock)
	_reposition(rock, center)

	var visual: Node = ASTEROID_MESHES.pick_random().instantiate()
	rock.add_child(visual)


func _reposition(rock: Area3D, center: Vector3) -> void:
	var dir := _spread_direction(rock)
	rock.global_position = center + dir * randf_range(min_spawn_dist, max_spawn_dist)

	# Difficulty ramp: rocks drift faster the more you clear (capped).
	var pressure := minf(1.0 + score / 6000.0, 2.0)
	var rock_size := randf_range(1.4, 4.5)
	var velocity := -dir * randf_range(6.0, 16.0) * pressure
	velocity += Vector3(
		randf_range(-4.0, 4.0), randf_range(-4.0, 4.0), randf_range(-4.0, 4.0)
	)
	rock.setup(velocity, rock_size, randf_range(0.2, 1.2))


func _spread_direction(rock: Area3D) -> Vector3:
	# Mostly spawn ahead of the player's travel direction so rocks fly at them,
	# with enough spread that they can't get lazy about it.
	var base := Vector3.FORWARD
	if rock.get_parent() != null:
		var player := get_tree().get_first_node_in_group("player")
		if player != null:
			base = -player.global_transform.basis.z
	var dir := base.rotated(
		Vector3(randf_range(-1.0, 1.0), randf_range(-1.0, 1.0), randf_range(-1.0, 1.0)).normalized(),
		randf_range(0.0, 0.9)
	)
	return dir.normalized()
