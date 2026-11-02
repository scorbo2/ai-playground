extends Node3D

signal fire_requested(origin: Vector3, direction: Vector3)

const CRUISE_SPEED := 15.0
const BOOST_SPEED := 27.0
const ACCELERATION := 14.0
const PITCH_RATE := 1.25
const YAW_RATE := 1.45
const ROLL_RATE := 1.9
const FIRE_INTERVAL := 0.115

var model_scene: PackedScene
var controls_enabled := true
var speed := CRUISE_SPEED
var previous_position := Vector3.ZERO
var boosting := false

var _fire_cooldown := 0.0
var _muzzle_side := -1.0
var _exhausts: Array[MeshInstance3D] = []

func _ready() -> void:
	previous_position = global_position
	_build_visual()
	_build_exhaust()

func _physics_process(delta: float) -> void:
	_fire_cooldown = maxf(0.0, _fire_cooldown - delta)
	if not controls_enabled:
		_update_exhaust(delta, 0.0)
		return

	previous_position = global_position
	var pitch := Input.get_action_strength("pitch_up") - Input.get_action_strength("pitch_down")
	var yaw := Input.get_action_strength("yaw_left") - Input.get_action_strength("yaw_right")
	var roll := Input.get_action_strength("roll_left") - Input.get_action_strength("roll_right")

	rotate_object_local(Vector3.RIGHT, pitch * PITCH_RATE * delta)
	rotate_object_local(Vector3.UP, yaw * YAW_RATE * delta)
	rotate_object_local(Vector3.BACK, roll * ROLL_RATE * delta)
	basis = basis.orthonormalized()

	boosting = Input.is_action_pressed("boost")
	var target_speed := BOOST_SPEED if boosting else CRUISE_SPEED
	speed = move_toward(speed, target_speed, ACCELERATION * delta)
	global_position += forward() * speed * delta
	_update_exhaust(delta, 1.35 if boosting else 1.0)

	if Input.is_action_pressed("fire") and _fire_cooldown <= 0.0:
		_fire_cooldown = FIRE_INTERVAL
		_muzzle_side *= -1.0
		var origin := to_global(Vector3(_muzzle_side * 0.655, 0.115, -1.24))
		fire_requested.emit(origin, forward())

func forward() -> Vector3:
	return -global_basis.z.normalized()

func right() -> Vector3:
	return global_basis.x.normalized()

func up() -> Vector3:
	return global_basis.y.normalized()

func _build_visual() -> void:
	if model_scene == null:
		push_error("Ship controller requires the Skyjet model scene.")
		return
	var model := model_scene.instantiate()
	model.name = "SkyjetModel"
	model.scale = Vector3.ONE * 0.36
	add_child(model)

func _build_exhaust() -> void:
	var plume_material := StandardMaterial3D.new()
	plume_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	plume_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	plume_material.albedo_color = Color(0.03, 0.55, 1.0, 0.24)
	plume_material.emission_enabled = true
	plume_material.emission = Color(0.02, 0.55, 1.0)
	plume_material.emission_energy_multiplier = 2.5

	var plume_mesh := SphereMesh.new()
	plume_mesh.radius = 0.12
	plume_mesh.height = 0.24
	plume_mesh.radial_segments = 12
	plume_mesh.rings = 6

	var placements := [
		[Vector3(0.0, 0.10, 1.58), Vector3(1.25, 1.25, 5.4)],
		[Vector3(-0.533, 0.10, 1.47), Vector3(0.75, 0.75, 3.8)],
		[Vector3(0.533, 0.10, 1.47), Vector3(0.75, 0.75, 3.8)],
	]
	for placement in placements:
		var exhaust := MeshInstance3D.new()
		exhaust.mesh = plume_mesh
		exhaust.material_override = plume_material
		exhaust.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		exhaust.position = placement[0]
		exhaust.scale = placement[1]
		exhaust.set_meta("base_scale", placement[1])
		add_child(exhaust)
		_exhausts.append(exhaust)

func _update_exhaust(_delta: float, throttle: float) -> void:
	var pulse := 1.0 + sin(Time.get_ticks_msec() * 0.025) * 0.055
	for exhaust in _exhausts:
		var base_scale: Vector3 = exhaust.get_meta("base_scale")
		exhaust.scale = Vector3(base_scale.x, base_scale.y, base_scale.z * throttle * pulse)
		exhaust.visible = throttle > 0.01
