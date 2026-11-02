extends Area3D
## Free-flight space controls: mouse-steered yaw/pitch, WASD thrust.
## The Area3D doubles as the "crash sensor" - touching an asteroid is fatal.

signal died

const MOUSE_SENS := 0.0022
const PITCH_LIMIT := deg_to_rad(75.0)
const MAX_SPEED := 70.0
const BOOST_MULT := 1.9
const RESPONSE := 6.0 # higher = snappier velocity lerp
const FIRE_INTERVAL := 0.14

@export var bullet_scene: PackedScene

var _velocity := Vector3.ZERO
var _fire_timer := 0.0
var _alive := true

@onready var _model: Node3D = $ShipModel
@onready var _muzzles: Array[Node3D] = [$MuzzleR, $MuzzleL]


func _ready() -> void:
	add_to_group("player")
	area_entered.connect(_on_area_entered)
	_soften_engine_glow()


func _soften_engine_glow() -> void:
	# The glTF importer amplifies the Blender emission strength (3x), which
	# blooms the chase cam. Cap any hot emissive surface via per-surface
	# overrides so the imported asset itself stays untouched.
	for mesh_node in _model.find_children("*", "MeshInstance3D", true, true):
		for surface in mesh_node.mesh.get_surface_count():
			var mat = mesh_node.get_active_material(surface)
			if mat is StandardMaterial3D and mat.emission_enabled \
					and mat.emission_energy_multiplier > 1.0:
				var softened: StandardMaterial3D = mat.duplicate()
				softened.emission_energy_multiplier = 0.55
				mesh_node.set_surface_override_material(surface, softened)


func _unhandled_input(event: InputEvent) -> void:
	if not _alive:
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		_steer(event.relative)


func _steer(relative: Vector2) -> void:
	# Yaw always happens around the world Y axis; pitch around our local X.
	var yaw := Basis(Vector3.UP, -relative.x * MOUSE_SENS)
	var pitched_basis: Basis = yaw * transform.basis
	var pitch := Basis(pitched_basis.x, -relative.y * MOUSE_SENS)
	var candidate: Basis = pitch * pitched_basis
	# Reject the pitch step if the nose would exceed the limit (gimbal-free check).
	if absf((candidate * Vector3.FORWARD).dot(Vector3.UP)) > sin(PITCH_LIMIT):
		candidate = pitched_basis
	transform.basis = candidate


func _physics_process(delta: float) -> void:
	if not _alive:
		return

	var local := Vector3.ZERO
	local.x = _axis(KEY_D, KEY_A) # strafe
	local.y = _axis(KEY_SPACE, KEY_C) # climb / dive
	local.z = _axis(KEY_S, KEY_W) # W thrusts forward (-Z)

	# Modifier keys (Shift) report through logical state only - physical API skips them.
	var boost := BOOST_MULT if Input.is_key_pressed(KEY_SHIFT) else 1.0
	var wish := Vector3.ZERO
	if local != Vector3.ZERO:
		wish = transform.basis * local.normalized() * MAX_SPEED * boost
	_velocity = _velocity.lerp(wish, 1.0 - exp(-RESPONSE * delta))
	global_position += _velocity * delta

	_fire_timer -= delta
	if Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT) and _fire_timer <= 0.0:
		_fire_timer = FIRE_INTERVAL
		_fire()


func _axis(positive: Key, negative: Key) -> float:
	# Godot's action-axis helpers are logical-only; physical keys keep working
	# on non-QWERTY layouts, so we assemble the axis by hand.
	var response := 0.0
	if Input.is_physical_key_pressed(positive):
		response += 1.0
	if Input.is_physical_key_pressed(negative):
		response -= 1.0
	return response


func _fire() -> void:
	if bullet_scene == null:
		push_error("player: bullet_scene not assigned")
		return
	var forward := global_transform.basis * Vector3.FORWARD
	for muzzle in _muzzles:
		var bullet: Area3D = bullet_scene.instantiate()
		get_parent().add_child(bullet)
		bullet.global_transform = muzzle.global_transform
		bullet.direction = forward


func _on_area_entered(area: Area3D) -> void:
	if _alive and area.is_in_group("asteroids"):
		die()


func die() -> void:
	_alive = false
	monitoring = false
	_model.hide()
	_velocity = Vector3.ZERO
	Effects.explode(global_position, 3.2, get_parent())
	set_physics_process(false)
	died.emit()
